# Key Patterns

Internal patterns and conventions used throughout the CodeFreedom codebase.

## 1. Profile Inheritance

- `default` and `bare` are **standalone** — no inheritance.
- All other profiles inherit from `default`. Profile's own `env` merges on top.
- Mode-specific overrides (`sandbox.env`, `local.env`) also inherit.
- **`tools` field** (`"tools": ["chrome", "web"]`): declares tool containers to auto-start. First session starts them, last session stops them.

## 2. Environment Variable Chain

Component-specific env files are loaded only for the matching subcommand.

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

## 3. Tools are Shared Infrastructure

Tools (chrome, web, github, web-bridge) are **shared** — once started they keep running until explicitly stopped. Container names are **static** (from profile). All sessions share the same tool container.

1. First `cf agent claude` or `cf tools start` creates the container.
2. Subsequent invocations detect it's already running and are no-ops.
3. `cf tools stop` is the only way to stop it.

| Tool | Env var | Default |
|------|---------|---------|
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

## 6. Version Source of Truth

Only `pyproject.toml` holds the version. `__init__.py` derives `__version__` from `importlib.metadata` — never edit it directly.
