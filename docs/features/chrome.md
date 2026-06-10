---
title: Chrome Tool
description: Headless Chrome container for browser automation via CDP.
---

# Chrome Tool

A headless Google Chrome container for browser automation. Code agents connect via the Chrome DevTools Protocol (CDP) on port 9222.

## When to Use

- Automate browser interactions (click, fill forms, navigate)
- Run Playwright or Puppeteer scripts
- Need a simple, fast browser target

> For web search and stealth scraping, use the [Web tool](web.md) instead.

## Usage

```bash
# Install the _default recipe to create the chrome profile
cf init recipe

codefreedom tools chrome start    # Start container
codefreedom tools chrome url      # Get CDP debug URL
codefreedom tools chrome status   # Check status
codefreedom tools chrome stop     # Stop
```

## Connecting from an Agent

Get the CDP URL:

```bash
codefreedom tools chrome url
```

Output:

```
devtools://devtools/bundled/inspector.html?ws=127.0.0.1:9222
```

Or point Playwright/Puppeteer to `ws://127.0.0.1:9222`.

## Configuration

Settings live in `~/.codefreedom/profiles/chrome.json`:

| Setting          | Default                               | Description     |
| ---------------- | ------------------------------------- | --------------- |
| `image`          | `codefreedom:chrome`                  | Docker image    |
| `container_name` | `codefreedom-chrome`                  | Container name  |
| `port`           | `9222`                                | CDP debug port  |
| `data_dir`       | `~/.codefreedom/sandbox/tools/chrome` | Persistent data |

## Data Persistence

Browser data (cookies, localStorage, extensions) persists in `~/.codefreedom/sandbox/tools/chrome/` across restarts.
