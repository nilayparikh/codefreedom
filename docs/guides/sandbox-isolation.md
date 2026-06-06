# Sandbox Isolation

Sandbox mode runs Claude Code in ephemeral Docker containers with complete isolation from the host -- profile-isolated state, network separation, and controlled file access.

## How It Works

Each sandbox session creates a fresh container (`codefreedom-XXXX`) that is destroyed on exit. Claude Code is `docker exec`'d into the running container -- the container runs `sleep infinity` as PID 1, and the agent runs as a child process.

```
docker run -d --rm --name codefreedom-a1b2 ... sleep infinity
  |
  +-- docker exec -it codefreedom-a1b2 claude --dangerously-skip-permissions
```

This two-step approach keeps the container alive independently of the shell session, enabling clean cleanup on exit.

## Isolation Layers

### 1. Process Isolation (Container)

Each sandbox session runs in its own Docker container:

- **Ephemeral naming:** `codefreedom-XXXX` (random 4-hex character name).
- **Auto-cleanup:** `--rm` flag removes the container on exit. A `finally` block also runs `docker stop` + `docker rm -f` as a safety net.
- **Non-root user:** Runs as `codefreedom` (uid 1000) inside the container, not root.
- **`--run-as-me` option:** Maps host uid/gid into the container for file ownership compatibility.

### 2. File System Isolation

The container mounts only specific host paths -- nothing else is accessible:

| Mount | Direction | Purpose |
|-------|-----------|---------|
| `{workspace}:/workspace` | rw | Project files (read-write) |
| `~/.gitconfig:{container_home}/.gitconfig` | **ro** | Git identity (read-only) |
| `~/.ssh:{container_home}/.ssh` | **ro** | SSH keys (read-only) |
| `~/.codefreedom/sandbox/<profile>/.claude:{container_home}/.claude` | rw | **Profile-isolated** Claude Code state |
| `~/.codefreedom/sandbox/<profile>/.claude/.claude.json` | rw | **Fresh** config (never copied from host) |
| `{workspace}/.claude:/workspace/.claude` | rw | Workspace-level Claude state |
| `~/.codefreedom/sandbox/tools/.cache:{container_home}/.cache` | rw | Shared tools cache |

**Key isolation properties:**

- **Per-profile state:** Each profile gets its own `~/.codefreedom/sandbox/<profile>/.claude/` directory. Running `--profile ultra` never touches `--profile air`'s state.
- **Fresh config:** `.claude.json` is created as `{}` on each launch -- host config is never copied into the container.
- **Read-only host access:** `~/.gitconfig` and `~/.ssh` are mounted read-only. The container cannot modify them.
- **World-writable sandbox dirs:** Sandbox directories are `chmod 0o777` to handle uid/gid mismatches between host and container.

### 3. Network Isolation

The sandbox uses **host networking** (`--network host`):

- The container shares the host's network namespace.
- Tool containers (Chrome on port 9222, Camoufox on port 8420) are reachable via `localhost`.
- The proxy at `http://localhost:4000` is directly accessible.

This is a deliberate trade-off: host networking enables tool communication and proxy routing. If you need stricter network isolation, use Docker bridge networks with explicit port mappings.

### 4. GPU Isolation

GPU access is controlled via `--gpus all`:

- **CUDA image:** Requires NVIDIA GPU + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).
- **ROCm image:** Requires AMD GPU + ROCm container runtime.
- **Ubuntu image:** Works without a GPU (CPU-only).

The image is selected by profile (`sandbox_images` dict) or CLI flags (`--cuda`, `--rocm`).

### 5. IPC Isolation

The sandbox uses `--ipc=host` (shared IPC namespace) to improve GPU shared-memory performance and simplify inter-process communication.

## Session Lifecycle

```
codefreedom claude --sandbox --profile pro
  |
  |-- 1. Load env chain (7 tiers)
  |-- 2. Resolve profile "pro" (inherit from "default")
  |-- 3. Get sandbox image from profile (or env vars)
  |-- 4. Generate session ID: "codefreedom-a1b2"
  |-- 5. Acquire tools (start Chrome, Camoufox containers)
  |-- 6. Ensure sandbox dirs exist (~/.codefreedom/sandbox/pro/.claude/)
  |-- 7. docker run -d --rm --name codefreedom-a1b2 ... sleep infinity
  |-- 8. docker exec -it codefreedom-a1b2 claude ...
  |
  |-- (user works in Claude Code)
  |
  |-- 9. Ctrl+C or /exit -> Claude exits
  |-- 10. docker stop codefreedom-a1b2
  |-- 11. docker rm -f codefreedom-a1b2
  |-- 12. Release tools (decrement ref counts, stop if last session)
```

## Profile-Isolated State

Each profile gets its own isolated `.claude` directory:

```
~/.codefreedom/sandbox/
├── default/
│   └── .claude/
│       └── .claude.json    # Fresh {} on each launch
├── ultra/
│   └── .claude/
│       └── .claude.json    # Independent of "default"
├── pro/
│   └── .claude/
│       └── .claude.json    # Independent of "default"
└── tools/
    ├── chrome/             # Shared Chrome data
    ├── web/                # Shared Camoufox data
    └── .cache/             # Shared cache
```

This means:
- **No cross-profile contamination:** Running with `--profile ultra` never sees state from `--profile air`.
- **Persistent across sessions:** The directory persists between launches (only the container is ephemeral).
- **Clean slate:** `.claude.json` is always `{}` -- no host config leaks into the container.

## Tool Container Isolation

Tool containers (Chrome, Camoufox) are shared across sessions but isolated from the host:

### Chrome Container

- Runs with `--network host` (host networking for CDP access).
- `--shm-size=512m` (prevents Chrome crashes on shared memory).
- `--restart unless-stopped` (persists across session restarts).
- Persistent data at `~/.codefreedom/sandbox/tools/chrome/` (browser profiles, cache).

### Camoufox (Web) Container

- Runs on **bridge network** with port mapping (`-p 8420:8420`).
- Persistent data at `~/.codefreedom/sandbox/tools/web/`.

### Reference Counting

Tool containers are managed via reference counting in `~/.codefreedom/proc/`:

```
~/.codefreedom/proc/
├── sessions/
│   └── codefreedom-a1b2.json    # Session tracking: tools, PID, timestamp
└── tools/
    ├── chrome.json              # Lock file: ref_count, active sessions
    └── web.json                 # Lock file: ref_count, active sessions
```

- **`acquire_tools()`:** Starts containers if not running, increments ref count.
- **`release_tools()`:** Decrements ref count, stops container when it reaches 0.
- **Stale session cleanup:** On every acquire, dead PIDs are detected (`os.kill(pid, 0)`) and cleaned up. Running containers are **never stopped** during cleanup -- they are adopted by the next session.

## Security Considerations

### What Isolation Provides

| Threat | Mitigation |
|--------|------------|
| Host file modification | Only specific paths mounted; most are read-only |
| Host config contamination | Fresh `.claude.json` on each launch |
| Cross-profile state leakage | Per-profile `.claude` directories |
| Container persistence | `--rm` + explicit cleanup on exit |
| Root access | Runs as uid 1000 (`codefreedom` user) |

### Trade-offs

| Aspect | Current | Stricter Alternative |
|--------|---------|---------------------|
| Network | `--network host` | Bridge network + explicit port mappings |
| IPC | `--ipc=host` | Private IPC namespace |
| GPU | `--gpus all` | Selective device passthrough |
| Capabilities | Default | Minimal capabilities |

The current configuration prioritizes functionality (tool communication, proxy routing) over strict isolation. For higher-security environments, consider:

1. **Bridge networking:** Replace `--network host` with a custom bridge network and explicit port mappings.
2. **Private IPC:** Remove `--ipc=host` if GPU shared-memory performance isn't needed.
3. **Read-only workspace:** Mount the workspace as `:ro` if the agent only needs to read files.

## Image Selection

### Via Profile (`sandbox_images`)

```json
{
  "profiles": {
    "gpu-work": {
      "sandbox_images": {
        "default": "docker.io/nilayparikh/codefreedom:latest",
        "cuda": "docker.io/nilayparikh/codefreedom:cuda-latest",
        "rocm": "docker.io/nilayparikh/codefreedom:rocm-latest"
      }
    }
  }
}
```

When `--cuda` or `--rocm` is passed, the matching key is selected. Otherwise `default` is used.

### Via Environment Variables

```bash
export CLAUDE_CODE_REGISTRY=docker.io/nilayparikh
export CLAUDE_CODE_IMAGE_NAME=codefreedom
export CLAUDE_CODE_IMAGE_TAG=cuda-latest
```

Profile `sandbox_images` takes precedence over environment variables.

### Available Images

| Image | Registry | Tags | Use Case |
|-------|----------|------|----------|
| CUDA | `docker.io/nilayparikh/codefreedom` | `cuda-latest`, `cuda-v0.1.0` | NVIDIA GPU workloads |
| ROCm | `docker.io/nilayparikh/codefreedom` | `rocm-latest`, `rocm-v0.1.0` | AMD GPU workloads |
| Ubuntu | `docker.io/nilayparikh/codefreedom` | `latest`, `v0.1.0` | CPU-only / general-purpose |

Also available on `ghcr.io/nilayparikh/codefreedom` as a mirror.

## Container Management

```bash
# Stop all sandbox containers
codefreedom claude --stop

# Check container status
codefreedom claude --status
```

See [Sandbox Mode](sandbox.md) for GPU requirements and LSP setup, and [Profiles](profiles.md) for profile configuration details.
