# Key Patterns

Internal patterns and conventions used throughout the CodeFreedom codebase.

## 1. Profile Inheritance

- `default` and `bare` are **standalone** — no inheritance.
- All other profiles inherit from `default`. Profile's own `env` merges on top.
- Mode-specific overrides (`sandbox.env`, `local.env`) also inherit.
- **`tools` field** (`"tools": ["chrome", "web"]`): declares tool containers to auto-start. First session starts them, last session stops them.

## 2. Environment Variable Chain

No `.env` files. All configuration comes from YAML + `CF_CLI_*` env vars.

**Resolution order (lowest → highest):**

1. `profiles.yaml` — recipe-managed defaults with `${VAR:-default}`
2. `recipe.yaml` — recipe vars (override profiles)
3. `override.yaml` — user overrides (same schema)
4. `CF_CLI_*` — secrets from machine env (prefix stripped, highest priority)

`${VAR}` interpolation happens at runtime on every `load_config()` call. Files are stored with literal `${VAR}` placeholders — no install-time baking. Empty-string values in `CF_CLI_*` are valid overrides (do NOT fall through to default).

### Common Module Rule

- `config/loader.py` owns the single `load_config()` entry point.
- `config/interpolation.py` owns `resolve_var()`, `resolve_dict()`, `interpolate_all()`.
- `config/models.py` owns Pydantic schema (`ConfigModel`, `ProfileEntry`, etc.).
- CLI commands, VS Code helpers, recipe code, and diagnostics must not implement separate config or secret precedence rules.
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

- `config/loader.py` is the single source of truth — `load_config()` loads all configuration.
- `config/models.py` owns the unified schema (`ConfigModel`, `ProfileEntry`, `AgentDefinition`).
- `config/interpolation.py` owns `${VAR}` resolution — single pass, runtime only.
- Recipes declare `vars:` (dynamic key-value pairs) and `required_secrets` / `config_vars`.
- No `.env` files — secrets come exclusively from `CF_CLI_*` machine env vars.
- `override.yaml` mirrors the full `profiles.yaml` schema — any value can be overridden, not just `env`.

## 7. Version Source of Truth

Only `pyproject.toml` holds the version. `__init__.py` derives `__version__` from `importlib.metadata` — never edit it directly.
