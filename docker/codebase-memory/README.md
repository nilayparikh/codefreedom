# CodeFreedom Codebase Memory MCP Bridge

HTTP MCP bridge over [DeusData/codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp)
stdio, plus a self-contained host-side Python manager
(`src/codebase_memory/`) that runs **one container per git workspace**.

The upstream exposes 14 code-intelligence tools
(`index_repository`, `search_graph`, `trace_path`, `query_graph`,
`detect_changes`, `get_architecture`, `get_code_snippet`, `search_code`,
`manage_adr`, `list_projects`, `delete_project`, `index_status`,
`get_graph_schema`, `ingest_traces`) as an HTTP MCP server on port
`8330`. When `ENABLE_UI=1` the upstream's built-in 3D graph
visualization is exposed on port `9749`.

## What lives here

```
docker/codebase-memory/
├── Dockerfile.Codebase-memory       # builds the in-container image
├── bridge.py                        # in-container stdio↔HTTP bridge
├── README.md                        # this file
└── src/
    └── codebase_memory/             # host-side Python package
        ├── __init__.py
        ├── git_root.py              # git rev-parse --show-toplevel, max 3 levels
        ├── project_id.py            # sanitize basename, collision disambiguator
        ├── manifest.py              # per-workspace YAML manifest
        ├── related.py               # related git paths
        ├── manager.py               # docker run/stop/restart, port allocation
        ├── reconcile.py             # manifest vs running container
        ├── compact.py               # VACUUM the cache, optional team-shared artifact
        ├── browser.py               # webbrowser wrapper
        └── cli.py                   # 8 subcommands
```

The host-side package is imported by codefreedom at
`src/codefreedom/tools/codebase_memory.py` (a thin loader that adds
`docker/codebase-memory/src/` to `sys.path` and re-exports the package).
The in-container bridge runs at container startup and exposes the
upstream's MCP over HTTP.

## Workspace model — per-project container, git-locked

A **workspace** is one git repository. The host-side package resolves
the project root from the user's CWD via:

```bash
git -C <cwd-or-ancestor> rev-parse --show-toplevel
```

walking up at most 3 levels. No `.git` within the bound → error. The
resolved root is the project.

Each project gets its own:

- **Container**: `codefreedom-tools-codebase-memory-<id>` where `<id>`
  is the sanitized basename (e.g. `proj-a`).
- **MCP port**: first free in `8330+` (default 8330); persisted in the
  manifest and auto-advanced if the port is taken.
- **UI port**: `mcp_port + 1419` (e.g. 9749 for 8330).
- **Cache**: `~/.codefreedom/cache/codebase-memory/<id>/` — the
  upstream's SQLite graph store, bind-mounted at `/cache` in the
  container. Survives container restarts; `compact` reclaims space.
- **Manifest**: `<project_root>/.codefreedom/codebase-memory.yaml` —
  the source of truth, user-editable, permissive loader. The
  directory is auto-added to `.gitignore` on first init.

Two agents in different CWDs → two containers, two ports, two cache
dirs. They don't see each other unless they query the same
upstream-indexed project name.

## CLI — `cf r tl cbmem <verb>`

The package ships 8 subcommands; all operate on the **current project**
(no central registry, no FS scan):

```
cf r tl cbmem init                     # create .codefreedom/codebase-memory.yaml
cf r tl bmem start                     # reconcile + start/restart
cf r tl bmem stop                      # stop container
cf r tl bmem restart                   # stop + start
cf r tl bmem status                    # show container, ports, memory, cache, related
cf r tl bmem reset [--keep-manifest] [--keep-cache]
cf r tl bmem logs [-f]
cf r tl bmem compact [--artifact]     # VACUUM the cache; --artifact writes .codebase-memory/graph.db.zst
```

The `cbmem` short alias is also registered. `-h` on each prints help.

### How `start` decides what to do

```
1. Read manifest (or init on miss).
2. If remote_url set → use that, no local container.
3. Else:
   a. Allocate first free MCP+UI port pair starting at 8330+9749.
   b. If container doesn't exist → CREATE.
   c. If container exists, manifest-hash label matches, running → no-op.
   d. If container exists, hash differs → RESTART (rm + run).
   e. If container exists but stopped → START.
4. On CREATED/RESTARTED, if manifest.auto_open_ui is true → open
   http://127.0.0.1:<ui_port>/ in the default browser.
```

The user never types `docker run`. The YAML is the data surface
(paths, aliases, ports, env, related projects, `auto_open_ui`); the
CLI is just lifecycle.

## Manifest shape

```yaml
# <project_root>/.codefreedom/codebase-memory.yaml
# User-editable. Created by 'cf r tl cbmem init' or auto-created on first
# 'cf r ag'. Missing fields get defaults; unknown fields are preserved.
version: 1
id: proj-a
mcp_port: 8330
ui_port: 9749
container_name: codefreedom-tools-codebase-memory-proj-a
image: docker.io/nilayparikh/codefreedom:codebase-memory-v1.0.0
created_at: 2026-06-30T20:00:00Z
last_used_at: 2026-06-30T20:30:00Z

# Networking
remote_url: ""            # when set, no local container; use this MCP URL

# Container tunables
memory_mb: 1024
shm_size_mb: 512
auto_start: true

# UI / UX
auto_open_ui: true        # default true; false to suppress browser auto-open

# Extra environment variables passed to the container
env: {}

# Additional git paths to mount and index in the same container.
# Each becomes a sub-project in the container's cache; queryable via
# search_graph(project="<basename>").
related_paths:
  - path: /home/user/code/shared-lib
    alias: shared
  - path: /home/user/code/sibling
    alias: ""
```

## Why the `-ui` build arg matters

The upstream project ships **two** Linux static binaries per release:

| Asset | Includes HTTP UI? |
| --- | --- |
| `codebase-memory-mcp-linux-{arch}-portable.tar.gz` | no |
| `codebase-memory-mcp-ui-linux-{arch}-portable.tar.gz` | **yes** |

The standard asset silently no-ops the `--ui` flag and the embedded
HTTP server never starts, so `http://127.0.0.1:9749/` returns
`connection reset by peer`. This Dockerfile downloads the **UI** asset
when `ENABLE_UI=1` (the default).

## Why the container runs as root

The manager bind-mounts the user's host source code at
`/workspace/<id>` (read-only) and a per-project cache at `/cache`
(read-write for SQLite WAL). Running as root avoids permission issues
with host UIDs and per-file modes (e.g. a 600-mode file owned by the
host user's UID is still readable as root inside the container). The
`github` MCP tool follows the same convention; `chrome`, `web`, and
`web-bridge` drop to a non-root user because they only touch their
own internal directories and never bind-mount user source.

If a future maintainer is tempted to "harden" the image with a
`USER` directive, they should add a per-mount user remap (e.g.
`--user "$(id -u):$(id -g)"` at run time, plus matching `fsGroup` in
Compose) rather than baking a UID into the image — the per-workspace
mount layout means there is no single UID that works for every host.

## Build

```bash
docker build \
  --build-arg CBM_VERSION=0.8.1 \
  --build-arg ENABLE_UI=1 \
  -t docker.io/nilayparikh/codefreedom:codebase-memory-v1.0.0 \
  -f docker/codebase-memory/Dockerfile.Codebase-memory \
  docker/codebase-memory/
```

`CBM_VERSION` defaults to `0.8.1`. Pin to a known-good release; bump
via the GitHub Actions workflow input.

The Dockerfile pulls the upstream `-portable` Linux static binary
(UI variant when `ENABLE_UI=1`) and verifies its SHA-256 against
the published `checksums.txt`. `-portable` is fully static (no glibc
version pinning), matching the upstream's own guidance for older
distributions.

## Environment Variables (in-container bridge)

| Variable | Default | Description |
| --- | --- | --- |
| `CBM_CACHE_DIR` | `/cache` | SQLite cache + per-project indexes |
| `CBM_LOG_LEVEL` | `info` | `debug`, `info`, `warn`, `error`, `none` |
| `CBM_AUTO_INDEX` | `true` | Auto-index on MCP session start (set by the manager) |
| `CBM_DIAGNOSTICS` | `false` | Periodic diagnostics to `/tmp/cbm-diagnostics-<pid>.ndjson` |
| `CBM_WORKERS` | auto | Override upstream worker count |
| `ENABLE_UI` | `1` | Spawn upstream with `--ui=true` and start the UI proxy |
| `CBM_UI_PORT` | `9749` | Port the proxy listens on (host-visible) |
| `CBM_UI_UPSTREAM_PORT` | `19749` | Port the upstream UI binds inside the container |
| `MCP_LISTEN_HOST` | `0.0.0.0` | HTTP listen host |
| `MCP_LISTEN_PORT` | `8330` | HTTP MCP listen port |
| `REQUEST_TIMEOUT` | `60` | Per-request upstream timeout in seconds |

## Why two UI ports inside the container?

The upstream CBM UI server binds `127.0.0.1` only, which means
Docker's `-p 9749:9749` port mapping has no process to forward to and
host connections get `connection reset by peer`. The bridge therefore
runs a tiny reverse proxy: the upstream listens on
`127.0.0.1:19749` and the proxy binds `0.0.0.0:9749` (the published
port), forwarding every request verbatim. `0.0.0.0:9749` and
`127.0.0.1:9749` would conflict on Linux (same port, different
addresses), which is why the internal port is shifted.

## Endpoints (per workspace)

| Endpoint | Purpose |
| --- | --- |
| `POST /mcp` (host port 8330+) | HTTP MCP JSON-RPC endpoint |
| `GET /healthz` | Liveness probe (returns 503 if upstream is gone) |
| `GET /` (host port 9749+) | Graph visualization UI |
| `GET /assets/...` | UI static assets |
| `GET /api/...` | UI data API (proxied to upstream) |

## Indexing workflow

1. `cd /path/to/your/repo` (must be a git repo, or one within 3 levels up).
2. `cf r tl cbmem init` (or just run `cf r ag` from anywhere in the project — auto-inits).
3. `cf r tl cbmem start` — container comes up, browser auto-opens the UI.
4. From your coding agent, call `index_repository(repo_path="/workspace/<id>")` to index the project.
5. Call `list_projects` to confirm.
6. Use `search_graph`, `trace_path`, `get_architecture`, etc.
7. Open the URL printed by `status` to explore the graph in the browser.

### Multiple workspaces

Each distinct git project is its own workspace. Run `cf r ag` from
`~/code/proj-a` and from `~/code/proj-b` and you get two containers,
two ports, two cache dirs. They share the same upstream image, the
same `~/.codefreedom/cache/codebase-memory/` parent, and the same
launch script — nothing else.

### Cache compaction

`cf r tl cbmem compact` runs `sqlite3 <db> 'VACUUM INTO <db>.compact'`
on every `.db` in the project's cache, atomically swaps, drops the
WAL/SHM sidecars, and reports size deltas. With `--artifact`, also
writes the upstream's `.codebase-memory/graph.db.zst` team-shared
artifact next to the project root.

## Image Registries

- `docker.io/nilayparikh/codefreedom:codebase-memory-v1.0.0`
- `ghcr.io/nilayparikh/codefreedom:codebase-memory-v1.0.0`

## Third-Party Components

- [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) by DeusData
- [Python](https://www.python.org/) (runtime)

See the upstream repository for license and security details.
