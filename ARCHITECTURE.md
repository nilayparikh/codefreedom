# Building Blocks

Architecture map. Every module, its responsibility, and how they wire together.

## Layer Model

```text
User (CLI)
  |
cli/          -- command dispatch, user-facing logic
  |
core/         -- env, profiles, config, interpolation
  |             core/settings.py is the configuration owner
sandbox/      -- container lifecycle, signals, terminal
docker/       -- Docker client helpers
tools/        -- tool classes, MCP endpoint dispatch
  |
infra/        -- Docker images, proxy config, recipes
```

Each layer calls only the layer below it. No cross-layer or sideways calls.

## Component Inventory

### Core (leaf modules — no intra-package imports)

| Block           | File                                      | Responsibility                                                        |
| --------------- | ----------------------------------------- | --------------------------------------------------------------------- |
| `config`        | `src/codefreedom/core/config.py`          | `CODEFREEDOM_HOME` path, `resolve_agent_config()` single entry point  |
| `settings`      | `src/codefreedom/core/settings.py`        | Common runtime config and secret resolution seam, typed settings, provenance |
| `env_loader`    | `src/codefreedom/env_loader.py`           | 9-layer `.env` chain, `eprint()`                                      |
| `interpolate`   | `src/codefreedom/core/interpolate.py`     | `${VAR}` interpolation                                                 |
| `log`           | `src/codefreedom/log.py`                  | `tag()`, colored output, shared logging                                |
| `profiles`      | `src/codefreedom/core/profiles.py`        | Profile YAML loading, `load_profile_env()`, tool profile resolution    |
| `http_client`   | `src/codefreedom/core/http_client.py`     | Shared HTTP client utilities                                           |
| `schemas`       | `src/codefreedom/schemas/`                | Pydantic models for profiles, recipes                                  |

### CLI (subcommands + shared utilities)

| Block             | File                                        | Responsibility                                                                  |
| ----------------- | ------------------------------------------- | ------------------------------------------------------------------------------- |
| `main`            | `src/codefreedom/cli/main.py`               | Top-level parser, dispatches to `setup`/`run`/`manage` subcommands              |
| `common`          | `src/codefreedom/cli/common.py`             | Shared CLI utilities (argument parsing, profile loading, output helpers)        |
| `formatter`       | `src/codefreedom/cli/formatter.py`          | Help text formatting                                                            |
| **setup**         |                                             |                                                                                 |
| `recipe`          | `src/codefreedom/cli/setup/recipe.py`       | `cf setup init` — plan, apply, list recipes                                      |
| `config_setup`    | `src/codefreedom/cli/setup/config.py`       | `cf setup config vscode` — VS Code chatLanguageModels.json generation           |
| `deinit`          | `src/codefreedom/cli/setup/deinit.py`       | `cf setup deinit` — teardown, stop containers, remove config                    |
| **run**           |                                             |                                                                                 |
| `agent`           | `src/codefreedom/cli/run/agent.py`          | Agent dispatch: alias resolution, `get_agent_names()`, `validate_agent_args()`  |
| `claude`          | `src/codefreedom/cli/claude.py`             | `cf run agent claude-code` — init, profiles, sandbox/native launch              |
| `mimo`            | `src/codefreedom/cli/mimo.py`               | `cf run agent mimo-code` — 0-click proxy config, sandbox/native                 |
| `opencode`        | `src/codefreedom/cli/opencode.py`           | `cf run agent open-code` — 0-click proxy config, sandbox/native                 |
| `proxy`           | `src/codefreedom/cli/run/proxy.py`          | `cf run proxy` — start/stop/status/validate via Docker Compose                  |
| `tools`           | `src/codefreedom/cli/run/tools.py`          | `cf run tools` — CLI layer delegates to `tools/registry.py`                     |
| `docker_utils`    | `src/codefreedom/cli/docker_utils.py`       | `start_tool_container()`, image checks, tool metadata                           |
| `vscode`          | `src/codefreedom/cli/vscode.py`             | VS Code agent config generation helpers                                         |
| **manage**        |                                             |                                                                                 |
| `doctor`          | `src/codefreedom/cli/manage/doctor.py`      | `cf manage doctor` — profile-aware env checks, agent binary checks              |
| `update`          | `src/codefreedom/cli/manage/update.py`      | Docker image + PyPI update checks                                               |
| `admin`           | `src/codefreedom/cli/manage/admin.py`       | `cf manage admin` CLI entry point (backup/restore/prune/inspect)                |

### Sandbox (container lifecycle)

| Block           | File                                        | Responsibility                                                                |
| --------------- | ------------------------------------------- | ----------------------------------------------------------------------------- |
| `launcher`      | `src/codefreedom/sandbox/launcher.py`       | `run_sandbox()`, `sandbox_status()`, `sandbox_stop()` — canonical container owner |
| `signals`       | `src/codefreedom/sandbox/signals.py`        | Signal forwarding for sandbox processes                                       |
| `terminal`      | `src/codefreedom/sandbox/terminal.py`       | Terminal allocation for interactive sandbox sessions                           |

### Tools (MCP endpoint dispatch)

| Block           | File                                        | Responsibility                                                                |
| --------------- | ------------------------------------------- | ----------------------------------------------------------------------------- |
| `registry`      | `src/codefreedom/tools/registry.py`         | `acquire_tools()`, `release_tools()`, `start_all_tools()`, `stop_all_tools()` |
| `chrome`        | `src/codefreedom/tools/chrome.py`           | Chrome MCP tool — `mcp_endpoint`, `mcp_server_name`                           |
| `web`           | `src/codefreedom/tools/web.py`              | Camoufox MCP tool                                                             |
| `web_bridge`    | `src/codefreedom/tools/web_bridge.py`       | Web bridge tool                                                               |
| `github`        | `src/codefreedom/tools/github.py`           | GitHub MCP tool                                                               |
| `schemas/`      | `src/codefreedom/tools/schemas/`            | Per-tool Pydantic schemas                                                     |

### Agents (VS Code config generation)

| Block           | File                                        | Responsibility                                                                |
| --------------- | ------------------------------------------- | ----------------------------------------------------------------------------- |
| `claude_settings`| `src/codefreedom/agents/vscode/claude_settings.py` | Claude Code VS Code settings generation                            |
| `proxy_models`  | `src/codefreedom/agents/vscode/proxy_models.py`   | Proxy model list for VS Code config                               |

### Recipe System

| Block           | File                                        | Responsibility                                                                |
| --------------- | ------------------------------------------- | ----------------------------------------------------------------------------- |
| `store`         | `src/codefreedom/recipe/store.py`           | Git clone/update of recipe repository                                         |
| `plan`          | `src/codefreedom/recipe/plan.py`            | Recipe plan generation, secrets status, `_find_env_secrets_targets()`          |
| `merge`         | `src/codefreedom/recipe/merge.py`           | File merge logic for recipe application                                       |
| `apply`         | `src/codefreedom/recipe/apply.py`           | `_print_summary()`, `_resolve_secret()`, apply execution                      |

### Admin (backup/restore)

| Block           | File                                        | Responsibility                                                                |
| --------------- | ------------------------------------------- | ----------------------------------------------------------------------------- |
| `backup`        | `src/codefreedom/admin/backup.py`           | Archive creation, PG dump                                                     |
| `restore`       | `src/codefreedom/admin/restore.py`          | Archive extraction, diff preview                                              |
| `prune`         | `src/codefreedom/admin/prune.py`            | Old backup removal                                                            |
| `_utils`        | `src/codefreedom/admin/_utils.py`           | `_MANAGED_PATHS`, `_collect_files()`, `_redact_value()`                       |

### Docker (client helpers)

| Block           | File                                        | Responsibility                                                                |
| --------------- | ------------------------------------------- | ----------------------------------------------------------------------------- |
| `client`        | `src/codefreedom/docker/client.py`          | Docker API client wrapper                                                     |

### Infrastructure (runtime assets)

| Block             | Location                   | Responsibility                                                                  |
| ----------------- | -------------------------- | ------------------------------------------------------------------------------- |
| `docker_images`   | `docker/`                  | CUDA, ROCm, Ubuntu, Chrome, Camoufox, LiteLLM, GitHub, Web, Web-Bridge images  |
| `litellm`         | `docker/litellm/`          | Self-contained LiteLLM proxy image with embedded PostgreSQL                     |
| `litellm_patches` | `docker/litellm/patches/`  | Build-time patches (WebSearch count, Azure responses disable)                   |
| `litellm_plugins` | `docker/litellm/plugins/`  | Reasoning-efforts mapping baked into image                                      |
| `web-bridge`      | `docker/web-bridge/`       | FastAPI sidecar — SearXNG → Camoufox MCP translation                           |
| `proxy_config`    | `~/.codefreedom/proxy/`    | LiteLLM routing, provider YAML, model aliases, plugin configs                   |
| `recipes`         | `recipes/`                 | Configuration recipes from github.com/nilayparikh/codefreedom-recipes           |

## Dependency Graph

```text
core/config.py, core/profiles.py, core/interpolate.py, env_loader.py, log.py  (leaf — no intra-package deps)
  |
cli/docker_utils.py                                                          (log only)
  |
sandbox/launcher.py                                                          (log, docker/client)
  |
cli/main.py                                                                  -> log
cli/claude.py                                                                -> core/settings, log, profiles, tool_registry, sandbox/launcher
cli/mimo.py                                                                  -> core/settings, log, profiles, tool_registry, sandbox/launcher
cli/opencode.py                                                              -> core/settings, log, profiles, tool_registry, sandbox/launcher
cli/run/agent.py                                                             -> log (dynamic import of agent modules)
cli/run/tools.py                                                             -> log, tools/registry (delegates lifecycle)
cli/run/proxy.py                                                             -> core/config, log, env_loader
cli/vscode.py                                                                -> core/config, log, agents/vscode
cli/manage/doctor.py                                                         -> core/config, log, docker_utils, core/profiles
tools/registry.py                                                            -> log, tools/*, docker/client
recipe/apply.py                                                              -> core/settings, recipe/merge
recipe/plan.py                                                               -> core/config, recipe/store

## Common Module Rule

`src/codefreedom/core/settings.py` is the common module for runtime configuration and secrets.

- Runtime commands should resolve configuration and secrets through that module.
- `src/codefreedom/env_loader.py` remains the low-level source loader, not an alternate consumer seam.
- Recipe files in `codefreedom-recipes` remain declarative inputs and must not introduce separate configuration or secret-handling logic.
```

## Request Flow

### `cf run agent claude-code --sandbox`

```text
main.py (parse)
  -> agent.py (resolve alias 'cc' -> 'claude-code', dispatch to claude.py)
    -> claude.py (load profile, resolve sandbox image, acquire tools)
      -> profiles.py (load_profiles, load_profile_env)
      -> tool_registry.py (acquire_tools: start Docker tool containers)
      -> sandbox/launcher.py (run_sandbox: create container, exec Claude CLI)
        -> core/config.py (get_codefreedom_dir for volume mounts)
      -> tool_registry.py (release_tools)
```

### `cf run proxy start`

```text
main.py (parse)
  -> proxy.py (_start_compose: Docker Compose only)
    -> core/config.py (get_codefreedom_dir for proxy path)
    -> env_loader.py (load_dotenv for proxy env files)
    -> docker compose up -d starts:
       - litellm (:4000)    — codefreedom:litellm-latest (embedded PG, plugins)
       - web-bridge (:8500) — codefreedom:web-bridge -> Camoufox MCP
```

### `cf run tools start -c -w`

```text
main.py (parse)
  -> tools.py (parse tool flags, delegate to registry)
    -> registry.py (start_all_tools: start Chrome + Web containers)
      -> docker/client.py (Docker API calls)
```

### `cf setup init -pa costeffective-coding`

```text
main.py (parse)
  -> recipe.py (init_recipe)
    -> store.py (_ensure_store: git clone/update recipes)
    -> plan.py (plan_recipe: generate patch manifest, check secrets)
    -> user confirms
    -> apply.py (apply_recipe: merge files, validate secrets via _resolve_secret)
      -> _resolve_secret: CF_CLI_* -> os.environ -> .env.user -> .env.*.secrets
```

## Rules

- **One responsibility per block.** If a file does two things, split it.
- **Add a block when shared across 2+ locations.** One-off logic stays inline.
- **Layer discipline.** CLI calls core. Core calls nothing above it. Infra is data.
- **Keep this file accurate.** When code changes, update the inventory and graph in the same PR.

## Tool Registry Design

Tools declared in profiles (`"tools": ["chrome", "web"]`) are auto-managed.
The tool registry (`tools/registry.py`) is the **canonical owner** of tool lifecycle.

### Ownership

- **`tools/registry.py`** — acquire/release, session tracking, MCP endpoint resolution, bulk lifecycle (`start_all_tools`, `stop_all_tools`)
- **`cli/run/tools.py`** — CLI layer: parsing, output, delegates to registry
- **`cli/docker_utils.py`** — Docker primitives (`container_is_running`, `ensure_image`)

### Lifecycle

1. **`cf run agent claude-code` starts** — `acquire_tools()`: start containers, return acquired tools
2. **Agent session runs** — tools stay running independently
3. **Agent exits** — `release_tools()` in finally block (no-op, tools persist)
4. **`cf run tools stop`** — explicit stop via `stop_all_tools()`

### First-one-starts, last-one-stops

| Session A | Session B | Chrome State            |
| --------- | --------- | ----------------------- |
| starts    | —         | started (ref=1)         |
| running   | starts    | already running (ref=2) |
| exits     | running   | stays running (ref=1)   |
| —         | exits     | stopped (ref=0)         |
