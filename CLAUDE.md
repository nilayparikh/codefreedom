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
├── cli/
│   ├── main.py      # Top-level parser, --init, dispatches to subcommands
│   ├── claude.py    # 'codefreedom claude' — profile loading, run dispatch
│   ├── chrome.py    # 'codefreedom tools chrome' — Chrome browser container
│   └── proxy.py     # 'codefreedom proxy' — lifecycle (up/down/status)
├── profiles.py      # Profile JSON loading, ${VAR} resolution, inheritance
├── launcher.py      # Docker sandbox and native local execution
├── env_loader.py    # .env chain: ~/.codefreedom → machine env
└── examples/        # Bundled into package, copied by --init
    ├── .env.example, .env.secrets.example
    ├── profiles/    # JSON profiles + schema + tool profiles (tools-*.json)
    └── proxy/       # config.yaml, docker-compose.yaml, providers/*.yaml
```

Entry points: `codefreedom` / `cf` → `src/codefreedom/cli/main.py:main`

### CLI Commands

| Command                                             | Description                                       |
| --------------------------------------------------- | ------------------------------------------------- |
| `codefreedom --init`                                | Bootstrap `~/.codefreedom/` from bundled examples |
| `codefreedom --init --force`                        | Force re-create even if already initialized       |
| `codefreedom claude`                                | Launch Claude Code (alias: `cf cc`)               |
| `codefreedom claude --sandbox`                      | Launch in Docker container with GPU               |
| `codefreedom claude --native-models`                | Bypass proxy, use Anthropic `/login`              |
| `codefreedom claude --list-profiles`                | List available profiles                           |
| `codefreedom claude --stop`                         | Stop running sandbox containers                   |
| `codefreedom claude --status`                       | Show sandbox container status                     |
| `codefreedom claude --dangerously-skip-permissions` | Skip permission prompts (local mode)              |
| `codefreedom proxy --up`                            | Start LiteLLM proxy (native Python)               |
| `codefreedom proxy --up --docker`                   | Start via Docker Compose                          |
| `codefreedom proxy --down`                          | Stop proxy                                        |
| `codefreedom proxy --status`                        | Show proxy status                                 |
| `codefreedom proxy --validate`                      | Validate proxy config                             |
| `codefreedom proxy --port PORT`                     | Set proxy port (default: 4000)                    |
| `codefreedom proxy --host HOST`                     | Set bind host (default: 0.0.0.0)                  |
| `cf cc`                                             | Alias for `codefreedom claude`                    |
| `cf px`                                             | Alias for `codefreedom proxy`                     |
| `codefreedom tools chrome start`                    | Start Chrome browser container (Xvfb + Chromium)  |
| `codefreedom tools chrome stop`                     | Stop Chrome container                             |
| `codefreedom tools chrome status`                   | Show Chrome container status                      |
| `codefreedom tools chrome url`                      | Print CDP debug URL for agent connection          |
| `codefreedom --init`                                | Also copies `tools-chrome.json` → `chrome.json`   |

## Key Patterns

### Profile Inheritance

### Claude Code Profiles (`profiles.json`)

- `default` and `bare` are **standalone** — no inheritance.

### Tool Profiles (`~/.codefreedom/profiles/chrome.json`)

Tools (chrome browser, etc.) load settings from `~/.codefreedom/profiles/<tool>.json`.
Generated by `codefreedom --init` from bundled `src/codefreedom/examples/profiles/tools-*.json`.

| Setting          | Default                               | Profile override                                                               |
| ---------------- | ------------------------------------- | ------------------------------------------------------------------------------ |
| `image`          | `codefreedom:Chrome-local`            | Change to `ghcr.io/nilayparikh/codefreedom:Chrome-latest` for published builds |
| `container_name` | `codefreedom-chrome`                  | Custom container name                                                          |
| `port`           | `9222`                                | CDP debug port                                                                 |
| `data_dir`       | `~/.codefreedom/sandbox/tools/chrome` | Persistent data mount                                                          |
| `env`            | `DISPLAY=:99`                         | Extra env vars forwarded to container                                          |

- All other profiles inherit from `default`. Profile's own `env` merges on top.
- Mode-specific overrides (`sandbox.env`, `local.env`) also inherit: custom profile gets `default`'s mode env first, then its own.

### Environment Variable Chain (5 layers, lowest to highest)

1. `~/.codefreedom/.env` — primary config (warns if missing)
2. `~/.codefreedom/.env.secrets` — API keys (skips if missing)
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
- `sandbox_image` fallback chain: profile → `default` → env vars (`CLAUDE_CODE_REGISTRY/IMAGE_NAME/IMAGE_TAG`) → hardcoded default.

## Docker

Four image families in `docker/` published to `ghcr.io/nilayparikh/codefreedom`:

| Image      | Dockerfile                             | Use Case                                                           |
| ---------- | -------------------------------------- | ------------------------------------------------------------------ |
| **CUDA**   | `docker/claude-code/Dockerfile.CUDA`   | NVIDIA GPU workloads                                               |
| **ROCm**   | `docker/claude-code/Dockerfile.ROCm`   | AMD GPU workloads                                                  |
| **Ubuntu** | `docker/claude-code/Dockerfile.Ubuntu` | CPU-only / general-purpose                                         |
| **Chrome** | `docker/browser/Dockerfile.Chrome`     | Xvfb + Chromium for undetectable headed browsing via CDP port 9222 |

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

Four test modules in `tests/`, all using `pytest` with `tmp_path` fixtures and `monkeypatch` for path isolation — never touching real `~/.codefreedom/` during tests.

| File                 | Coverage                                                      |
| -------------------- | ------------------------------------------------------------- |
| `test_env_loader.py` | `.env` parsing, 5-layer chain precedence, `${VAR}` resolution |
| `test_profiles.py`   | Profile loading, inheritance, env resolution                  |
| `test_proxy.py`      | Path resolution, config validation, Docker Compose discovery  |
| `test_init.py`       | `--init` bootstrap, file creation, skip/force logic           |

CI runs tests on Python 3.10/11/12 across Ubuntu, Windows, and macOS via `integration-test.yml`.

## Gotchas

### parse_known_args rescue pattern

When an unknown flag appears **before** a known flag, `parse_known_args` puts ALL remaining args into the unknown list. The `_CLAUDE_BOOL_FLAGS` dict in `main.py` rescues CodeFreedom flags. **If you add a new boolean flag to the claude subcommand, add it to `_CLAUDE_BOOL_FLAGS` too.**

### `eprint` duplication

`eprint` is intentionally duplicated in `env_loader.py` and `profiles.py` to avoid circular imports. Don't consolidate.

### `--dangerously-skip-permissions`

Sandbox mode **always** passes this to Claude CLI inside the container. Local mode only passes it if the user explicitly requests it.

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
