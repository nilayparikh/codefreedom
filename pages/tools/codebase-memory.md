---
title: Codebase Memory
description: Codebase knowledge graph MCP server — 14 structural tools for code intelligence (indexing, search, trace, query, architecture).
---

## Overview

Runs [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) (DeusData) in Docker with an HTTP bridge. Indexes your source code into a persistent knowledge graph and exposes 14 MCP tools that give coding agents structural understanding of a codebase — call graphs, dead-code detection, semantic search, architectural overview, and more.

**Third-party components:** codebase-memory-mcp (DeusData)

**All processing is local.** Source code never leaves your machine.

## Endpoints

| Endpoint | URL | Purpose |
| --- | --- | --- |
| MCP | `http://127.0.0.1:8330/mcp` | MCP server for agent integration |
| Graph UI (optional) | `http://127.0.0.1:9749/` | 3D knowledge graph visualizer (when `enable_ui: true`) |

## Configuration

Profile: `~/.codefreedom/profiles/codebase_memory.yaml`

```yaml
codebase-memory:
  image: docker.io/nilayparikh/codefreedom:codebase-memory-latest
  container_name: codefreedom-tools-codebase-memory
  port: 8330
  ui_port: 9749
  bind_host: "0.0.0.0"
  remote_url: "http://192.168.1.5:8330"
  enable_ui: false
  log_level: info
  auto_index: false
  env:
    CBM_CACHE_DIR: /cache
    CBM_LOG_LEVEL: info
```

| Setting | Default | Description |
| --- | --- | --- |
| `image` | `codefreedom:codebase-memory-latest` | Docker image (wraps `DeusData/codebase-memory-mcp`) |
| `container_name` | `codefreedom-tools-codebase-memory` | Docker container name |
| `port` | `8330` | Host port for the HTTP MCP endpoint |
| `ui_port` | `9749` | Host port for the optional graph-UI server |
| `bind_host` | `0.0.0.0` | Bind address (all interfaces) |
| `remote_url` | `None` | Remote Codebase Memory endpoint URL |
| `enable_ui` | `false` | Expose the 3D graph visualization on `ui_port` |
| `log_level` | `info` | Upstream log verbosity: `debug`, `info`, `warn`, `error`, `none` |
| `auto_index` | `false` | Upstream auto-index on MCP session start |
| `env.CBM_CACHE_DIR` | `/cache` | Upstream SQLite cache directory (mounted from data_dir) |

## MCP Tools

The 14 tools exposed by `codebase-memory-mcp` are registered as `mcp__codebase-memory__*` in agent MCP configs:

### Indexing

| Tool | Description |
| --- | --- |
| `index_repository` | Index a repository into the knowledge graph |
| `list_projects` | List all indexed projects with node/edge counts |
| `delete_project` | Remove a project and all its graph data |
| `index_status` | Check indexing status of a project |

### Querying

| Tool | Description |
| --- | --- |
| `search_graph` | Structured search by label, name pattern, file pattern, degree filters |
| `trace_path` | BFS traversal — who calls a function and what it calls (depth 1-5) |
| `detect_changes` | Map git diff to affected symbols with risk classification |
| `query_graph` | Execute Cypher-like graph queries (read-only) |
| `get_graph_schema` | Node/edge counts, relationship patterns, property definitions |
| `get_code_snippet` | Read source code for a function by qualified name |
| `get_architecture` | Codebase overview: languages, packages, routes, hotspots, clusters, ADR |
| `search_code` | Grep-like text search within indexed project files |
| `manage_adr` | CRUD for Architecture Decision Records |
| `ingest_traces` | Ingest runtime traces to validate HTTP_CALLS edges |

## Environment Variables

| Variable | Description |
| --- | --- |
| `CBM_CACHE_DIR` | SQLite cache + per-project indexes (default: `/cache` inside the container) |
| `CBM_LOG_LEVEL` | Upstream log verbosity |
| `CBM_AUTO_INDEX` | Set to `true` to auto-index on MCP session start |
| `CBM_DIAGNOSTICS` | Set to `1` to write periodic diagnostics to `/tmp/cbm-diagnostics-<pid>.ndjson` |
| `CBM_WORKERS` | Override upstream parallel-indexing worker count |
| `ENABLE_UI` | Set to `1` to start the upstream with `--ui=true --port=9749` |
| `CF_CLI_CODEBASE_MEMORY_PORT` | Machine env var override for `port` |
| `CF_CLI_CODEBASE_MEMORY_UI_PORT` | Machine env var override for `ui_port` |

## Docker

Data directory: `~/.codefreedom/tools/codebase-memory/` mounted to `/cache` (the upstream's `CBM_CACHE_DIR`).

Resource caps: `--shm-size=512m -m 4g --memory-swap 4g` (matches the indexing workload profile).

## MCP Server Name

Registered as `codebase-memory` in agent MCP configs.

## Commands

```bash
cf run tools codebase-memory start       # Start Codebase Memory container
cf run tools codebase-memory stop        # Stop and remove
cf run tools codebase-memory restart     # Restart
cf run tools codebase-memory status      # Show status
```

Short:

```bash
cf r tl codebase-memory start
cf r tl -m start         # all tools, filter by --codebase-memory
cf r tl status
```

## Example Agent Usage

Ask your agent: **"Index this project and tell me what calls `Search`."**

The agent calls:

1. `mcp__codebase-memory__index_repository(repo_path="/abs/path")` — builds the knowledge graph
2. `mcp__codebase-memory__trace_path(function_name="Search", direction="both")` — returns the call graph

For multi-service work, point `remote_url` at a shared server so your whole team reuses the same index:

```yaml
codebase-memory:
  remote_url: "http://192.168.1.5:8330"
```
