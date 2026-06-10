# Building Blocks

Architecture map. Every module, its responsibility, and how they wire together.

## Layer Model

```
User (CLI)
  |
cli/          -- command dispatch, user-facing logic
  |
core/         -- env, profiles, launcher, config
  |
infra/        -- Docker images, proxy config, recipes
```

Three layers. Each layer calls only the layer below it. No cross-layer or sideways calls.

## Component Inventory

### Core (leaf modules — no intra-package imports)

| Block           | File                               | Responsibility                                                        |
| --------------- | ---------------------------------- | --------------------------------------------------------------------- |
| `config`        | `src/codefreedom/config.py`        | `CODEFREEDOM_HOME` path (defaults `~/.codefreedom`)                   |
| `env_loader`    | `src/codefreedom/env_loader.py`    | 9-layer `.env` chain, `${VAR}` interpolation                          |
| `profiles`      | `src/codefreedom/profiles.py`      | Profile JSON, inheritance, env resolution, tools list                 |
| `tool_registry` | `src/codefreedom/tool_registry.py` | Reference-counted tool container lifecycle via `~/.codefreedom/proc/` |

Details on env chain layers and profile inheritance: see `CLAUDE.md` > Key Patterns.

### CLI (subcommands + shared utilities)

| Block             | File                                     | Responsibility                                                                  |
| ----------------- | ---------------------------------------- | ------------------------------------------------------------------------------- |
| `main`            | `src/codefreedom/cli/main.py`            | Top-level parser, dispatches to subcommands                                     |
| `claude`          | `src/codefreedom/cli/claude.py`          | `codefreedom claude` — init, profiles, sandbox/native launch                    |
| `proxy`           | `src/codefreedom/cli/proxy.py`           | `codefreedom proxy` — init, start/stop/status/validate                          |
| `chrome`          | `src/codefreedom/cli/chrome.py`          | `codefreedom tools chrome` — browser container lifecycle                        |
| `web`             | `src/codefreedom/cli/web.py`             | `codefreedom tools web` — Camoufox MCP container lifecycle                      |
| `docker_utils`    | `src/codefreedom/cli/docker_utils.py`    | Shared Docker helpers — container exists/running, ensure image, ephemeral names |
| `recipe`          | `src/codefreedom/cli/recipe.py`          | Recipe system — fetch, plan, and apply configuration recipes                    |
| `tool_init_utils` | `src/codefreedom/cli/tool_init_utils.py` | Tool acceptance gates, notices, tool metadata                                   |
| `admin`           | `src/codefreedom/cli/admin.py`           | `codefreedom admin` — backup/restore/prune                                      |
| `vscode`          | `src/codefreedom/cli/vscode.py`          | `codefreedom vscode` — VS Code config generation (claude, proxy)                |

### Infrastructure (runtime assets)

| Block             | Location                   | Responsibility                                                                  |
| ----------------- | -------------------------- | ------------------------------------------------------------------------------- |
| `docker_images`   | `docker/`                  | CUDA, ROCm, Ubuntu, Chrome, Camoufox, LiteLLM image families                    |
| `web-bridge`      | `docker/web-bridge/`       | FastAPI sidecar — SearXNG → Camoufox MCP translation for WebSearch interception |
| `litellm`         | `docker/litellm/`          | Self-hosted LiteLLM proxy image with embedded PostgreSQL 18.4                   |
| `litellm_patches` | `docker/litellm/patches/`  | Build-time patches applied into the LiteLLM image                               |
| `litellm_plugins` | `docker/litellm/plugins/`  | LiteLLM callbacks baked into the image (reasoning-efforts mapping)              |
| `proxy_config`    | `~/.codefreedom/proxy/`    | LiteLLM routing, provider YAML, model aliases, plugin configs                   |
| `recipes`         | `recipes/`                 | Configuration recipes from github.com/nilayparikh/codefreedom-recipes           |
| `tool_profiles`   | `~/.codefreedom/profiles/` | Per-tool JSON settings (chrome, web)                                            |

**litellm component.** The `docker/litellm/` directory contains a multi-stage Dockerfile (`Dockerfile.LiteLLM`) that builds a self-contained LiteLLM proxy image with embedded PostgreSQL 18.4 (built from source), Prisma schema management, and the WebSearch count display patch. The image installs LiteLLM from a git fork at a pinned tag (default `nilayparikh/litellm.git` at `v1.87.1`) with `--no-deps`, then layers a curated minimal dependency set. Patches in `docker/litellm/patches/` are applied at build time:

- `patch_websearch_count.py` — injects `server_tool_use.web_search_requests` into LiteLLM WebSearch responses so Claude Code TUI displays "Did N searches" (covers short-circuit, typed-plan, and legacy agentic-loop paths).
- `patch_responses_azure.py` — disables LiteLLM's auto-routing of GPT-5.x through the Azure Responses API (Azure Foundry does not reliably serve the Responses API yet).

Plugins in `docker/litellm/plugins/` are baked into the image and deployed by the entrypoint at container start:

- `reasoning_efforts_mapping.py` — v2 CustomLogger that translates reasoning-effort signals across provider standards using rule-based mapping (`mapping` and `thinking_budget` rule types). Reads its config from a YAML file on the host (user-editable).

The entrypoint (`entrypoint.sh`) orchestrates: PG cluster init, `prisma db push`, plugin deployment, and LiteLLM startup. It uses tini as PID 1 for clean signal forwarding. The image runs as non-root user `codefreedom` (uid 1000).

Replaces the upstream `ghcr.io/berriai/litellm` image so we control the LiteLLM version, patches, and the Trivy CVE surface. Published on `docker.io` and `ghcr.io`.

**web-bridge component.** The `docker/web-bridge/` directory contains `Dockerfile.Bridge`, `requirements.txt`, and `app/bridge.py`. It builds the `codefreedom:web-bridge` image, published on `docker.io` and `ghcr.io`. The bridge runs as a sibling service in the proxy `docker-compose.yaml` on the shared `codefreedom` network — no host port is published. LiteLLM reaches it via service DNS at `http://web-bridge:8500`. The bridge translates SearXNG-shaped `/search` requests into JSON-RPC calls against the Camoufox MCP `web_search` tool, enabling LiteLLM's `websearch_interception` callback to transparently replace Claude Code's native `WebSearch` with a local stealth browser. See `docker/web-bridge/README.md` and `docs/proxy/websearch-interception.md`.

Details on Docker naming, image families, proxy system: see `CLAUDE.md` > Docker / Proxy System.

## Dependency Graph

```
config.py, env_loader.py, profiles.py, tool_registry.py  (leaf — no intra-package deps)
  |
cli/docker_utils.py                                       (stdlib only)
cli/init_utils.py                                         (stdlib only)
cli/tool_init_utils.py                                    -> env_loader
  |
cli/main.py                                               -> env_loader
cli/launcher.py                                            -> config, env_loader
cli/claude.py                                              -> init_utils, config, env_loader, launcher, profiles, tool_registry
cli/proxy.py                                               -> init_utils, config, env_loader
cli/chrome.py, cli/web.py                                  -> docker_utils, init_utils, tool_init_utils, config, env_loader
cli/vscode.py                                              -> config, env_loader, profiles
```

## Request Flow

### `codefreedom claude --sandbox`

```
main.py (parse)
  -> claude.py (load profile, resolve sandbox image, get tools)
    -> profiles.py (load_profiles, get_profile_sandbox_images, get_profile_tools)
    -> tool_registry.py (acquire_tools: start Docker tool containers, write /proc locks)
    -> launcher.py (run_docker: create ephemeral container, exec Claude CLI)
      -> config.py (get_codefreedom_dir for volume mounts)
    -> tool_registry.py (release_tools: decrement ref_count, stop if last session)
```

### `codefreedom proxy start`

```
main.py (parse)
  -> proxy.py (_start_compose: Docker Compose only)
    -> config.py (get_codefreedom_dir for proxy path)
    -> env_loader.py (load_dotenv for proxy env files)
    -> docker compose up -d starts:
       - litellm (:4000)         — codefreedom:litellm-latest (embedded PG, patches baked in)
       - web-bridge (:8500)      — codefreedom:web-bridge   -->  Camoufox MCP (:8420/mcp)
```

The LiteLLM container entrypoint handles: PG cluster init (first run), `prisma db push`, plugin deployment (reasoning-efforts mapping `.py` into the host-mounted config dir), and LiteLLM startup. The embedded PG listens on localhost:5432 only (no host port exposed).

The web-bridge is a FastAPI sidecar (`docker/web-bridge/`) that translates
SearXNG-shaped `/search` requests into JSON-RPC calls against the Camoufox
MCP `web_search` tool. LiteLLM's `websearch_interception` callback routes
Claude Code's native `WebSearch` to the bridge — transparently replacing it
with a local stealth browser call.

### `codefreedom tools chrome start`

```
main.py (parse)
  -> chrome.py (load tool profile, start container)
    -> docker_utils.py (check_docker, ensure_image, container_is_running)
    -> config.py (get_codefreedom_dir for data_dir)
```

## Rules

- **One responsibility per block.** If a file does two things, split it.
- **Add a block when shared across 2+ locations.** One-off logic stays inline.
- **Layer discipline.** CLI calls core. Core calls nothing in the package. Infra is data, not code.
- **Keep this file accurate.** When code changes, update the inventory and graph in the same PR.

## Tool Registry (`/proc`) Design

Tools declared in profiles (`"tools": ["chrome", "web"]`) are auto-managed.
The tool registry in `~/.codefreedom/proc/` tracks which sessions use which tools.

### Directory Layout

```
~/.codefreedom/proc/
  sessions/
    <session-id>.json    — session_id, profile, tools, pid, started_at
  tools/
    <tool>.json          — tool, container_name, ref_count, sessions dict
```

### Lifecycle

1. **`codefreedom claude` starts** — `acquire_tools()`:
   - `cleanup_stale_sessions()` first: reaps dead-PID sessions, adjusts ref_counts
     (never stops containers — they are adopted by the next session)
   - For each tool: call `tool.start()` (no-op if container already running)
   - Create/increment tool lock with session ID in sessions dict
   - Write session file
2. **Claude session runs** — tools stay running independently
3. **Claude exits** (normal or Ctrl+C) — `release_tools()` in finally block:
   - Decrement ref_count, remove session from sessions dict
   - If ref_count == 0: call `tool.stop()`, delete lock
   - Delete session file
4. **Crash (SIGKILL)** — finally doesn't run, but `cleanup_stale_sessions()`
   on next invocation cleans `/proc` state. The running container is adopted.
5. **Reboot** — tool containers restart (persistent `--restart unless-stopped`).
   Stale `/proc` entries cleaned; containers adopted by next session.

### First-one-starts, last-one-stops

| Session A | Session B | Chrome State            |
| --------- | --------- | ----------------------- |
| starts    | —         | started (ref=1)         |
| running   | starts    | already running (ref=2) |
| exits     | running   | stays running (ref=1)   |
| —         | exits     | stopped (ref=0)         |
