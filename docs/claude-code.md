# Claude Code Launcher

The `codefreedom claude` (or `cf cc`) command is the primary way to launch
[Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview) with
profile-based model routing through your LiteLLM proxy.

> This replaces `claude-code.py` and `claude-code.sh` from the `.init` stack.
> `claude-code.sh` is no longer supported — use `codefreedom claude` instead.

## Quick Reference

```bash
# Default: Docker mode with Flash model
codefreedom claude
cf cc

# Local mode (no Docker container)
codefreedom claude --local

# Pick a model profile
codefreedom claude --profile pro
codefreedom claude --profile ultra

# Combine: local mode + a specific profile
codefreedom claude --local --profile pro

# List available profiles
codefreedom claude --list-profiles

# Stop the persistent container
codefreedom claude --stop

# Show container status
codefreedom claude --status

# Pass additional Claude CLI flags
codefreedom claude --resume "<session-id>"
codefreedom claude -p "Write a unit test for this function"
codefreedom claude --profile pro --worktree feature-x
```

## Dependencies

| Dependency                 | Required For                    | Notes                                           |
| -------------------------- | ------------------------------- | ----------------------------------------------- |
| `docker`                   | Docker mode                     | Standard install                                |
| `claude` CLI               | `--local` mode                  | `npm install -g @anthropic-ai/claude-code`      |
| `jq`                       | `--profile` / `--list-profiles` | `apt install jq` or `brew install jq`           |
| `NVIDIA Container Toolkit` | GPU passthrough                 | `nvidia-ctk runtime configure --runtime=docker` |

The Docker image is pulled from GHCR automatically — no local build needed for normal usage.

## Execution Modes

### Docker Mode (Default)

Runs Claude Code inside a persistent Docker container with GPU passthrough,
network isolation, and full model routing through LiteLLM.

```bash
codefreedom claude
# or explicitly
codefreedom claude --profile default
```

**Container lifecycle:**

| Event                                 | Behavior                                                                                   |
| ------------------------------------- | ------------------------------------------------------------------------------------------ |
| First invocation                      | Pulls image from GHCR, creates container with `sleep infinity`, then `docker exec` into it |
| Subsequent invocations                | Reuses the running container — just `docker exec` a new Claude session                     |
| `Ctrl+C` in a session                 | Kills only that Claude process — container and other sessions continue                     |
| `/exit` in Claude                     | Exits that session only — container stays alive                                            |
| Last session exits                    | Container keeps running (shows `Reusing running container` next time)                      |
| `codefreedom claude --stop`           | Stops and removes the container                                                            |
| `docker restart claude-dev-workspace` | Resets container state, config dirs preserved                                              |

**Why persistent container?**

The old pattern (`docker run --rm`) created a fresh container every time and
cleaned it up on exit. This meant:

- `Ctrl+C` or `/exit` **killed the container** — any other sessions attached to it died too
- No concurrent sessions — each terminal had to wait for the other to finish
- Container startup overhead on every invocation

The persistent pattern uses `docker run -d ... sleep infinity` to keep the
container alive, and each invocation attaches via `docker exec -it`. Multiple
terminals can each run `codefreedom claude` simultaneously, and `Ctrl+C` only
affects that session.

### Local Mode

Runs Claude Code directly on the host (no Docker container). Useful for
lightweight tasks, testing, or environments where Docker isn't available.

```bash
codefreedom claude --local
```

**Requirements:** The `claude` CLI must be installed on the host:

```bash
npm install -g @anthropic-ai/claude-code
```

**Trade-offs vs Docker mode:**

| Aspect                           | Docker Mode                       | Local Mode            |
| -------------------------------- | --------------------------------- | --------------------- |
| Isolation                        | Full container sandbox            | Host environment      |
| GPU passthrough                  | Automatic (`--gpus all`)          | Requires manual setup |
| Concurrent sessions              | Yes (multi-exec)                  | Host-dependent        |
| `--dangerously-skip-permissions` | Safe (container boundaries)       | Requires trust        |
| Startup time                     | ~2s (exec into running container) | ~0.5s (direct)        |

## Profile System

Profiles define sets of environment variables that control Claude Code's
model selection, routing, and behavior. They are defined in
`profiles/claude-code-profiles.json`.

### How Profiles Work

1. Environment loading follows a strict precedence order (later wins):

```
~/.env.secrets  (auth tokens — always highest precedence)
       ↓
workspace/.env  (project configuration)
       ↓
profile env     (mode-specific overrides from claude-code-profiles.json)
       ↓
script defaults (fallback values in codefreedom)
```

2. **Profile inheritance:** Most profiles inherit from `default`. The inheritance rules are:

| Profile               | Inheritance             | Effect                                                                                      |
| --------------------- | ----------------------- | ------------------------------------------------------------------------------------------- |
| `default`             | Standalone              | Loads its own env vars directly                                                             |
| `bare`                | Standalone              | Loads only its minimal env vars — **no model aliases, no sandbox settings, no preferences** |
| `ultra`, `pro`, `air` | Inherits from `default` | Loads `default` env vars first, then overlays profile-specific overrides                    |

This means `ultra`, `pro`, and `air` only need to specify what's different
(`CLAUDE_MODEL`). Everything else — sandbox settings, model aliases, IDE
suppression flags — comes from `default`.

3. **Custom profiles** also inherit from `default` automatically. Create a
   profile with only the vars you want to override:

```json
{
  "profiles": {
    "my-custom": {
      "description": "Custom profile — overrides model and endpoint",
      "env": {
        "CLAUDE_MODEL": "CodeFreedom/Ultra",
        "ANTHROPIC_BASE_URL": "http://custom-proxy.local:4000"
      }
    }
  }
}
```

4. **All profiles share the same `~/.claude` and `workspace/.claude` directories.**
   This means:
   - Conversation history is preserved across profile switches
   - Settings, skills, plugins, and session state are consistent
   - Only runtime behavior changes (which model is used, which endpoint is targeted)

5. Profiles are resolved on the **host side** before Docker exec — no
   container rebuild needed.

### Built-in Profiles

| Profile   | Model               | Inheritance             | Best For                                     |
| --------- | ------------------- | ----------------------- | -------------------------------------------- |
| `default` | `CodeFreedom/Flash` | Standalone (base)       | General purpose, discovery, scanning         |
| `ultra`   | `CodeFreedom/Ultra` | Inherits from `default` | Architecture, planning, complex reasoning    |
| `pro`     | `CodeFreedom/Pro`   | Inherits from `default` | Bounded implementation, precise code writing |
| `air`     | `CodeFreedom/Air`   | Inherits from `default` | Mechanical scanning, large-file reading      |
| `bare`    | _(default)_         | Standalone (minimal)    | Minimal mode — native Anthropic auth         |

### Multi-Endpoint Profiles

Profiles can target different LiteLLM proxies by setting `ANTHROPIC_BASE_URL`
and `ANTHROPIC_AUTH_TOKEN`:

```json
{
  "profiles": {
    "local": {
      "description": "Local self-hosted inference",
      "env": {
        "CLAUDE_MODEL": "CodeFreedom/Pro",
        "ANTHROPIC_BASE_URL": "http://localhost:4000",
        "ANTHROPIC_AUTH_TOKEN": "sk-local-key"
      }
    },
    "cloud": {
      "description": "Cloud proxy endpoint",
      "env": {
        "CLAUDE_MODEL": "CodeFreedom/Ultra",
        "ANTHROPIC_BASE_URL": "https://cloud-proxy.example.com",
        "ANTHROPIC_AUTH_TOKEN": "sk-cloud-key"
      }
    }
  }
}
```

## Migrating from .init

If you previously used `.init`'s `claude-code.py` or `claude-code.sh`:

| Old (.init)                        | New (codefreedom)                    |
| ---------------------------------- | ------------------------------------ |
| `./claude-code.py`                 | `codefreedom claude`                 |
| `./claude-code.sh`                 | `codefreedom claude`                 |
| `./claude-code.py --profile pro`   | `codefreedom claude --profile pro`   |
| `./claude-code.py --local`         | `codefreedom claude --local`         |
| `./claude-code.py --stop`          | `codefreedom claude --stop`          |
| `./claude-code.py --status`        | `codefreedom claude --status`        |
| `./claude-code.py --list-profiles` | `codefreedom claude --list-profiles` |

The profiles file is now at `profiles/claude-code-profiles.json` instead of
the workspace root. Copy your custom profiles from `.init`'s root
`claude-code-profiles.json` into codefreedom's `profiles/` directory.
