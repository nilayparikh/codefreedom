# Camoufox Web Search Tool

A stealth browser container based on **Camoufox** (a Firefox fork without
Chrome DevTools Protocol) for undetectable web search and scraping. Runs an
**MCP server on port 8420** exposing `web_search` and `web_fetch` tools.

## Overview

The Camoufox web tool combines a stealth Firefox-based browser with an MCP
server for reliable web automation:

- **Camoufox** — Firefox fork without CDP, presenting a standard Firefox
  profile to websites (no automation fingerprints)
- **Xvfb** — virtual display at 1920x1080x24 for headed mode
- **PyAutoGUI** — OS-level mouse/keyboard emulation for complex interactions
- **browserforge** — generates consistent browser profiles per session
- **MCP Streamable HTTP server** — exposes `web_search` and `web_fetch` tools
  on port 8420

> The MCP server runs inside the container. Coding agents connect to
> `http://localhost:8420` to invoke the tools.

## Usage

```bash
# Initialize the tool profile (accepts third-party notice)
codefreedom tools web init

# Start the container
codefreedom tools web start

# Check container status
codefreedom tools web status

# Stop the container
codefreedom tools web stop
```

### Available MCP Tools

Once the container is running, coding agents can use:

| Tool         | Description                                                                                  |
| ------------ | -------------------------------------------------------------------------------------------- |
| `web_search` | Search the web via configured engines, returns structured results with optional AI summaries |
| `web_fetch`  | Fetch a web page's content (text + HTML) with anti-bot evasion                               |

## Container

The container image is based on `python:3.13-slim` (multi-arch: `linux/arm64`,
`linux/amd64`). It includes:

- Camoufox stealth browser (Firefox fork) — [Dockerfile](https://github.com/nilayparikh/codefreedom/blob/main/docker/web/Dockerfile.Camoufox)
- Xvfb (X virtual framebuffer)
- PyAutoGUI (OS-level input automation)
- browserforge (browser profile generation)
- MCP Python SDK (Streamable HTTP server)

### Image

| Setting          | Default                                 | Profile override (in `camoufox.json`)                         |
| ---------------- | --------------------------------------- | ------------------------------------------------------------- |
| `image`          | `codefreedom:camoufox`                  | Change to `docker.io/nilayparikh/codefreedom:camoufox-latest` |
| `container_name` | `codefreedom-camoufox`                  | Custom container name                                         |
| `port`           | `8420`                                  | MCP server port                                               |
| `data_dir`       | `~/.codefreedom/sandbox/tools/camoufox` | Persistent data mount                                         |
| `env`            | `DISPLAY=:99`                           | Extra env vars forwarded to container                         |

### Data Persistence

Browser profile data (cookies, sessions, storage) persists in
`~/.codefreedom/sandbox/tools/camoufox/` across container restarts.

## Third-Party Components

This container includes:

- Camoufox — stealth browser (daijro)
- Firefox — browser engine (Mozilla Foundation)

CodeFreedom is not responsible for the behavior, security, or privacy
practices of these components.
