# Chrome Browser Tool

A hardened Google Chrome browser container with Xvfb virtual display for
undetectable headed browsing. Coding agents connect via the
**Chrome DevTools Protocol (CDP)** at port 9222 to inspect, debug, and
automate web pages.

## Overview

The Chrome tool runs Google Chrome Stable (retail build) inside a Docker
container with full desktop emulation:

- **Xvfb** — virtual framebuffer at 1920x1080x24 for realistic canvas
  fingerprinting
- **PulseAudio** — prevents `AudioContext` fingerprinting failures
- **MS Core Fonts + CJK + emoji** — matches a desktop font inventory
- **`--ipc=host` + `--cap-add=SYS_ADMIN`** — unprivileged Chrome without
  `--no-sandbox`, preserving accurate WebGL and hardware evaluation

> Chrome DevTools Protocol (CDP) is the standard protocol used by
> Playwright, Puppeteer, and Selenium. Any CDP-compatible client can
> connect to port 9222.

## Usage

```bash
# Initialize the tool profile (accepts third-party notice)
codefreedom tools chrome init

# Start the container
codefreedom tools chrome start

# Get the CDP debug URL for your agent
codefreedom tools chrome url

# Check container status
codefreedom tools chrome status

# Stop the container
codefreedom tools chrome stop
```

### Connecting from an Agent

Use the CDP URL printed by `codefreedom tools chrome url`:

```
devtools://devtools/bundled/inspector.html?ws=127.0.0.1:9222
```

Or point a Playwright/Puppeteer script to `ws://127.0.0.1:9222`.

## Container

The container image is based on `ubuntu:24.04` (multi-arch: `linux/arm64`,
`linux/amd64`). It includes:

- Google Chrome Stable (arm64: Chromium snapshots) — [Dockerfile](https://github.com/nilayparikh/codefreedom/blob/main/docker/chrome/Dockerfile.Chrome)
- Xvfb (X virtual framebuffer)
- PulseAudio (virtual audio)
- MS Core Fonts + CJK + emoji font packages
- `dumb-init` as PID 1 supervisor

### Image

| Setting          | Default                               | Profile override (in `chrome.json`)                         |
| ---------------- | ------------------------------------- | ----------------------------------------------------------- |
| `image`          | `codefreedom:chrome`                  | Change to `docker.io/nilayparikh/codefreedom:chrome-latest` |
| `container_name` | `codefreedom-tools-chrome`            | Custom container name                                       |
| `port`           | `9222`                                | CDP debug port                                              |
| `data_dir`       | `~/.codefreedom/sandbox/tools/chrome` | Persistent data mount                                       |
| `env`            | `DISPLAY=:99`                         | Extra env vars forwarded to container                       |

### Data Persistence

Browser profile data (cookies, localStorage, extensions) persists in
`~/.codefreedom/sandbox/tools/chrome/` across container restarts.

## Third-Party Components

This container includes:

- Google Chrome / Chromium (Google LLC)
- Xvfb — virtual display (X.org Foundation)
- PulseAudio — virtual audio (freedesktop.org)
- MS Core Fonts — Arial, Times New Roman, etc. (Microsoft Corporation)
- dumb-init — PID 1 supervisor (Yelp, Inc.)

CodeFreedom is not responsible for the behavior, security, or privacy
practices of these components.
