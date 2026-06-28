---
title: Web Bridge
description: SearXNG-shaped HTTP bridge for LiteLLM web search interception.
---

## Overview

Translates SearXNG-style `/search` requests into MCP calls against the Camoufox `web_search` tool. LiteLLM's `websearch_interception` callback routes Claude Code's native WebSearch through this bridge.

The bridge sits between the LiteLLM proxy and the [Web tool](web.md) — it does not run its own browser.

## Endpoints

| Endpoint | URL | Purpose |
| --- | --- | --- |
| Search | `http://127.0.0.1:8500/search` | SearXNG-compatible search API |
| Health | `http://127.0.0.1:8500/healthz` | Health check |

## Configuration

Profile: `~/.codefreedom/profiles/web-bridge.yaml`

```yaml
web_bridge:
  image: docker.io/nilayparikh/codefreedom:web-bridge-latest
  container_name: codefreedom-web-bridge
  port: 8500
  bind_host: "0.0.0.0"
  remote_url: "http://192.168.1.5:8500"
  env:
    MCP_WEB_URL: ${MCP_WEB_URL:-http://host.docker.internal:8420/mcp}
    WEB_BRIDGE_COOLDOWN_SECONDS: ${WEB_BRIDGE_COOLDOWN_SECONDS:-2.0}
    MCP_TIMEOUT_SECONDS: ${MCP_TIMEOUT_SECONDS:-60}
```

| Setting | Default | Description |
| --- | --- | --- |
| `image` | `codefreedom:web-bridge-latest` | Docker image |
| `container_name` | `codefreedom-web-bridge` | Docker container name |
| `port` | `8500` | Host port |
| `bind_host` | `0.0.0.0` | Bind address (all interfaces) |
| `remote_url` | `None` | Remote Web Bridge endpoint URL |

## Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `MCP_WEB_URL` | `http://host.docker.internal:8420/mcp` | URL to Camoufox MCP server |
| `WEB_BRIDGE_COOLDOWN_SECONDS` | `2.0` | Delay between searches |
| `MCP_TIMEOUT_SECONDS` | `60` | Timeout for MCP calls |
| `CODEFREEDOM_WEB_BRIDGE_PORT` | `8500` | Override host port via env |

## How It Fits

```text
Claude Code WebSearch → LiteLLM websearch_interception → Web Bridge (:8500) → Camoufox MCP (:8420)
```

The proxy's `config.yaml` configures this:

```yaml
search_tools:
  - search_tool_name: codefreedom-web
    litellm_params:
      search_provider: searxng
      api_base: http://web-bridge:8500
```

## Docker

Data directory: `~/.codefreedom/tools/web-bridge/` mounted to `/app/data`.

**Note:** Start the web-bridge before the proxy so WebSearch works:

```bash
cf r tl web-bridge start
cf r px start
```

## MCP Server Name

Registered as `web-bridge` in agent MCP configs.

## Commands

```bash
cf run tools web-bridge start   # Start bridge container
cf run tools web-bridge stop    # Stop and remove
cf run tools web-bridge restart # Restart
cf run tools web-bridge status  # Show status
```

Short:

```bash
cf r tl web-bridge start
cf r tl web-bridge status
```
