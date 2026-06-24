# Key Patterns

Internal patterns and conventions used throughout the CodeFreedom codebase.

## 1. Profile Inheritance

- `default` and `bare` are **standalone** — no inheritance.
- All other profiles inherit from `default`. Profile's own `env` merges on top.
- Mode-specific overrides (`sandbox.env`, `local.env`) also inherit.
- **`tools` field** (`"tools": ["chrome", "web"]`): declares tool containers to auto-start. First session starts them, last session stops them.

## 2. Environment Variable Chain

Component-specific env files are loaded only for the matching subcommand.

The project goal is that **all configuration and secret resolution flows through one common module**. Runtime consumers should resolve values through `src/codefreedom/core/settings.py` and `src/codefreedom/env_loader.py` rather than implementing their own precedence logic.

**Priority (lowest to highest):**

1. Component config (`.env.claude` / `.env.proxy`)
2. Shared config (`.env`)
3. Workspace config (`{workspace}/.env`)
4. Component secrets (`.env.claude.secrets` / `.env.proxy.secrets`)
5. Shared secrets (`.env.secrets`)
6. Workspace secrets (`{workspace}/.env.secrets`)
7. User overrides (`.env.user`)
8. System env (`os.environ`)
9. `CF_CLI_*` overrides (absolute highest)

All layers support `${VAR}` and `${VAR:-default}` interpolation. **Empty-string env vars are valid overrides.**

### Common Module Rule

- `src/codefreedom/core/settings.py` owns runtime configuration and secret resolution seams.
- `src/codefreedom/env_loader.py` is the low-level loader used by that seam.
- CLI commands, VS Code helpers, recipe summary code, and diagnostics must not implement separate config or secret precedence rules.
- Recipes declare metadata and presets only; they do not define independent configuration logic.

## 3. Tools are Shared Infrastructure

Tools (chrome, web, github, web-bridge) are **shared** — once started they keep running until explicitly stopped. Container names are **static** (from profile). All sessions share the same tool container.

1. First `cf run agent claude-code` or `cf run tools start` creates the container.
2. Subsequent invocations detect it's already running and are no-ops.
3. `cf run tools stop` is the only way to stop it.

| Tool | Env var | Default |
| --- | --- | --- |
| Chrome | `CODEFREEDOM_CHROME_PORT` | `9222` |
| Web | `CODEFREEDOM_WEB_PORT` | `8420` |
| GitHub | `CODEFREEDOM_GITHUB_PORT` | `0` (auto) |
| Web-bridge | `CODEFREEDOM_WEB_BRIDGE_PORT` | `8500` |

## 4. Proxy System

- LiteLLM instance routing model requests to providers.
- Default: **stateless** (no database). Optional PostgreSQL unlocks Admin UI.
- Provider config: `~/.codefreedom/proxy/config/providers/*.yaml`
- **Docker-only** — no native mode, no `litellm` extra in `pyproject.toml`.

## 5. Sandbox Containers

- Ephemeral: `codefreedom-XXXX` (random 4-hex name), auto-removed on exit.
- Pattern: container runs `sleep infinity`; agent is `docker exec`'d into it.
- Volume mounts: workspace (rw), `~/.gitconfig` (ro), `~/.ssh` (ro).

## 6. Configuration Management

- `core/settings.py` is the single source of truth for runtime configuration.
- Recipes declare metadata and `generated_artifacts`; CodeFreedom generates setup scripts, env templates, and summary metadata at install time.
- Generated artifacts replace static script files — recipes no longer ship hardcoded setup scripts.
- Static script files in recipes remain as fallback during migration; once all recipes declare `generated_artifacts`, static copies will be removed.

## 7. Version Source of Truth

Only `pyproject.toml` holds the version. `__init__.py` derives `__version__` from `importlib.metadata` — never edit it directly.
