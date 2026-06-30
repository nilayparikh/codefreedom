# CodeFreedom Codebase Memory MCP Bridge

HTTP MCP bridge over [DeusData/codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp)
stdio. Exposes the upstream's 14 code-intelligence tools
(`index_repository`, `search_graph`, `trace_path`, `query_graph`,
`detect_changes`, `get_architecture`, `get_code_snippet`, `search_code`,
`manage_adr`, `list_projects`, `delete_project`, `index_status`,
`get_graph_schema`, `ingest_traces`) as an HTTP MCP server on port
`8330`.

## Build

```bash
docker build \
  --build-arg CBM_VERSION=0.8.1 \
  -t docker.io/nilayparikh/codefreedom:codebase-memory-latest \
  -f docker/codebase-memory/Dockerfile.CodebaseMemory \
  docker/codebase-memory/
```

`CBM_VERSION` defaults to `0.8.1`. Pin to a known-good release; bump via
the GitHub Actions workflow input.

The Dockerfile pulls the upstream `-portable` Linux static binary and
verifies its SHA-256 against the published `checksums.txt`. `-portable`
is fully static (no glibc version pinning), matching the upstream's own
guidance for older distributions.

## Run

```bash
docker run -d --name codefreedom-tools-codebase-memory \
  -p 8330:8330 \
  -e CBM_LOG_LEVEL=info \
  -e CBM_CACHE_DIR=/cache \
  -v ~/.codefreedom/tools/codebase-memory:/cache \
  docker.io/nilayparikh/codefreedom:codebase-memory-latest
```

Optional: enable the built-in 3D graph visualization on a second port
by adding `-e ENABLE_UI=1` and `-p 9749:9749`.

## Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `CBM_CACHE_DIR` | `/cache` | SQLite cache + per-project indexes |
| `CBM_LOG_LEVEL` | `info` | `debug`, `info`, `warn`, `error`, `none` |
| `CBM_AUTO_INDEX` | `false` | Auto-index on MCP session start |
| `CBM_DIAGNOSTICS` | `false` | Periodic diagnostics to `/tmp/cbm-diagnostics-<pid>.ndjson` |
| `CBM_WORKERS` | auto | Override upstream worker count |
| `ENABLE_UI` | `false` | Spawn upstream with `--ui=true --port=9749` |
| `MCP_LISTEN_HOST` | `0.0.0.0` | HTTP listen host |
| `MCP_LISTEN_PORT` | `8330` | HTTP MCP listen port |

## Endpoints

| Endpoint | Purpose |
| --- | --- |
| `POST /mcp` | HTTP MCP JSON-RPC endpoint |
| `GET /healthz` | Liveness probe |
| `GET /` (port 9749, when `ENABLE_UI=1`) | Graph visualization UI |

## Image Registries

- `docker.io/nilayparikh/codefreedom:codebase-memory-latest`
- `ghcr.io/nilayparikh/codefreedom:codebase-memory-latest`

## Third-Party Components

- [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) by DeusData
- [Python](https://www.python.org/) (runtime)

See the upstream repository for license and security details.
