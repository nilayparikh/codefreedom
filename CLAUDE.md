# CodeFreedom — CLAUDE.md

> Unified CLI wrapper for code agents. Switch LLM providers, isolate environments, eliminate config sprawl.

## Project Purpose

CodeFreedom solves three problems:

1. **Model lock-in** — switch LLM providers without reconfiguring your code agent.
2. **Environment chaos** — isolated, reproducible environments per project with GPU support.
3. **Config sprawl** — profiles, proxy routing, and sandbox settings managed from one place (`~/.codefreedom`).

It orchestrates code agents through their **publicly supported interfaces only** (environment variables, CLI flags, API endpoints). No patching, no reverse-engineering.

### Goals

- **Agent-agnostic architecture.** Each code agent (Claude Code, Cursor, Codex) gets a subcommand, profile, and routes through the same proxy. Claude Code is the first implementation.
- **Just configuration.** Profiles are environment variables. Proxy routing is standard LiteLLM config.
- **Opt-in providers.** Set an API key to enable a provider. Leave it empty to disable. Nothing phones home by default.

## Behavioral Guidelines

- **Think before coding.** State assumptions. Ask if uncertain. Surface tradeoffs.
- **Simplicity first.** Minimum code that solves the problem. No speculative features or abstractions.
- **Surgical changes.** Touch only what's needed. Match existing style. Clean up only your own mess.
- **Goal-driven.** Define verifiable success criteria. Loop until tests pass.

## Internal Specs

Internal standards live in `/specs/` (not published to GitHub Pages — that's `/docs/`).

| Document              | Purpose                                                                            |
| --------------------- | ---------------------------------------------------------------------------------- |
| `specs/cli-output.md` | CLI output conventions: prefixes, streams, punctuation, return codes               |
| `specs/code-style.md` | Code style: module organization, shared utilities, tool patterns, type annotations |

## Commands

```bash
pip install -e ".[dev]"          # editable install with dev deps
pip install -e ".[all]"          # everything (dev + docs)
python -m pytest tests/ -v       # run tests
ruff check src/ tests/           # lint
mypy src/                        # type-check
python -m codefreedom --help     # CLI (no install needed)
mkdocs serve -a localhost:8080   # local docs preview
./scripts/release.sh             # cut a release (bumps version, tags, publishes)
```

The proxy is always run via `docker compose` against the self-hosted
`codefreedom:litellm-latest` image. No host-side `litellm` install is
required (and the `[litellm]` extra has been removed).

## Architecture

```
src/codefreedom/
├── __init__.py      # __version__ from importlib.metadata
├── __main__.py      # python -m codefreedom entry point
├── admin.py         # Backup/restore engine (manifest, diff, prune)
├── config.py        # CODEFREEDOM_HOME resolution (defaults to ~/.codefreedom)
├── cli/
│   ├── main.py            # Top-level parser, dispatches to subcommands
│   ├── admin.py           # 'codefreedom admin' — backup, restore, list, inspect, prune
│   ├── claude.py          # 'codefreedom claude' — profile loading, run dispatch
│   ├── proxy.py           # 'codefreedom proxy' — lifecycle (start/stop/status)
│   ├── chrome.py          # 'codefreedom tools chrome' — start/stop/status/url
│   ├── web.py             # 'codefreedom tools web' — start/stop/status (Camoufox)
│   ├── github.py          # 'codefreedom tools github' — GitHub MCP server lifecycle
│   ├── web_bridge.py      # 'codefreedom tools web-bridge' — SearXNG→Camoufox bridge
│   ├── tools.py           # Unified tool management (start/stop/restart/status all)
│   ├── docker_utils.py    # Shared Docker helpers (start/stop/status/ephemeral names)
│   ├── recipe.py          # Recipe system — fetch, plan, apply config recipes
│   ├── update.py          # 'codefreedom update' — Docker image + PyPI version checks
│   ├── vscode.py          # 'codefreedom vscode' — VS Code config fragment generation
│   ├── doctor.py          # 'codefreedom doctor' — environment diagnostic checks
│   ├── deinit.py          # 'codefreedom deinit' — full teardown (containers + config)
│   └── tool_init_utils.py # Shared acceptance prompt, notices, tool metadata
├── profiles.py      # Profile JSON loading, ${VAR} resolution, inheritance
├── tool_registry.py # Reference-counted tool lifecycle via ~/.codefreedom/proc/
├── launcher.py      # Docker sandbox and native local execution
├── env_loader.py    # .env chain: component-specific → legacy → workspace → system
└── recipes/         # Configuration recipes from github.com/nilayparikh/codefreedom-recipes
```

Entry points: `codefreedom` / `cf` → `src/codefreedom/cli/main.py:main`

### Architecture Docs

| Document          | Purpose                                                         |
| ----------------- | --------------------------------------------------------------- |
| `ARCHITECTURE.md` | Full architecture map — components, dependencies, request flows |

Use the `arch-docs` skill to keep this current when code changes.

### CLI Commands

| Command                                                    | Description                                                                |
| ---------------------------------------------------------- | -------------------------------------------------------------------------- |
| `codefreedom init recipe`                                  | Install default base recipe from codefreedom-recipes                       |
| `codefreedom init recipe --list`                           | List available recipes                                                     |
| `codefreedom init recipe --plan NAME`                      | Preview a recipe without applying                                          |
| `codefreedom init recipe --apply PLAN_ID`                  | Apply a previously generated plan                                          |
| `codefreedom init recipe --store URL_OR_PATH`              | Use a custom recipe store (GitHub URL or local folder)                     |
| `codefreedom claude`                                       | Launch Claude Code (alias: `cf cc`)                                        |
| `codefreedom claude --sandbox`                             | Launch in Docker container with GPU                                        |
| `codefreedom claude --cuda`                                | Use CUDA GPU image (with --sandbox)                                        |
| `codefreedom claude --rocm`                                | Use ROCm GPU image (with --sandbox)                                        |
| `codefreedom claude --run-as-me`                           | Run sandbox as host user (uid/gid match)                                   |
| `codefreedom claude --native-models`                       | Bypass proxy, use Anthropic `/login`                                       |
| `codefreedom claude --profile PROFILE`                     | Use a specific profile (default: "default")                                |
| `codefreedom claude --list-profiles`                       | List available profiles                                                    |
| `codefreedom claude config`                                | Resolve profile env vars for standalone use                                |
| `codefreedom claude --dangerously-skip-permissions`        | Skip permission prompts (local mode)                                       |
| `codefreedom mimo`                                         | Launch MiMoCode with 0-click proxy auto-config (alias: `cf mc`)            |
| `codefreedom mimo --sandbox`                               | Launch in Docker container                                                 |
| `codefreedom mimo --run-as-me`                             | Run sandbox as host user (uid/gid match)                                   |
| `codefreedom mimo --profile PROFILE`                       | Use a specific profile (default: "default")                                |
| `codefreedom mimo --list-profiles`                         | List available profiles                                                    |
| `codefreedom mimo config`                                  | Generate proxy-resolved `mimocode.json` for standalone use                 |
| `codefreedom proxy init`                                   | Initialize proxy configs + .env.proxy                                      |
| `codefreedom proxy start`                                  | Start the proxy (Docker Compose; only mode)                                |
| `codefreedom proxy start --port PORT`                      | Override `LITELLM_PORT` for this run only (default: 4000)                  |
| `codefreedom proxy start --host HOST`                      | Override `LITELLM_BIND_HOST` for this run only (default: 0.0.0.0)          |
| `codefreedom proxy stop`                                   | Stop proxy                                                                 |
| `codefreedom proxy restart`                                | Restart proxy (Docker Compose; preserves state, no image pull)             |
| `codefreedom proxy status`                                 | Show proxy status                                                          |
| `codefreedom proxy validate`                               | Validate proxy config                                                      |
| `codefreedom admin backup`                                 | Backup CodeFreedom config (no secrets)                                     |
| `codefreedom admin backup --out PATH`                      | Backup to a specific path                                                  |
| `codefreedom admin restore PATH`                           | Restore with interactive diff preview                                      |
| `codefreedom admin restore PATH --dry-run`                 | Preview restore without making changes                                     |
| `codefreedom admin restore PATH --force`                   | Restore without confirmation prompt                                        |
| `codefreedom admin list-backups`                           | List all available backups (alias: `ls`)                                   |
| `codefreedom admin inspect PATH`                           | Show manifest contents of a backup archive                                 |
| `codefreedom admin prune --keep N`                         | Keep N most recent backups, delete rest                                    |
| `codefreedom admin prune --older-than 30d`                 | Delete backups older than duration                                         |
| `codefreedom update`                                       | Check all CodeFreedom Docker images and PyPI for updates (alias: `cf upd`) |
| `codefreedom update sandbox`                               | Check only sandbox images                                                  |
| `codefreedom update chrome`                                | Check only Chrome tool image                                               |
| `codefreedom update web`                                   | Check only Web tool image                                                  |
| `codefreedom update proxy`                                 | Check only proxy images (litellm + web-bridge)                             |
| `codefreedom vscode claude config`                         | Print a VS Code `settings.json` fragment for the Claude Code extension     |
| `codefreedom vscode claude config --profile PROFILE`       | Render the fragment for a specific profile                                 |
| `codefreedom vscode claude config --host HOST --port PORT` | Override `ANTHROPIC_BASE_URL` host/port in the fragment                    |
| `codefreedom vscode claude config --out PATH`              | Write the fragment to a file instead of stdout                             |
| `codefreedom vscode proxy config --host H`                 | Generate a VS Code `chatLanguageModels.json` entry from the proxy          |
| `codefreedom tools chrome init`                            | Initialize Chrome tool profile (requires acceptance)                       |
| `codefreedom tools chrome start`                           | Start Chrome browser container (Xvfb + Chromium)                           |
| `codefreedom tools chrome stop`                            | Stop Chrome container                                                      |
| `codefreedom tools chrome restart`                         | Restart Chrome container (preserves state, no image pull)                  |
| `codefreedom tools chrome status`                          | Show Chrome container status                                               |
| `codefreedom tools chrome url`                             | Print CDP debug URL for agent connection                                   |
| `codefreedom tools web init`                               | Initialize Camoufox tool profile (requires acceptance)                     |
| `codefreedom tools web start`                              | Start Camoufox container (MCP server on port 8420)                         |
| `codefreedom tools web stop`                               | Stop Camoufox container                                                    |
| `codefreedom tools web restart`                            | Restart Camoufox container (preserves state, no image pull)                |
| `codefreedom tools web status`                             | Show Camoufox container status                                             |
| `codefreedom tools start`                                  | Start all tools (chrome, web, github, web-bridge)                          |
| `codefreedom tools stop`                                   | Stop all tools                                                             |
| `codefreedom tools restart`                                | Restart all tools                                                          |
| `codefreedom tools status`                                 | Show status of all tools                                                   |
| `codefreedom tools github init`                            | Initialize GitHub MCP tool profile (requires acceptance)                   |
| `codefreedom tools github start`                           | Start GitHub MCP container (stdio-to-HTTP bridge on port 8082)             |
| `codefreedom tools github stop`                            | Stop GitHub MCP container                                                  |
| `codefreedom tools github restart`                         | Restart GitHub MCP container (preserves state, no image pull)              |
| `codefreedom tools github status`                          | Show GitHub MCP container status                                           |
| `codefreedom tools web-bridge init`                        | Initialize web-bridge tool profile (requires acceptance)                   |
| `codefreedom tools web-bridge start`                       | Start web-bridge container (SearXNG endpoint on port 8500)                 |
| `codefreedom tools web-bridge stop`                        | Stop web-bridge container                                                  |
| `codefreedom tools web-bridge restart`                     | Restart web-bridge container (preserves state, no image pull)              |
| `codefreedom tools web-bridge status`                      | Show web-bridge container status                                           |
| `codefreedom doctor`                                       | Run full environment diagnostic (alias: `cf doc`, `cf dr`)                 |
| `codefreedom doctor --verbose`                             | Show detail messages for all checks                                        |
| `codefreedom deinit`                                       | Full teardown: stop containers, remove ~/.codefreedom (interactive)        |
| `codefreedom deinit --force`                               | Full teardown without confirmation prompt                                  |
| `cf cc`                                                    | Alias for `codefreedom claude`                                             |
| `cf px`                                                    | Alias for `codefreedom proxy`                                              |
| `cf adm`                                                   | Alias for `codefreedom admin`                                              |
| `cf upd` / `cf up`                                         | Alias for `codefreedom update`                                             |
| `cf vsc`                                                   | Alias for `codefreedom vscode`                                             |
| `cf doc` / `cf dr`                                         | Alias for `codefreedom doctor`                                             |

## Key Patterns

### Profile Inheritance

### Claude Code Profiles (`profiles.json`)

- `default` and `bare` are **standalone** — no inheritance.
- All other profiles inherit from `default`. Profile's own `env` merges on top.
- Mode-specific overrides (`sandbox.env`, `local.env`) also inherit: custom profile gets `default`'s mode env first, then its own.
- **`tools` field** (`"tools": ["chrome", "web"]`): declares tool containers to auto-start.
  First session starts them, last session stops them. Child profiles merge with default's
  tools (deduplicated). Set `"tools": []` to opt out. Tracked via `~/.codefreedom/proc/`.
  Works in both sandbox and local modes.

### MiMoCode Profiles (`~/.codefreedom/profiles/mimo-code.yaml`)

Same structure as Claude Code profiles, using MiMoCode-specific environment variables.
The `default` and `bare` profiles are standalone; all others inherit from `default`.

| Profile   | Purpose                          | Key env vars                                      |
| --------- | -------------------------------- | ------------------------------------------------- |
| `default` | Base — 0-click proxy auto-config | `LITELLM_BASE_URL`, `MIMOCODE_DISABLE_AUTOUPDATE` |
| `bare`    | Minimal standalone               | `MIMOCODE_MIMO_ONLY`                              |
| `ultra`   | Maximum capability               | `MIMOCODE_EXPERIMENTAL=1`                         |
| `pro`     | Production coding                | `MIMOCODE_PERMISSION=build`                       |
| `flash`   | Speed-optimized                  | Disables heavy plugins                            |
| `air`     | Minimal-resource                 | Disables background work                          |
| `ui-ux`   | Frontend/design                  | `MIMOCODE_MAX_PROMPT_IMAGES=20`                   |

The generated `mimocode.json` (auto-created from proxy model list) is injected via
`MIMOCODE_CONFIG` env var — all proxy models are available as `codefreedom/<model-id>`.

### Tool Profiles (`~/.codefreedom/profiles/<tool>.yaml`)

Tools (chrome, web, github, web-bridge) load settings from
`~/.codefreedom/profiles/<tool>.yaml`. Created by `cf init recipe`.
Tools refuse to start without a valid profile. Legacy `.json` profiles
for chrome/web are still supported for backward compatibility.

| Setting          | Default                                           | Profile override                                                                            |
| ---------------- | ------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `image`          | `docker.io/nilayparikh/codefreedom:chrome-latest` | Change to a different tag or registry (also on `ghcr.io/nilayparikh/codefreedom` as mirror) |
| `container_name` | `codefreedom-tools-chrome`                        | Custom container name                                                                       |
| `port`           | `9222`                                            | CDP debug port                                                                              |
| `data_dir`       | `~/.codefreedom/sandbox/tools/chrome`             | Persistent data mount                                                                       |
| `env`            | `CHROME_DEBUG_PORT=9222`                          | Extra env vars forwarded to container                                                       |

Chrome runs headless. For stealth / anti-bot browsing, use the `web` tool (Camoufox) instead.

### Tools are Shared, Persistent Infrastructure

Tools (chrome, web/camoufox, github, web-bridge) are **shared** — once started
they keep running until explicitly stopped (`cf tools <name> stop`). Container
names are **static** (from the profile, e.g. `codefreedom-tools-chrome`). All
sessions and profiles share the same tool container:

1. First `cf cc` or `cf tools <name> start` creates the container.
2. Subsequent invocations detect it's already running and are no-ops.
3. `cf tools <name> stop` is the only way to stop it.
4. No random suffixes, no auto-cleanup, no per-session isolation.

Ports are configured in the tool profile and can be overridden via documented
environment variables (checked at profile load time):

| Tool       | Env var                       | Default    |
| ---------- | ----------------------------- | ---------- |
| Chrome     | `CODEFREEDOM_CHROME_PORT`     | `9222`     |
| Web        | `CODEFREEDOM_WEB_PORT`        | `8420`     |
| GitHub     | `CODEFREEDOM_GITHUB_PORT`     | `0` (auto) |
| Web-bridge | `CODEFREEDOM_WEB_BRIDGE_PORT` | `8500`     |

The proxy (`litellm` + `web-bridge`) is **separate** — it gets unique
container names + project name per instance via `generate_container_name()`
because the proxy config (port, providers) varies by instance.

### Environment Variable Chain

Component-specific env files are loaded only for the matching subcommand. Shared
and workspace env files are loaded for all components.

**Priority groups** (all configs before secrets, user overrides before machine env):

- Config files (lowest priority): `.env.claude` / `.env.proxy` → `.env` → `{workspace}/.env`
- Secrets files: `.env.claude.secrets` / `.env.proxy.secrets` → `.env.secrets` → `{workspace}/.env.secrets`
- User overrides: `.env.user` (highest config priority, never touched by recipes)
- Machine env (highest priority): `os.environ`
- `CF_CLI_*` overrides (absolute highest): any env var prefixed `CF_CLI_`
  (e.g. `CF_CLI_LITELLM_MASTER_KEY`) is stripped of its prefix and applied
  as a final override, beating everything. Use this for shell-level overrides
  that must always win regardless of `.env` file contents.

**codefreedom claude** (8 layers + CF_CLI, lowest to highest):

1. `{codefreedom_dir}/.env.claude` — Claude Code config (skips if missing)
2. `{codefreedom_dir}/.env` — shared config (skips if missing)
3. `{workspace}/.env` — workspace config (skips if missing)
4. `{codefreedom_dir}/.env.claude.secrets` — Claude Code secrets (skips if missing)
5. `{codefreedom_dir}/.env.secrets` — shared secrets (skips if missing)
6. `{workspace}/.env.secrets` — workspace secrets (skips if missing)
7. `{codefreedom_dir}/.env.user` — user overrides (skips if missing)
8. `os.environ` — system env (always wins)
9. `CF_CLI_*` — machine env vars prefixed with `CF_CLI_` are stripped
   of the prefix and applied as final overrides (always wins everything)

**codefreedom proxy** (8 layers + CF_CLI):

1. `{codefreedom_dir}/.env.proxy` — proxy config (skips if missing)
2. `{codefreedom_dir}/.env` — shared config (skips if missing)
3. `{workspace}/.env` — workspace config (skips if missing)
4. `{codefreedom_dir}/.env.proxy.secrets` — proxy secrets (skips if missing)
5. `{codefreedom_dir}/.env.secrets` — shared secrets (skips if missing)
6. `{workspace}/.env.secrets` — workspace secrets (skips if missing)
7. `{codefreedom_dir}/.env.user` — user overrides (skips if missing)
8. `os.environ` — system env (always wins)
9. `CF_CLI_*` — machine env vars prefixed with `CF_CLI_` are stripped
   of the prefix and applied as final overrides (always wins everything)

**codefreedom tools** (chrome, web, etc.) — 6 layers + CF_CLI:

1. `{codefreedom_dir}/.env` — shared config (skips if missing)
2. `{workspace}/.env` — workspace config (skips if missing)
3. `{codefreedom_dir}/.env.secrets` — shared secrets (skips if missing)
4. `{workspace}/.env.secrets` — workspace secrets (skips if missing)
5. `{codefreedom_dir}/.env.user` — user overrides (skips if missing)
6. `os.environ` — system env (always wins)
7. `CF_CLI_*` — machine env vars prefixed with `CF_CLI_` are stripped
   of the prefix and applied as final overrides (always wins everything)

All layers support `${VAR}` and `${VAR:-default}` interpolation. **Empty-string env vars are valid overrides** (`export FOO=""` does NOT fall through to defaults).

### Version Source of Truth

Only `pyproject.toml` holds the version. `__init__.py` derives `__version__` from `importlib.metadata` — never edit it directly.

### Proxy System

- LiteLLM instance routing model requests to providers (DeepSeek, Azure Foundry, NVIDIA, local).
- Default: **stateless** (no database). Optional PostgreSQL unlocks Admin UI, spend tracking.
- Provider config: `~/.codefreedom/proxy/config/providers/*.yaml` — opt-in via API key env vars.
- Model aliases controlled by env vars: `LITELLM_MODEL_ALIAS_BEST`, `LITELLM_MODEL_ALIAS_FABLE`, `LITELLM_MODEL_ALIAS_SONNET`, `LITELLM_MODEL_ALIAS_OPUS`, `LITELLM_MODEL_ALIAS_HAIKU`, `LITELLM_MODEL_ALIAS_SONNET_1M`, `LITELLM_MODEL_ALIAS_OPUS_1M`, `LITELLM_MODEL_ALIAS_OPUSPLAN`.

#### Reasoning-efforts mapping plugin (v2)

The proxy ships a CustomLogger plugin that translates reasoning-effort signals
across provider standards using **rule-based mapping**. Claude Code emits
Anthropic's `output_config.effort` (low / medium / high / xhigh / max) but
DeepSeek and OpenAI expect `reasoning_effort` (none / low / medium / high /
xhigh). The plugin resolves a rule per model and applies it on every request.

**Two rule types:**

- **`mapping`** — maps incoming reasoning-level strings to values the downstream
  model accepts via a `values` dict (direct incoming→outgoing map).
- **`thinking_budget`** — maps reasoning-level strings to a numeric thinking-token
  budget, written to a dotted-path field (e.g. `extra_body.max_thinking_tokens`).

A model may have exactly one rule (inline via `model_info`, or named from YAML).
No rule → pure field rename (`output_config.effort` ↔ `reasoning_effort`) using
the provider's native output type.

**Files:**
| File | Purpose |
|------|---------|
| `docker/litellm/plugins/reasoning_efforts_mapping.py` | Plugin module — baked into Docker image |
| `~/.codefreedom/proxy/config/plugins/reasoning-efforts/reasoning-efforts-mapping.yaml` | User-editable override (created by `cf init recipe`) |
| `tests/test_reasoning_efforts_mapping.py` | Unit tests |

**Key facts:**

- The plugin runs on `async_pre_request_hook` (Anthropic `/v1/messages`) and `async_log_pre_api_call` (OpenAI `/v1/chat/completions`).
- Rules are resolved from `model_info.codefreedom.plugins.reasoning-efforts` (inline) or the YAML config (named). Fallback is `auto` — pure field rename based on provider detection.
- The `.py` module is baked into the LiteLLM image at `/app/litellm-plugins/`. The entrypoint symlinks it into the host-mounted config directory at container start (avoids writing the .py onto the host filesystem).
- The YAML config lives on the host (user-editable). Cached by mtime — edits take effect on the next request without a proxy restart.
- Wired in `config.yaml` via `callbacks: ["plugins.reasoning-efforts.reasoning_efforts_mapping.instance"]` — the lowercase `instance` is a module-level singleton (not the class) to match LiteLLM's callback dispatch.
- The `proxy init` flow copies the YAML config alongside the rest of the proxy config.

### Sandbox Containers

- Ephemeral: `codefreedom-XXXX` (random 4-hex name), auto-removed on exit via `--rm` + `finally` fallback.
- Pattern: container runs `sleep infinity`; Claude Code is `docker exec`'d into it.
- Volume mounts: workspace (rw), `~/.gitconfig` (ro), `~/.ssh` (ro), per-profile `~/.codefreedom/sandbox/<profile>/.claude` (isolated, gitignored).
- `sandbox_images` mapping (dict with `default`/`cuda`/`rocm` keys): child profiles inherit from `default` and can override individual entries. Falls back to env vars (`CLAUDE_CODE_REGISTRY/IMAGE_NAME/IMAGE_TAG`) → hardcoded default if unset.

## Docker

### Naming Convention

Docker tags **must be lowercase** — Docker considers uppercase tags valid but the
community standard is lowercase. This applies to local tags, CI tags, and registry
references. Examples:

| ✅ Correct                            | ❌ Incorrect                          |
| ------------------------------------- | ------------------------------------- |
| `codefreedom:chrome`                  | `codefreedom:Chrome`                  |
| `ghcr.io/.../codefreedom:cuda-latest` | `ghcr.io/.../codefreedom:CUDA-latest` |
| `codefreedom:rocm-v0.1.0`             | `codefreedom:ROCm-v0.1.0`             |
| `codefreedom:web`                     | `codefreedom:Web`                     |

### Image Families

Seven image families in `docker/` published to `docker.io/nilayparikh/codefreedom` (also available on `ghcr.io/nilayparikh/codefreedom` as a mirror). The **GitHub MCP Server** tool uses the official `ghcr.io/github/github-mcp-server` image (not built by CodeFreedom):

| Image          | Dockerfile                             | Use Case                                                                                                                                                  |
| -------------- | -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **CUDA**       | `docker/claude-code/Dockerfile.CUDA`   | NVIDIA GPU workloads                                                                                                                                      |
| **ROCm**       | `docker/claude-code/Dockerfile.ROCm`   | AMD GPU workloads                                                                                                                                         |
| **Ubuntu**     | `docker/claude-code/Dockerfile.Ubuntu` | CPU-only / general-purpose                                                                                                                                |
| **Chrome**     | `docker/chrome/Dockerfile.Chrome`      | Headless Chromium for browser automation via CDP port 9222                                                                                                |
| **Web**        | `docker/web/Dockerfile.Web`            | Camoufox MCP server for stealth / anti-bot web search and scraping                                                                                        |
| **GitHub MCP** | `docker/github/Dockerfile.Github`      | stdio-to-HTTP bridge over `ghcr.io/github/github-mcp-server`, exposes GitHub API tools via HTTP MCP on port 8082                                          |
| **LiteLLM**    | `docker/litellm/Dockerfile.LiteLLM`    | Self-hosted LiteLLM proxy image. Replaces `ghcr.io/berriai/litellm` in the proxy compose stack. Bakes in the WebSearch count display patch at build time. |
| **Web Bridge** | `docker/web-bridge/Dockerfile.Bridge`  | FastAPI SearXNG-shaped sidecar → Camoufox MCP for transparent WebSearch interception                                                                      |

Images are built, cosign-signed, and published by per-family GitHub Actions workflows (`docker-cuda.yml`, `docker-rocm.yml`, `docker-ubuntu.yml`, `docker-chrome.yml`, `docker-web.yml`, `docker-github.yml`, `docker-litellm.yml`, `docker-web-bridge.yml`) on changes to their respective Dockerfiles. Each workflow also runs a `verify` job against both registries — see [Image Supply Chain](#image-supply-chain-cosign) under CI/CD.

## CI/CD

| Workflow                | Trigger                                        | Purpose                                                                            |
| ----------------------- | ---------------------------------------------- | ---------------------------------------------------------------------------------- |
| `integration-test.yml`  | push/PR                                        | Tests on Python 3.10/11/12 across Ubuntu, Windows, macOS                           |
| `docker-cuda.yml`       | `docker/claude-code/Dockerfile.CUDA` changes   | Build, cosign-sign, and publish CUDA image to `docker.io` + `ghcr.io`              |
| `docker-rocm.yml`       | `docker/claude-code/Dockerfile.ROCm` changes   | Build, cosign-sign, and publish ROCm image to `docker.io` + `ghcr.io`              |
| `docker-ubuntu.yml`     | `docker/claude-code/Dockerfile.Ubuntu` changes | Build, cosign-sign, and publish Ubuntu image to `docker.io` + `ghcr.io`            |
| `docker-chrome.yml`     | `docker/chrome/Dockerfile.Chrome` changes      | Build, cosign-sign, and publish Chrome image to `docker.io` + `ghcr.io`            |
| `docker-web.yml`        | `docker/web/Dockerfile.Web` changes            | Build, cosign-sign, and publish Camoufox web image to `docker.io` + `ghcr.io`      |
| `docker-github.yml`     | `docker/github/Dockerfile.Github` changes      | Build, cosign-sign, and publish GitHub MCP bridge image to `docker.io` + `ghcr.io` |
| `docker-litellm.yml`    | `docker/litellm/Dockerfile.LiteLLM` changes    | Build, cosign-sign, and publish LiteLLM proxy image to `docker.io` + `ghcr.io`     |
| `docker-web-bridge.yml` | `docker/web-bridge/Dockerfile.Bridge` changes  | Build, cosign-sign, and publish web-bridge image to `docker.io` + `ghcr.io`        |
| `gated-checkin.yml`     | push/PR                                        | Release-gate checks on tagged commits                                              |
| `pipy.yaml`             | `v*` tags                                      | Publish to PyPI                                                                    |
| `publish-docs.yml`      | push to `main`                                 | Build MkDocs site, deploy to GitHub Pages                                          |
| `trivy.yml`             | push/PR                                        | Security scanning with Trivy                                                       |

### Image Supply Chain (Cosign)

All published images are signed with [Sigstore cosign](https://github.com/sigstore/cosign) using **keyless (OIDC) signing** — the workflow run is the signer, no long-lived private key is required. The pattern lives in two reusable composite actions so adding a new image family is a one-line change per registry:

| Action                          | Purpose                                                                                                |
| ------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `.github/actions/cosign-sign`   | Installs cosign and runs `cosign sign --yes <image@digest>`. Caller is responsible for registry login. |
| `.github/actions/cosign-verify` | Installs cosign and runs `cosign verify` against the GitHub OIDC issuer and the repo identity.         |

Each `docker-*.yml` workflow has the same structure:

1. **`build` job** — builds, pushes to both registries, then calls `cosign-sign` for the Docker Hub and GHCR refs.
2. **`verify` job** (`needs: build`) — re-logs in and calls `cosign-verify` for both refs, proving the published digest is verifiable by anyone.

Consumer verification (works on any tag):

```bash
cosign verify \
  --certificate-identity-regexp 'https://github.com/nilayparikh/codefreedom' \
  --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' \
  ghcr.io/nilayparikh/codefreedom:cuda-latest
```

**Adding a new image family.** Copy any `docker-*.yml`, change the `Dockerfile` path, the `IMAGE_VERSION` arg, the family tag (e.g. `cuda-v…` → `rocm-v…`), and the cache `scope`. The build/sign/verify wiring is already inherited — no cosign knowledge required.

## Tests

Nineteen test modules in `tests/`, all using `pytest` with `tmp_path` fixtures and `monkeypatch` for path isolation — never touching real `~/.codefreedom/` during tests.

| File                                | Coverage                                                              |
| ----------------------------------- | --------------------------------------------------------------------- |
| `test_admin.py`                     | Backup, restore, list, inspect, prune, sha256, categorization         |
| `test_chrome.py`                    | Chrome tool container lifecycle (start/stop/status/url)               |
| `test_deinit.py`                    | Full teardown: stop containers, remove config, preserve .env.user     |
| `test_doctor.py`                    | Environment diagnostics: config, Docker, ports, permissions           |
| `test_docker_utils.py`              | Docker container lifecycle helpers (start/stop/status)                |
| `test_env_loader.py`                | `.env` parsing, component-aware chain precedence, `${VAR}` resolution |
| `test_github.py`                    | GitHub MCP tool container lifecycle (start/stop/status/restart)       |
| `test_recipe.py`                    | Recipe system — fetch, plan, apply, merge                             |
| `test_mcp_endpoints.py`             | MCP endpoint configuration and validation                             |
| `test_profiles.py`                  | Profile loading, inheritance, env resolution                          |
| `test_proxy.py`                     | Path resolution, config validation, Docker Compose discovery          |
| `test_reasoning_efforts_mapping.py` | Reasoning-efforts plugin: normalisation, config, translation          |
| `test_vscode_claude.py`             | VS Code Claude Code config fragment generation                        |
| `test_vscode_proxy.py`              | VS Code proxy config fragment generation                              |
| `test_web.py`                       | Web (Camoufox) tool container lifecycle                               |
| `test_web_bridge.py`                | Web bridge (SearXNG → Camoufox MCP) integration                       |

CI runs tests on Python 3.10/11/12 across Ubuntu, Windows, and macOS via `integration-test.yml`.

## Gotchas

### parse_known_args rescue pattern

When an unknown flag appears **before** a known flag, `parse_known_args` puts ALL remaining args into the unknown list. The `_CLAUDE_BOOL_FLAGS` dict in `main.py` rescues CodeFreedom flags. **If you add a new boolean flag to the claude subcommand, add it to `_CLAUDE_BOOL_FLAGS` too.**

### `eprint` and `_VAR_REF_RE` — single source of truth

`eprint()` is defined once in `env_loader.py` — all modules import from there. Do not duplicate it in other files. If a circular import would result, refactor the dependency instead.

`_VAR_REF_RE` (the `${VAR}` / `${VAR:-default}` regex) is defined once in `interpolate.py` — all modules import from there. The shared `resolve_env_vars()` and `resolve_env_dict()` functions handle all interpolation. Do not inline regex substitution in other modules.

### `--dangerously-skip-permissions`

Sandbox mode **always** passes this to Claude CLI inside the container. Local mode only passes it if the user explicitly requests it.

### Unicode in output strings breaks Windows CI

Windows terminal defaults to cp1252 encoding, which cannot encode Unicode box-drawing characters (`─`, `◆`, `★`, etc.). Any `print()` or string that uses these characters will cause a `UnicodeEncodeError` on Windows.

**Always use plain ASCII in user-facing strings** — replace `───` with `---`, `◆` with `*`, etc.
Affected files: `src/codefreedom/cli/claude.py`, `proxy.py`, `tool_init_utils.py` (the `_NOTICE`/`_NON_DISCLAIMER` variables).

### Tool profiles use YAML — not JSON

Tool profiles (`chrome`, `web`, `github`, `web-bridge`) use `.yaml` files at
`~/.codefreedom/profiles/<tool>.yaml`. Legacy `.json` profiles for chrome/web
are still supported. The `github` and `web-bridge` tools are YAML-only.

### Proxy is Docker-only — no native mode

The proxy always runs via `docker compose` against the self-hosted
`codefreedom:litellm-latest` image. There is no `--docker` flag, no native
Python path, and no `litellm` extra in `pyproject.toml`. If you add a new
proxy subcommand, do not reintroduce native-mode logic. The image bakes in
patches at build time from `docker/litellm/patches/`
(`patch_websearch_count.py`, `patch_responses_azure.py`); do not re-add
volume mounts or entrypoint wrappers for them.

### CustomLogger callbacks: reference `instance`, not the class

LiteLLM's `get_instance_fn` does `getattr(module, name)` and stores the
result directly in `litellm.callbacks`. If a callback is a **class**
(not an instance), `isinstance(Callback, CustomLogger)` returns `False`,
and the class object ends up in callbacks — then `callback.method(...)`
fails with missing `self`. Always reference a module-level singleton
instance (lowercase `instance`) from `config.yaml`, e.g.
`plugins.reasoning_efforts_mapping.instance`.

### Patches are baked into the LiteLLM image, not mounted at runtime

Patches in `docker/litellm/patches/` are applied during the image build
(`COPY patches/...` + `RUN python patch_*.py` in `Dockerfile.LiteLLM`).
Older guides referenced mount-it-at-runtime; that pattern is gone.
If you change LiteLLM and a patch can no longer find its target, the
build fails loudly — do not silently fall back.

## What to Include vs Exclude

### Include in CLAUDE.md

- Commands that developers run frequently (install, test, lint, build)
- Architecture overview with module responsibilities
- Non-obvious patterns (inheritance, env chain, interpolation)
- Gotchas that cause bugs if misunderstood
- Behavioral guidelines (brief, actionable)

### Exclude from CLAUDE.md

- Detailed API documentation (use `/docs` for that)
- Full CLI flag reference (use `--help` output)
- Provider-specific configuration details (use proxy docs)
- Dockerfile contents (use `docker/` directory)
- Changelog or release notes (use `CHANGELOG.md`)
- Anything the agent can discover by reading the source code directly
