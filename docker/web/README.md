# docker/web

Camoufox (Firefox fork) container with MCP server for stealth / anti-bot web automation.

## Overview

Runs Camoufox -- a Firefox fork that presents a standard browser fingerprint to websites -- inside a Docker container with an MCP (Model Context Protocol) server on port 8420.

- **Camoufox** -- Firefox fork without Chrome DevTools Protocol, avoiding detection
- **Xvfb at 1920x1080x24** -- headed mode with a real display buffer
- **PyAutoGUI** -- OS-level input emulation for interactive workflows
- **browserforge** -- generates consistent browser profiles
- **MCP Streamable HTTP server** on port 8420 (`web_search` + `web_fetch` tools)
- **Persistent profile** in `/userdata` for session continuity
- **MCP-only mode** -- no VNC viewer or other HTTP endpoints exposed

## Files

| File | Description |
| --- | --- |
| `Dockerfile.Web` | Multi-arch Dockerfile (amd64 + arm64) |
| `entrypoint.sh` | Starts Xvfb, Openbox, and the Python MCP server; supports `--script` mode |
| `app/` | Python application (browser, MCP server, extensions) |

## Build

```bash
docker build \
  -t codefreedom:web-v0.1.0 \
  -f docker/web/Dockerfile.Web docker/web/
```

## Run

```bash
docker run -d --name codefreedom-camoufox \
  -p 8420:8420 \
  -v ~/.codefreedom/sandbox/tools/camoufox:/userdata \
  codefreedom:web-latest
```

## Usage with CodeFreedom

```bash
codefreedom run tools web init      # accept terms, generate profile
codefreedom run tools web start     # start container
codefreedom run tools web status    # check container status
codefreedom run tools web stop      # stop container
```

## MCP Server

The MCP server exposes two tools over Streamable HTTP at `/mcp`:

- **`web_search`** -- search the web via Camoufox browser
- **`web_fetch`** -- fetch page content via Camoufox browser

## Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `PUID` | `1000` | Target UID for privilege dropping |
| `PGID` | `$PUID` | Target GID for privilege dropping |
| `XVFB_RESOLUTION` | `1920x1080` | Xvfb display resolution |
| `XVFB_DEPTH` | `24` | Color depth |
| `DISPLAY` | `:99` | X11 display |

## Script Mode

Pass `--script` with YAML on stdin for one-shot automated tasks (returns JSON on stdout, exits):

```bash
docker run --rm codefreedom:web-latest --script < task.yaml
```

## Registry

Published images are available on:

- `docker.io/nilayparikh/codefreedom:web`
- `ghcr.io/nilayparikh/codefreedom:web`
- `ghcr.io/nilayparikh/codefreedom:web-latest`
