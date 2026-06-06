# Sandbox Mode

Run code agents in ephemeral Docker containers with GPU passthrough and profile-isolated state.

## Overview

Each sandbox session gets a fresh container with a random name (`codefreedom-XXXX`) — cleaned up automatically on exit. No container locking from shared reuse.

## Usage

```bash
# Basic sandbox
codefreedom claude --sandbox

# With a specific profile
codefreedom claude --sandbox --profile bare

# Bypass proxy, use native auth
codefreedom claude --sandbox --native-models

# GPU-specific images
codefreedom claude --sandbox --cuda   # NVIDIA GPU
codefreedom claude --sandbox --rocm   # AMD GPU

# Run as host user (for file permissions)
codefreedom claude --sandbox --run-as-me
```

## Available Images

Three pre-configured images on `docker.io/nilayparikh/codefreedom` (also available on `ghcr.io/nilayparikh/codefreedom` as a mirror):

| Image      | Description                          | Tags                                      |
| ---------- | ------------------------------------ | ----------------------------------------- |
| **CUDA**   | NVIDIA CUDA + PyTorch (AI workloads) | `cuda-latest`, `cuda-v0.1`, `cuda-v0.1.0` |
| **ROCm**   | AMD ROCm + PyTorch (AI workloads)    | `rocm-latest`, `rocm-v0.1`, `rocm-v0.1.0` |
| **Ubuntu** | General-purpose (no AI frameworks)   | `latest`, `v0.1`, `v0.1.0`                |

All images include Claude Code, Node.js, Python, Git, and essential dev tools. Use them as base images and extend per your needs:

```dockerfile
FROM docker.io/nilayparikh/codefreedom:cuda-latest
RUN pip install your-custom-package
```

### Selecting an Image

**Method 1: Environment variables** (applies to all profiles)

```bash
export CLAUDE_CODE_IMAGE_TAG=cuda-latest
codefreedom claude --sandbox
```

Three variables control the full image reference:

| Variable                 | Default                 | Purpose            |
| ------------------------ | ----------------------- | ------------------ |
| `CLAUDE_CODE_REGISTRY`   | `docker.io/nilayparikh` | Container registry |
| `CLAUDE_CODE_IMAGE_NAME` | `codefreedom`           | Image name         |
| `CLAUDE_CODE_IMAGE_TAG`  | `latest`                | Image tag          |

The resolved image is: `{REGISTRY}/{IMAGE_NAME}:{IMAGE_TAG}`.

**Method 2: Profile `sandbox_images`** (GPU-aware per-profile)

Set `sandbox_images` (a dict with `default`, `cuda`, and/or `rocm` keys) in the profile. Child profiles inherit from `default` and can override individual entries. When `--cuda` or `--rocm` is passed, the matching key is selected; otherwise `default` is used. See [Profile System → Sandbox Images per Profile](agents.md#sandbox-images).

## GPU Requirements

Sandbox mode always passes `--gpus all` to Docker. This means:

- **CUDA image:** Requires an NVIDIA GPU with the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) installed.
- **ROCm image:** Requires an AMD GPU with ROCm support and the appropriate container runtime.
- **Ubuntu image:** Works without a GPU — use this for CPU-only workloads.

If you have no GPU, use the Ubuntu image:

```bash
export CLAUDE_CODE_IMAGE_TAG=latest
codefreedom claude --sandbox
```

## Container Lifecycle

| Event                          | Behavior                                                   |
| ------------------------------ | ---------------------------------------------------------- |
| `codefreedom claude --sandbox` | Creates `codefreedom-XXXX`, execs agent, cleans up on exit |
| `Ctrl+C` or `/exit`            | Container stopped and removed automatically                |
| `codefreedom claude --stop`    | Stops and removes ALL `codefreedom-*` containers           |
| `codefreedom claude --status`  | Lists all `codefreedom-*` containers                       |

State is isolated per-profile: `~/.codefreedom/sandbox/{profile}/.claude` persists across sessions but each launch gets a clean container.

## Code Intelligence (LSP)

All sandbox images include **language server binaries** for Claude Code's code intelligence plugins. Plugins are not pre-installed — binaries are on `$PATH` so you activate only what you need:

```bash
# Inside a Claude Code session, run once per language:
/plugin install typescript-lsp@claude-plugins-official
/plugin install pyright-lsp@claude-plugins-official
/plugin install rust-analyzer-lsp@claude-plugins-official
/plugin install clangd-lsp@claude-plugins-official
```

Then run `/reload-plugins` to activate. Claude Code's LSP tool will automatically report type errors and warnings after edits, and you can ask Claude to jump to definitions or find references.

| Language   | Binary                       | Plugin              |
| ---------- | ---------------------------- | ------------------- |
| Python     | `pyright`                    | `pyright-lsp`       |
| TypeScript | `typescript-language-server` | `typescript-lsp`    |
| Rust       | `rust-analyzer`              | `rust-analyzer-lsp` |
| C / C++    | `clangd`                     | `clangd-lsp`        |

## Trade-offs vs Local Mode

| Aspect          | Sandbox                  | Local              |
| --------------- | ------------------------ | ------------------ |
| Isolation       | Full container           | Host environment   |
| GPU passthrough | Automatic (`--gpus all`) | Manual setup       |
| State           | Per-profile isolation    | Shared `~/.claude` |
| Cleanup         | Auto on exit             | N/A                |

## Security Note

Sandbox mode runs Claude Code with `--dangerously-skip-permissions` inside the container. This is safe because the container is ephemeral (destroyed on exit) and isolated from the host. In local mode, normal Claude Code permissions apply.

See [Local Mode](local.md) for the non-sandboxed alternative.
