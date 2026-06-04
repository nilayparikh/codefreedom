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

## Commands

```bash
pip install -e ".[dev]"          # editable install with dev deps
pip install -e ".[litellm]"      # with proxy (LiteLLM) support
pip install -e ".[all]"          # everything (dev + litellm + docs)
python -m pytest tests/ -v       # run tests
ruff check src/ tests/           # lint
mypy src/                        # type-check
python -m codefreedom --help     # CLI (no install needed)
mkdocs serve -a localhost:8080   # local docs preview
./scripts/release.sh             # cut a release (bumps version, tags, publishes)
```

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
│   ├── claude.py          # 'codefreedom claude' — init, profile loading, run dispatch
│   ├── proxy.py           # 'codefreedom proxy' — init, lifecycle (start/stop/status)
│   ├── chrome.py          # 'codefreedom tools chrome' — init, start/stop/status/url
│   ├── web.py             # 'codefreedom tools web' — init, start/stop/status (Camoufox)
│   ├── docker_utils.py    # Shared Docker helpers (start/stop/status/ephemeral names)
│   ├── init_utils.py      # Shared init bootstrap (bundled examples, all-or-nothing copy)
│   └── tool_init_utils.py # Shared acceptance prompt, notices, tool metadata
├── profiles.py      # Profile JSON loading, ${VAR} resolution, inheritance
├── tool_registry.py # Reference-counted tool lifecycle via ~/.codefreedom/proc/
├── launcher.py      # Docker sandbox and native local execution
├── env_loader.py    # .env chain: component-specific → legacy → workspace → system
└── examples/        # Bundled into package, copied by init commands
    ├── claude/      # profiles + .env.claude.example, .env.claude.secrets.example
    ├── proxy/       # config.yaml, docker-compose.yaml, providers/, env files
    └── tools/       # chrome/ and web/ profile + schema files
```

Entry points: `codefreedom` / `cf` → `src/codefreedom/cli/main.py:main`

### Architecture Docs

| Document          | Purpose                                                         |
| ----------------- | --------------------------------------------------------------- |
| `ARCHITECTURE.md` | Full architecture map — components, dependencies, request flows |

Use the `arch-docs` skill to keep this current when code changes.

### CLI Commands

| Command                                             | Description                                                   |
| --------------------------------------------------- | ------------------------------------------------------------- |
| `codefreedom claude init`                           | Initialize Claude Code profiles + .env.claude                 |
| `codefreedom claude`                                | Launch Claude Code (alias: `cf cc`)                           |
| `codefreedom claude --sandbox`                      | Launch in Docker container with GPU                           |
| `codefreedom claude --cuda`                         | Use CUDA GPU image (with --sandbox)                           |
| `codefreedom claude --rocm`                         | Use ROCm GPU image (with --sandbox)                           |
| `codefreedom claude --native-models`                | Bypass proxy, use Anthropic `/login`                          |
| `codefreedom claude --profile PROFILE`              | Use a specific profile (default: "default")                   |
| `codefreedom claude --list-profiles`                | List available profiles                                       |
| `codefreedom claude --stop`                         | Stop running sandbox containers                               |
| `codefreedom claude --status`                       | Show sandbox container status                                 |
| `codefreedom claude --dangerously-skip-permissions` | Skip permission prompts (local mode)                          |
| `codefreedom proxy init`                            | Initialize proxy configs + .env.proxy                         |
| `codefreedom proxy start`                           | Start LiteLLM proxy (native Python)                           |
| `codefreedom proxy start --docker`                  | Start via Docker Compose                                      |
| `codefreedom proxy stop`                            | Stop proxy                                                    |
| `codefreedom proxy restart --docker`                | Restart proxy (Docker Compose native; preserves state)        |
| `codefreedom proxy status`                          | Show proxy status                                             |
| `codefreedom proxy validate`                        | Validate proxy config                                         |
| `codefreedom proxy --port PORT`                     | Set proxy port (default: 4000)                                |
| `codefreedom proxy --host HOST`                     | Set bind host (default: 0.0.0.0)                              |
| `codefreedom admin backup`                          | Backup CodeFreedom config (no secrets)                        |
| `codefreedom admin backup --out PATH`               | Backup to a specific path                                     |
| `codefreedom admin restore PATH`                    | Restore with interactive diff preview                         |
| `codefreedom admin restore PATH --dry-run`          | Preview restore without making changes                        |
| `codefreedom admin restore PATH --force`            | Restore without confirmation prompt                           |
| `codefreedom admin list-backups`                    | List all available backups                                    |
| `codefreedom admin inspect PATH`                    | Show manifest contents of a backup archive                    |
| `codefreedom admin prune --keep N`                  | Keep N most recent backups, delete rest                       |
| `codefreedom admin prune --older-than 30d`          | Delete backups older than duration                            |
| `codefreedom tools chrome init`                     | Initialize Chrome tool profile (requires acceptance)          |
| `codefreedom tools chrome start`                    | Start Chrome browser container (Xvfb + Chromium)              |
| `codefreedom tools chrome stop`                     | Stop Chrome container                                         |
| `codefreedom tools chrome restart`                  | Restart Chrome container (preserves state, no image pull)     |
| `codefreedom tools chrome status`                   | Show Chrome container status                                  |
| `codefreedom tools chrome url`                      | Print CDP debug URL for agent connection                      |
| `codefreedom tools web init`                        | Initialize Camoufox tool profile (requires acceptance)        |
| `codefreedom tools web start`                       | Start Camoufox container (MCP server on port 8420)            |
| `codefreedom tools web stop`                        | Stop Camoufox container                                       |
| `codefreedom tools web restart`                     | Restart Camoufox container (preserves state, no image pull)   |
| `codefreedom tools web status`                      | Show Camoufox container status                                |
| `cf cc`                                             | Alias for `codefreedom claude`                                |
| `cf px`                                             | Alias for `codefreedom proxy`                                 |
| `cf adm`                                            | Alias for `codefreedom admin`                                 |

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

### Tool Profiles (`~/.codefreedom/profiles/<tool>.json`)

Tools (chrome browser, web/camoufox) load settings from `~/.codefreedom/profiles/<tool>.json`.
Generated by `codefreedom tools <tool> init` from bundled `src/codefreedom/examples/tools/<tool>/`.
Tool init requires user acceptance (typing "I understand"). Tools refuse to start without successful init.

| Setting          | Default                               | Profile override                                                                                                                       |
| ---------------- | ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `image`          | `codefreedom:chrome`                  | Change to `docker.io/nilayparikh/codefreedom:chrome-latest` for published builds (also on `ghcr.io/nilayparikh/codefreedom` as mirror) |
| `container_name` | `codefreedom-tools-chrome`            | Custom container name                                                                                                                  |
| `port`           | `9222`                                | CDP debug port                                                                                                                         |
| `data_dir`       | `~/.codefreedom/sandbox/tools/chrome` | Persistent data mount                                                                                                                  |
| `env`            | `DISPLAY=:99`                         | Extra env vars forwarded to container                                                                                                  |

- All other profiles inherit from `default`. Profile's own `env` merges on top.
- Mode-specific overrides (`sandbox.env`, `local.env`) also inherit: custom profile gets `default`'s mode env first, then its own.

### Environment Variable Chain

Component-specific env files are loaded only for the matching subcommand. Shared
and workspace env files are loaded for all components.

**codefreedom claude** (7 layers, lowest to highest):

1. `~/.codefreedom/.env.claude` — Claude Code config (skips if missing)
2. `~/.codefreedom/.env.claude.secrets` — Claude Code secrets (skips if missing)
3. `~/.codefreedom/.env` — shared config (skips if missing)
4. `~/.codefreedom/.env.secrets` — shared secrets (skips if missing)
5. `{workspace}/.env` — workspace overrides (skips if missing)
6. `{workspace}/.env.secrets` — workspace secrets (skips if missing)
7. `os.environ` — system env (always wins)

**codefreedom proxy** (7 layers):

1. `~/.codefreedom/.env.proxy` — proxy config (skips if missing)
2. `~/.codefreedom/.env.proxy.secrets` — proxy secrets (skips if missing)
3. `~/.codefreedom/.env` — shared config (skips if missing)
4. `~/.codefreedom/.env.secrets` — shared secrets (skips if missing)
5. `{workspace}/.env` — workspace overrides (skips if missing)
6. `{workspace}/.env.secrets` — workspace secrets (skips if missing)
7. `os.environ` — system env (always wins)

**codefreedom tools** (chrome, web, etc.) — 5 layers:

1. `~/.codefreedom/.env` — shared config (skips if missing)
2. `~/.codefreedom/.env.secrets` — shared secrets (skips if missing)
3. `{workspace}/.env` — workspace overrides (skips if missing)
4. `{workspace}/.env.secrets` — workspace secrets (skips if missing)
5. `os.environ` — system env (always wins)

All layers support `${VAR}` and `${VAR:-default}` interpolation. **Empty-string env vars are valid overrides** (`export FOO=""` does NOT fall through to defaults).

### Version Source of Truth

Only `pyproject.toml` holds the version. `__init__.py` derives `__version__` from `importlib.metadata` — never edit it directly.

### Proxy System

- LiteLLM instance routing model requests to providers (DeepSeek, Azure Foundry, NVIDIA, local).
- Default: **stateless** (no database). Optional PostgreSQL unlocks Admin UI, spend tracking.
- Provider config: `~/.codefreedom/proxy/config/providers/*.yaml` — opt-in via API key env vars.
- Model aliases controlled by env vars: `LITELLM_MODEL_ALIAS_ULTRA`, `LITELLM_MODEL_ALIAS_PRO`, `LITELLM_MODEL_ALIAS_FLASH`, `LITELLM_MODEL_ALIAS_AIR`.

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

Four image families in `docker/` published to `docker.io/nilayparikh/codefreedom` (also available on `ghcr.io/nilayparikh/codefreedom` as a mirror):

| Image      | Dockerfile                             | Use Case                                                           |
| ---------- | -------------------------------------- | ------------------------------------------------------------------ |
| **CUDA**   | `docker/claude-code/Dockerfile.CUDA`   | NVIDIA GPU workloads                                               |
| **ROCm**   | `docker/claude-code/Dockerfile.ROCm`   | AMD GPU workloads                                                  |
| **Ubuntu** | `docker/claude-code/Dockerfile.Ubuntu` | CPU-only / general-purpose                                         |
| **Chrome** | `docker/chrome/Dockerfile.Chrome`      | Xvfb + Chromium for undetectable headed browsing via CDP port 9222 |
| **Web**    | `docker/web/Dockerfile.Web`            | Camoufox MCP server for stealth web search and scraping            |

Images are built and published via `publish-docker.yml` GitHub Actions workflow on `v*` tags.

## CI/CD

| Workflow               | Trigger        | Purpose                                                  |
| ---------------------- | -------------- | -------------------------------------------------------- |
| `integration-test.yml` | push/PR        | Tests on Python 3.10/11/12 across Ubuntu, Windows, macOS |
| `publish-docker.yml`   | `v*` tags      | Build & publish CUDA, ROCm, Ubuntu images to `ghcr.io`   |
| `pipy.yaml`            | `v*` tags      | Publish to PyPI                                          |
| `publish-docs.yml`     | push to `main` | Build MkDocs site, deploy to GitHub Pages                |
| `trivy.yml`            | push/PR        | Security scanning with Trivy                             |

## Tests

Eight test modules in `tests/`, all using `pytest` with `tmp_path` fixtures and `monkeypatch` for path isolation — never touching real `~/.codefreedom/` during tests.

| File                   | Coverage                                                              |
| ---------------------- | --------------------------------------------------------------------- |
| `test_admin.py`        | Backup, restore, list, inspect, prune, sha256, categorization         |
| `test_env_loader.py`   | `.env` parsing, component-aware chain precedence, `${VAR}` resolution |
| `test_profiles.py`     | Profile loading, inheritance, env resolution                          |
| `test_proxy.py`        | Path resolution, config validation, Docker Compose discovery          |
| `test_init_claude.py`  | Claude `--init` bootstrap, file creation, skip/force logic            |
| `test_init_proxy.py`   | Proxy `--init` bootstrap, file creation, skip/force logic             |
| `test_docker_utils.py` | Docker container lifecycle helpers (start/stop/status)                |
| `test_init_utils.py`   | Bundled examples resolution, all-or-nothing file copy                 |

CI runs tests on Python 3.10/11/12 across Ubuntu, Windows, and macOS via `integration-test.yml`.

## Gotchas

### parse_known_args rescue pattern

When an unknown flag appears **before** a known flag, `parse_known_args` puts ALL remaining args into the unknown list. The `_CLAUDE_BOOL_FLAGS` dict in `main.py` rescues CodeFreedom flags. **If you add a new boolean flag to the claude subcommand, add it to `_CLAUDE_BOOL_FLAGS` too.**

### `eprint` duplication

`eprint` is intentionally duplicated in `env_loader.py` and `profiles.py` to avoid circular imports. Don't consolidate.

### `--dangerously-skip-permissions`

Sandbox mode **always** passes this to Claude CLI inside the container. Local mode only passes it if the user explicitly requests it.

### Unicode in output strings breaks Windows CI

Windows terminal defaults to cp1252 encoding, which cannot encode Unicode box-drawing characters (`─`, `◆`, `★`, etc.). Any `print()` or string that uses these characters will cause a `UnicodeEncodeError` on Windows.

**Always use plain ASCII in user-facing strings** — replace `───` with `---`, `◆` with `*`, etc.
Affected files: `src/codefreedom/cli/claude.py`, `proxy.py`, `tool_init_utils.py` (the `_NOTICE`/`_NON_DISCLAIMER` variables).

### Top-level `--init` must stay in sync with CI

The integration test (`.github/workflows/integration-test.yml`) runs `codefreedom --init` to bootstrap all config files. The handler lives in `src/codefreedom/cli/main.py` before subcommand dispatch. Init is all-or-nothing: if any target file already exists, it skips and directs the user to docs/examples for manual merging.

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
