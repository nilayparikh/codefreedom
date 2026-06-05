# docker/web-bridge

Thin FastAPI service that translates SearXNG-style `/search` requests into JSON-RPC calls against the local Camoufox MCP `web_search` tool.

## Overview

Enables LiteLLM's `websearch_interception` callback to route Claude Code's native `WebSearch` through a local stealth browser. From Claude Code's perspective, `WebSearch` just works -- no `CLAUDE.md` edits, no `settings.json` changes.

### Request Flow

```
Claude Code  ->  LiteLLM Proxy (:4000)  ->  web-bridge (:8500)  ->  Camoufox MCP (:8420/mcp)  ->  search engines
```

1. Claude Code calls `web_search` via the proxy
2. LiteLLM triggers `websearch_interception` callback
3. Proxy calls `GET /search?q=<query>&format=json` on the bridge
4. Bridge translates to a JSON-RPC `tools/call` against the Camoufox MCP
5. Response flows back as SearXNG-shaped JSON

## Files

| File | Description |
| --- | --- |
| `Dockerfile.Bridge` | Multi-arch Dockerfile (amd64 + arm64) |
| `requirements.txt` | Python dependencies (fastapi, uvicorn, httpx) |
| `app/bridge.py` | FastAPI service -- SearXNG ingress, MCP egress |

## Build

```bash
docker build \
  -t docker.io/nilayparikh/codefreedom:web-bridge \
  -f docker/web-bridge/Dockerfile.Bridge docker/web-bridge/
```

## Deployment

The bridge runs as a sibling service in the proxy's `docker-compose.yaml` -- no separate start command needed:

```bash
codefreedom proxy start --docker    # starts proxy + bridge
docker ps --filter name=codefreedom-web-bridge   # confirm it is up
```

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/search?q=<query>&format=json` | SearXNG-compatible search |
| `GET` | `/healthz` | Liveness probe (`{"status": "ok"}`) |

## Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `HTTP_LISTEN_HOST` | `0.0.0.0` | Bind address |
| `HTTP_LISTEN_PORT` | `8500` | Bind port |
| `MCP_WEB_URL` | `http://host.docker.internal:8420/mcp` | Camoufox MCP endpoint |
| `WEB_BRIDGE_COOLDOWN_SECONDS` | `2.0` | Cooldown between requests (HTTP 429 within window) |
| `MCP_TIMEOUT_SECONDS` | `60` | Per-call MCP HTTP timeout |

## Error Responses

| Status | Code | Meaning |
| --- | --- | --- |
| `429` | `cooldown` | Rate limit active -- retry after cooldown |
| `502` | `mcp_unreachable` | Camoufox MCP is not responding |

## Registry

Published images are available on:
- `docker.io/nilayparikh/codefreedom:web-bridge`
- `ghcr.io/nilayparikh/codefreedom:web-bridge`
