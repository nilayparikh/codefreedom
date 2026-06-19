---
title: Chrome
description: Headless Chrome browser for automation, screenshots, and page interaction.
---

## Overview

Runs Google Chrome in Docker with Chrome DevTools Protocol (CDP) enabled. Code agents use this for browser automation, taking screenshots, filling forms, clicking elements, and executing JavaScript on pages.

**Third-party components:** Google Chrome / Chromium (Google LLC), dumb-init (PID 1 supervisor) (Yelp, Inc.)

## Endpoints

| Endpoint | URL | Purpose |
| --- | --- | --- |
| CDP | `http://127.0.0.1:9222` | Chrome DevTools Protocol |
| MCP | `http://127.0.0.1:9223/mcp` | MCP server for agent integration |
| DevTools | `devtools://devtools/bundled/inspector.html?ws=127.0.0.1:9222` | Browser DevTools UI |

## Configuration

Profile: `~/.codefreedom/profiles/chrome.yaml`

```yaml
chrome:
  image: docker.io/nilayparikh/codefreedom:chrome-latest
  container_name: codefreedom-tools-chrome
  port: 9222
  mcp_port: 9223
  mcp_path: /mcp
  env:
    CHROME_DEBUG_PORT: '9222'
    MCP_PORT: '9223'
```

| Setting | Default | Description |
| --- | --- | --- |
| `image` | `codefreedom:chrome-latest` | Docker image |
| `container_name` | `codefreedom-tools-chrome` | Docker container name |
| `port` | `9222` | CDP debug port (host) |
| `mcp_port` | `9223` | MCP server port (host) |
| `mcp_path` | `/mcp` | MCP endpoint path |
| `cdp_proxy_port` | `9220` | CDP proxy port (container internal) |

## Environment Variables

| Variable | Description |
| --- | --- |
| `CHROME_DEBUG_PORT` | CDP port inside container |
| `MCP_PORT` | MCP port inside container |
| `CDP_PROXY_PORT` | CDP proxy port inside container |
| `CODEFREEDOM_CHROME_PORT` | Override host port via env |

## Docker

The container runs with `--shm-size=512m` for adequate shared memory. Port mapping:

```text
Host 9222 → Container 9220 (CDP proxy)
Host 9223 → Container 9223 (MCP)
```

Data directory: `~/.codefreedom/tools/chrome/` mounted to `/data/chrome`.

## MCP Server Name

Registered as `chrome-devtools` in agent MCP configs.

## Commands

```bash
cf run tools chrome start       # Start Chrome container
cf run tools chrome stop        # Stop and remove
cf run tools chrome restart     # Restart
cf run tools chrome status      # Show status
cf run tools chrome url         # Print CDP URL
```

Short:

```bash
cf r tl chrome start
cf r tl chrome status
```
