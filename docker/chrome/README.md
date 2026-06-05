# docker/chrome

Headless Google Chrome container for browser automation via the Chrome DevTools Protocol (CDP).

## Overview

Runs plain headless Chrome in a minimal Ubuntu 24.04 container:

- **Headless mode** (`--headless=new`) -- no Xvfb, no display server, no fonts
- **Architecture-aware** -- Google Chrome Stable on amd64; Chromium snapshots from the Playwright CDN on arm64
- **`dumb-init` as PID 1** -- clean signal handling
- **Healthcheck** -- verifies the CDP `/json/version` endpoint
- **Minimal attack surface** -- no DBus, no PulseAudio, no X11, no sudo
- **stderr filtering** -- drops harmless warnings (xkbcomp, GCM, Vulkan) so logs stay clean
- **Stale lock cleanup** -- removes `SingletonLock`/`SingletonCookie`/`SingletonSocket` from previous container runs

For **stealth / anti-bot / headed** browsing, use the [web tool](../web/README.md) instead.

## Files

| File | Description |
| --- | --- |
| `Dockerfile.Chrome` | Multi-arch Dockerfile (amd64 + arm64) |

## Build

```bash
docker build --build-arg IMAGE_VERSION=0.2.0 \
  -t codefreedom:chrome-v0.2.0 \
  -f docker/chrome/Dockerfile.Chrome docker/chrome/
```

## Run

```bash
docker run -d --name codefreedom-chrome \
  -p 9222:9222 \
  --shm-size=512m \
  -v ~/.codefreedom/sandbox/tools/chrome:/data/chrome \
  codefreedom:chrome-latest
```

## Usage with CodeFreedom

```bash
codefreedom tools chrome init     # accept terms, generate profile
codefreedom tools chrome start    # start container
codefreedom tools chrome url      # print CDP debug URL
codefreedom tools chrome status   # check container status
codefreedom tools chrome stop     # stop container
```

## Connecting from an Agent

Point Playwright, Puppeteer, or DevTools to the CDP WebSocket:

```
ws://127.0.0.1:9222
```

Or open DevTools directly:

```
devtools://devtools/bundled/inspector.html?ws=127.0.0.1:9222
```

## Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `CHROME_DEBUG_PORT` | `9222` | CDP remote debugging port |
| `CHROME_DATA_DIR` | `/data/chrome` | Persistent profile data directory |

## Data Persistence

Browser profile data (cookies, localStorage, extensions) persists in the mounted `CHROME_DATA_DIR` volume across container restarts.

## Registry

Published images are available on:
- `docker.io/nilayparikh/codefreedom:chrome`
- `ghcr.io/nilayparikh/codefreedom:chrome`
- `ghcr.io/nilayparikh/codefreedom:chrome-latest`
