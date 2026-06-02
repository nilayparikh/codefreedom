# Claude Code Launcher

The `codefreedom claude` (or `cf cc`) command is the primary way to launch
[Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview) with
profile-based model routing through your LiteLLM proxy.

> This replaces `claude-code.py` and `claude-code.sh` from the `.init` stack.
> `claude-code.sh` is no longer supported — use `codefreedom claude` instead.

## Quick Reference

```bash
# Default: native mode with Flash model
codefreedom claude
cf cc

# Sandbox mode (Docker container with isolated .claude state)
codefreedom claude --sandbox

# Native Anthropic models/auth (bypasses proxy, uses /login)
codefreedom claude --native-models
codefreedom claude --native-models --sandbox

# Pick a model profile
codefreedom claude --profile pro
codefreedom claude --profile ultra

# Combine: sandbox mode + a specific profile
codefreedom claude --sandbox --profile pro

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
| `claude` CLI               | Native/local mode               | `npm install -g @anthropic-ai/claude-code`      |
| `jq`                       | `--profile` / `--list-profiles` | `apt install jq` or `brew install jq`           |
| `NVIDIA Container Toolkit` | GPU passthrough                 | `nvidia-ctk runtime configure --runtime=docker` |

The Docker image is pulled from GHCR automatically — no local build needed for normal usage.

## Execution Modes

### Native Mode (Default)

Runs Claude Code directly on the host (no Docker container). Profiles use the
host's `~/.claude` directory directly. Requires Node.js and the Claude CLI:

```bash
npm install -g @anthropic-ai/claude-code
```

```bash
codefreedom claude
# or with a profile
codefreedom claude --profile pro
```

**By default, native mode routes through the LiteLLM proxy** —
`ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN` from your profile are preserved.
Use `--native-models` if you want to bypass the proxy and use native Anthropic
`/login` auth instead.

### Sandbox Mode (`--sandbox`)

Runs Claude Code inside a persistent Docker container with GPU passthrough,
network isolation, profile-isolated `~/.codefreedom/{profile}/.claude` state,
and full model routing through LiteLLM.

```bash
codefreedom claude --sandbox
# or with a specific profile
codefreedom claude --sandbox --profile default
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

### Sandbox Mode

Runs Claude Code inside a persistent Docker container with GPU passthrough,
profile-isolated `~/.codefreedom/{profile}/.claude` state, and multi-session support.

```bash
codefreedom claude --sandbox
```

**The sandbox has its own isolated `.claude` directory** — conversation history,
settings, and session state are stored in `~/.codefreedom/{profile}/.claude`
so each profile stays completely separate from your host's `~/.claude` and
from other profiles.

**Requirements:**

```bash
docker --version
```

**Trade-offs vs native mode:**

| Aspect                           | Sandbox Mode                      | Native Mode           |
| -------------------------------- | --------------------------------- | --------------------- |
| Isolation                        | Full container sandbox            | Host environment      |
| GPU passthrough                  | Automatic (`--gpus all`)          | Requires manual setup |
| Concurrent sessions              | Yes (multi-exec)                  | Host-dependent        |
| `.claude` state isolation        | ✅ per-profile                    | ❌ shared host dir    |
| `--dangerously-skip-permissions` | Safe (container boundaries)       | Requires trust        |
| Startup time                     | ~2s (exec into running container) | ~0.5s (direct)        |

### Native Models Mode

Use `--native-models` to bypass the LiteLLM proxy and use Claude Code's native
Anthropic model discovery and `/login` authentication. This strips
`ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, and `IS_SANDBOX` from the
environment, so Claude Code falls back to its default behavior.

```bash
# Native mode with native Anthropic models
codefreedom claude --native-models

# Sandbox mode with native Anthropic models
codefreedom claude --native-models --sandbox
```

`--native-models` is the **only** way to get native `/login` auth — all
profiles (including `bare`) route through the LiteLLM proxy by default.

## Profile System

Profiles define sets of environment variables that control Claude Code's
model selection, routing, and behavior. They are defined in
`~/.codefreedom/profiles/claude-code.json` (initialized via `codefreedom --init`).

### How Profiles Work

1. Environment loading follows a strict precedence order (later wins):

```
~/.env.secrets  (auth tokens — always highest precedence)
       ↓
workspace/.env  (project configuration)
       ↓
profile env     (mode-specific overrides from profiles)
       ↓
script defaults (fallback values in codefreedom)
```

2. **Profile inheritance:** Most profiles inherit from `default`. The inheritance rules are:

| Profile               | Inheritance             | Effect                                                                                                                           |
| --------------------- | ----------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `default`             | Standalone              | Loads its own env vars directly                                                                                                  |
| `bare`                | Standalone              | Loads only its minimal env vars — **no model aliases, no sandbox settings, no preferences**. Still routes through LiteLLM proxy. |
| `ultra`, `pro`, `air` | Inherits from `default` | Loads `default` env vars first, then overlays profile-specific overrides                                                         |

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

4. **In sandbox mode, each profile gets an isolated `~/.codefreedom/{profile}/.claude` directory.**
   In native mode, profiles use the host's `~/.claude` directly.
   This means:
   - Sandbox: conversation history, settings, and session state are **isolated per profile**
   - Sandbox: `~/.codefreedom/` houses all sandbox state, separate from your host `~/.claude`
   - Native: `~/.claude` on the host is shared across profiles (traditional behavior)

5. Profiles are resolved on the **host side** before Docker exec — no
   container rebuild needed.

### Built-in Profiles

| Profile   | Model               | Inheritance             | Best For                                                |
| --------- | ------------------- | ----------------------- | ------------------------------------------------------- |
| `default` | `CodeFreedom/Flash` | Standalone (base)       | General purpose, discovery, scanning                    |
| `ultra`   | `CodeFreedom/Ultra` | Inherits from `default` | Architecture, planning, complex reasoning               |
| `pro`     | `CodeFreedom/Pro`   | Inherits from `default` | Bounded implementation, precise code writing            |
| `air`     | `CodeFreedom/Air`   | Inherits from `default` | Mechanical scanning, large-file reading                 |
| `bare`    | _(default)_         | Standalone (minimal)    | Minimal mode — no aliases, routes through LiteLLM proxy |

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
| `./claude-code.py --local`         | `codefreedom claude --sandbox`       |
| `./claude-code.py --native`        | `codefreedom claude --native-models` |
| `./claude-code.py --stop`          | `codefreedom claude --stop`          |
| `./claude-code.py --status`        | `codefreedom claude --status`        |
| `./claude-code.py --list-profiles` | `codefreedom claude --list-profiles` |

The profiles file is at `~/.codefreedom/profiles/claude-code.json` (initialized
via `codefreedom --init`). Copy your custom profiles from `.init`'s root
`claude-code-profiles.json` into `~/.codefreedom/profiles/claude-code.json`.
