# Key Patterns

Internal patterns and conventions used throughout the CodeFreedom codebase.

## 1. Profile Inheritance

- `default` and `bare` are **standalone** — no inheritance.
- All other profiles inherit from `default`. Profile's own `env` merges on top.
- Mode-specific overrides (`local.env`) also inherit.
- **`tools` field** (`"tools": ["chrome", "web"]`): declares tool containers to auto-start. First session starts them, last session stops them.

## 2. Environment Variable Chain

No `.env` files. All configuration comes from YAML + `CF_CLI_*` env vars.

**Resolution order (lowest → highest):**

1. `profiles.yaml` — recipe-managed defaults with `${VAR:-default}`
2. `recipe.yaml` — recipe vars (override profiles)
3. `override.yaml` — user overrides (same schema)
4. `.cf.yaml` — per-folder override (same schema, explicit path; see below)
5. `CF_CLI_*` — secrets from machine env (prefix stripped, highest priority)

`${VAR}` interpolation happens at runtime on every `load_config()` call. Files are stored with literal `${VAR}` placeholders — no install-time baking. Empty-string values in `CF_CLI_*` are valid overrides (do NOT fall through to default).

**Per-folder `.cf.yaml`:** Use `cf s folder <path>` (alias `cf s f`) to copy the current `override.yaml` into `<path>/.cf.yaml`. Same schema as `override.yaml`; sits one layer above it. Default path is the current directory. Activate it by exporting `CF_CLI_CF_YAML=<path>` or by passing `cf_yaml_path=` to `load_config()`. Existing `.cf.yaml` files are preserved by default — pass `--force` to overwrite. The existing block-schema `.cf.yaml` used by the `git` module (`git:` block) is unaffected: it lives in a disjoint top-level key and is read by `cli/git/config.py`, not by `load_config`.

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

Default container names: `codefreedom-chrome`, `codefreedom-web`, `codefreedom-tools-github`, `codefreedom-web-bridge`.

## 4. Proxy System

- LiteLLM instance routing model requests to providers.
- Default: **stateless** (no database). Optional PostgreSQL unlocks Admin UI.
- Provider config: `~/.codefreedom/proxy/config/providers/*.yaml`
- **Docker-only** — no native mode, no `litellm` extra in `pyproject.toml`.
- Default bind address: `0.0.0.0` (all interfaces, remote-accessible).
- Override via `common.bind_address` in `override.yaml` or `CF_CLI_BIND_ADDRESS` env var.
- Remote proxy: set `proxy.remote_url` in `override.yaml` to route clients to a remote proxy.

## 5. Configuration Management

- `config/loader.py` is the single source of truth — `load_config()` loads all configuration.
- `config/models.py` owns the unified schema (`ConfigModel`, `ProfileEntry`, `AgentDefinition`).
- `config/interpolation.py` owns `${VAR}` resolution — single pass, runtime only.
- Recipes declare `vars:` (dynamic key-value pairs) and `required_secrets` / `config_vars`.
- No `.env` files — secrets come exclusively from `CF_CLI_*` machine env vars.
- `override.yaml` mirrors the full `profiles.yaml` schema — any value can be overridden, not just `env`.

## 6. Remote Components

Components (proxy and tools) can be configured as remote:

- **Proxy:** `proxy.remote_url` in `override.yaml` — clients use `PROXY_BASE_URL` from config instead of local detection.
- **Tools:** `tools.<tool>.remote_url` in `override.yaml` — MCP endpoints use the remote URL verbatim.
- **Bind address:** `common.bind_address` controls server-side bind (default `0.0.0.0`). Client-side URL stays `127.0.0.1` for local access.
- When remote, lifecycle commands (`start`/`stop`/`restart`) are refused — use `--local` to override.

## 6. Version Source of Truth

`version.yaml` is the single source of truth for versioning. It holds the base version, dev iteration, and RC number. `pyproject.toml` is derived at release time by CI workflows and should never be edited on branches. `__init__.py` derives `__version__` from `importlib.metadata`.
