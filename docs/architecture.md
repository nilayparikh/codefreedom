# Architecture

Internal design: layer model, component inventory, dependency graph, and request flows.

## Layer Model

```text
User (CLI)
  |
cli/          -- command dispatch, user-facing logic
  |
config/       -- YAML loading, ${VAR} interpolation, schema validation, runtime settings
core/         -- env helpers, container lifecycle, agent runtime, HTTP client
  |
docker/       -- Docker client helpers, image pull utilities
tools/        -- tool classes, MCP endpoint dispatch
  |
recipe/       -- recipe store, plan, merge, apply
admin/        -- backup, restore, prune
```

Each layer calls only the layer below it. No cross-layer or sideways calls.

## Component Inventory

### Core (leaf modules -- no intra-package imports)

| Block | File | Responsibility |
|---|---|---|
| `config` | `src/codefreedom/core/config.py` | `CODEFREEDOM_HOME` path, `resolve_profiles_path()` |
| `http_client` | `src/codefreedom/core/http_client.py` | Shared HTTP client utilities |
| `container` | `src/codefreedom/core/container.py` | Canonical facade for tool lifecycle helpers |
| `agent_runtime` | `src/codefreedom/core/agent_runtime.py` | `detect_proxy_url()`, `fetch_proxy_models()`, `build_provider_models()` |
| `proxy_env` | `src/codefreedom/core/proxy_env.py` | Proxy environment resolution |
| `tool_base` | `src/codefreedom/core/tool_base.py` | Base classes for tool modules |
| `urls` | `src/codefreedom/core/urls.py` | URL constants and helpers |
| `log` | `src/codefreedom/log.py` | `tag()`, `eprint()`, colored output |

### Config (YAML loading, interpolation, schema)

| Block | File | Responsibility |
|---|---|---|
| `config` | `src/codefreedom/config/__init__.py` | Public API: `load_config()`, error types, models |
| `loader` | `src/codefreedom/config/loader.py` | `load_config()`, `ResolvedConfig`, `AgentConfig`, `ToolConfig` |
| `models` | `src/codefreedom/config/models.py` | Pydantic schema: `ConfigModel`, `ProfileEntry`, `AgentDefinition` |
| `interpolation` | `src/codefreedom/config/interpolation.py` | `${VAR}` resolution: `resolve_var()`, `resolve_dict()`, `interpolate_all()` |
| `runtime` | `src/codefreedom/config/runtime.py` | `resolve_agent_runtime()`, `list_profiles()`, `load_profile_env()`, settings |
| `errors` | `src/codefreedom/config/errors.py` | `ConfigError`, `MissingSecretError`, `ProfileError` |
| `display` | `src/codefreedom/config/display.py` | Config display/formatting helpers |
| `yaml_utils` | `src/codefreedom/config/yaml_utils.py` | `safe_load()`, `safe_dump()` |

### CLI (subcommands + shared utilities)

| Block | File | Responsibility |
|---|---|---|
| `main` | `src/codefreedom/cli/main.py` | Top-level parser, dispatches to `setup`/`run`/`manage`/`git` subcommands |
| `common` | `src/codefreedom/cli/common.py` | Shared CLI utilities (argument parsing, profile loading, output helpers) |
| `formatter` | `src/codefreedom/cli/formatter.py` | Help text formatting |
| `project_config` | `src/codefreedom/cli/project_config.py` | Project-level config helpers |
| **setup** | | |
| `recipe` | `src/codefreedom/cli/setup/recipe.py` | `cf setup init` -- re-exports from `recipe/` package |
| `config_setup` | `src/codefreedom/cli/setup/config.py` | `cf setup config` -- CLI parser and dispatch |
| `deinit` | `src/codefreedom/cli/setup/deinit.py` | `cf setup deinit` -- teardown, stop containers, remove config |
| **run** | | |
| `agent` | `src/codefreedom/cli/run/agent.py` | Agent dispatch: alias resolution, `get_agent_names()`, `validate_agent_args()` |
| `claude` | `src/codefreedom/cli/claude.py` | `cf run agent claude-code` -- init, profiles, launch |
| `mimo` | `src/codefreedom/cli/mimo.py` | `cf run agent mimo-code` -- 0-click proxy config |
| `opencode` | `src/codefreedom/cli/opencode.py` | `cf run agent open-code` -- 0-click proxy config |
| `pi` | `src/codefreedom/cli/pi.py` | `cf run agent pi-code` -- extension-based model discovery, LSP config |
| `codex` | `src/codefreedom/cli/codex.py` | `cf run agent codex-code` -- 0-click proxy config, model catalog generation |
| `proxy` | `src/codefreedom/cli/run/proxy.py` | `cf run proxy` -- start/stop/status/validate via Docker Compose |
| `tools` | `src/codefreedom/cli/run/tools.py` | `cf run tools` -- CLI layer delegates to `tools/registry.py` |
| `docker_utils` | `src/codefreedom/cli/docker_utils.py` | Docker primitives (re-exported via `core/container.py` facade) |
| `vscode` | `src/codefreedom/cli/vscode.py` | VS Code agent config generation helpers |
| **manage** | | |
| `doctor` | `src/codefreedom/cli/manage/doctor.py` | `cf manage doctor` -- profile-aware env checks, agent binary checks |
| `update` | `src/codefreedom/cli/manage/update.py` | Docker image + PyPI update checks |
| `admin` | `src/codefreedom/cli/manage/admin.py` | `cf manage admin` CLI entry point (backup/restore/prune/inspect) |
| **git** | | |
| `git` | `src/codefreedom/cli/git/` | Git workflows: commit messages, PR creation (`cmt`, `pr`, `init`) |

### Tools (MCP endpoint dispatch)

| Block | File | Responsibility |
|---|---|---|
| `registry` | `src/codefreedom/tools/registry.py` | `acquire_tools()`, `release_tools()`, `start_all_tools()`, `stop_all_tools()` |
| `chrome` | `src/codefreedom/tools/chrome.py` | Chrome MCP tool -- `mcp_endpoint`, `mcp_server_name` |
| `web` | `src/codefreedom/tools/web.py` | Camoufox MCP tool |
| `web_bridge` | `src/codefreedom/tools/web_bridge.py` | Web bridge tool |
| `github` | `src/codefreedom/tools/github.py` | GitHub MCP tool |
| `schemas/` | `src/codefreedom/tools/schemas/` | Per-tool Pydantic schemas |

### Agents (VS Code config generation)

| Block | File | Responsibility |
|---|---|---|
| `claude_settings` | `src/codefreedom/agents/vscode/claude_settings.py` | Claude Code VS Code settings generation |
| `proxy_models` | `src/codefreedom/agents/vscode/proxy_models.py` | Proxy model list for VS Code config |

### Recipe System

| Block | File | Responsibility |
|---|---|---|
| `store` | `src/codefreedom/recipe/store.py` | Git clone/update of recipe repository |
| `plan` | `src/codefreedom/recipe/plan.py` | Recipe plan generation, secrets status, `_find_env_secrets_targets()` |
| `merge` | `src/codefreedom/recipe/merge.py` | File merge logic for recipe application |
| `apply` | `src/codefreedom/recipe/apply.py` | `_print_summary()`, `_resolve_secret()`, apply execution |
| `generated_artifacts` | `src/codefreedom/recipe/generated_artifacts.py` | Setup script generation for recipes |
| `materialize` | `src/codefreedom/recipe/materialize.py` | Recipe file materialization and directory creation |

### Admin (backup/restore)

| Block | File | Responsibility |
|---|---|---|
| `backup` | `src/codefreedom/admin/backup.py` | Archive creation, PG dump |
| `restore` | `src/codefreedom/admin/restore.py` | Archive extraction, diff preview |
| `prune` | `src/codefreedom/admin/prune.py` | Old backup removal |
| `_utils` | `src/codefreedom/admin/_utils.py` | `_MANAGED_PATHS`, `_collect_files()`, `_redact_value()` |

### Docker (client helpers)

| Block | File | Responsibility |
|---|---|---|
| `client` | `src/codefreedom/docker/client.py` | Docker API client wrapper |
| `pull` | `src/codefreedom/docker/pull.py` | Image pull, digest comparison, `normalize_ref()`, `parse_image_ref()`, `get_local_digest()` |

### Launcher

| Block | File | Responsibility |
|---|---|---|
| `launcher` | `src/codefreedom/launcher.py` | Docker and native local execution for agents |

### Infrastructure (runtime assets)

| Block | Location | Responsibility |
|---|---|---|
| `docker_images` | `docker/` | Chrome, Camoufox, LiteLLM, GitHub, Web, Web-Bridge images |
| `litellm` | `docker/litellm/` | Self-contained LiteLLM proxy image with embedded PostgreSQL |
| `litellm_patches` | `docker/litellm/patches/` | Build-time patches (WebSearch count, Azure responses disable) |
| `litellm_plugins` | `docker/litellm/plugins/` | Reasoning-efforts mapping baked into image |
| `web-bridge` | `docker/web-bridge/` | FastAPI sidecar -- SearXNG -> Camoufox MCP translation |
| `proxy_config` | `~/.codefreedom/proxy/` | LiteLLM routing, provider YAML, model aliases, plugin configs |
| `recipes` | `recipes/` | Configuration recipes from github.com/nilayparikh/codefreedom-recipes |
| `version` | `version.yaml` | Single source of truth for versioning (`pyproject.toml` is derived at release time) |

## Dependency Graph

```text
core/config.py, core/http_client.py, core/agent_runtime.py, log.py  (leaf -- no intra-package deps)
  |
core/container.py                                                    (re-exports cli/docker_utils.py)
  |
cli/docker_utils.py                                                  (log, core/config)
cli/main.py                                                          -> log
cli/claude.py                                                        -> config/runtime, log, core/config, core/container
cli/mimo.py                                                          -> config/runtime, log, core/config, core/container
cli/opencode.py                                                      -> config/runtime, log, core/config, core/container
cli/pi.py                                                            -> config/runtime, log, core/config, core/container
cli/codex.py                                                         -> config/runtime, log, core/config, core/container
cli/run/agent.py                                                     -> log (dynamic import of agent modules)
cli/run/tools.py                                                     -> log, tools/registry (delegates lifecycle)
cli/run/proxy.py                                                     -> core/config, log, config/runtime
cli/vscode.py                                                        -> core/config, log, agents/vscode
cli/manage/doctor.py                                                 -> core/config, log, core/container, config/runtime
cli/git/                                                             -> log
tools/registry.py                                                    -> log, tools/*
recipe/apply.py                                                      -> config/runtime, recipe/merge
recipe/plan.py                                                       -> core/config, recipe/store
```

## Request Flow

### `cf run proxy start`

```text
main.py (parse)
  -> proxy.py (_start_compose: Docker Compose only)
    -> core/config.py (get_codefreedom_dir for proxy path)
    -> config/runtime.py (load settings)
    -> docker compose up -d starts:
       - litellm (:4000)    -- codefreedom:litellm-latest (embedded PG, plugins)
       - web-bridge (:8500) -- codefreedom:web-bridge -> Camoufox MCP
    -> if proxy.remote_url is set: refuse with "use --local to override"
```

### `cf run tools start -c -w`

```text
main.py (parse)
  -> tools.py (parse tool flags, delegate to registry)
    -> if tool.remote_url is set: skip (log remote URL)
    -> registry.py (start_all_tools: start Chrome + Web containers)
      -> core/container.py (Docker API calls via facade)
```

### `cf setup init -pa costeffective-coding`

```text
main.py (parse)
  -> recipe.py (init_recipe)
    -> store.py (_ensure_store: git clone/update recipes)
    -> plan.py (plan_recipe: generate patch manifest, check secrets)
    -> user confirms
    -> apply.py (apply_recipe: merge files, validate secrets via _resolve_secret)
      -> _resolve_secret: CF_CLI_* -> os.environ (no .env files)
```

## Tool Registry Design

Tools declared in profiles (`"tools": ["chrome", "web"]`) are auto-managed.
The tool registry (`tools/registry.py`) is the **canonical owner** of tool lifecycle.

### Ownership

- **`tools/registry.py`** -- acquire/release, session tracking, MCP endpoint resolution, bulk lifecycle (`start_all_tools`, `stop_all_tools`)
- **`cli/run/tools.py`** -- CLI layer: parsing, output, delegates to registry
- **`core/container.py`** -- canonical facade for Docker primitives (`container_is_running`, `ensure_image`, etc.)

### Lifecycle

1. **`cf run agent claude-code` starts** -- `acquire_tools()`: start containers, return acquired tools
2. **Agent session runs** -- tools stay running independently
3. **Agent exits** -- `release_tools()` in finally block (no-op, tools persist)
4. **`cf run tools stop`** -- explicit stop via `stop_all_tools()`

### First-one-starts, last-one-stops

| Session A | Session B | Chrome State |
|---|---|---|
| starts | -- | started (ref=1) |
| running   | starts | already running (ref=2) |
| exits     | running | stays running (ref=1) |
| --         | exits | stopped (ref=0) |
