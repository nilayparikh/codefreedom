---
title: Web Tool
description: Stealth browser for web search and scraping via MCP server.
---

# Web Tool

A headless browser container for web search and scraping. Runs an MCP server on port 8420.

## When to Use

- Search the web from your code agent
- Scrape pages that block standard bots
- Need stealth/anti-bot browsing

> For simple browser automation (click, fill forms), use the [Chrome tool](chrome.md) instead.

## Usage

```bash
# Install the _default recipe to create the web profile
cf setup init

codefreedom run tools web start     # Start container
codefreedom run tools web status    # Check status
codefreedom run tools web restart   # Restart (preserves state)
codefreedom run tools web stop      # Stop
```

## Available Tools

Once running, your code agent can use:

| Tool                | What It Does                                  |
| ------------------- | --------------------------------------------- |
| `web_search(query)` | Search the web via configured engines         |
| `web_fetch(url)`    | Fetch a webpage (bypasses anti-bot detection) |

Connect to `http://127.0.0.1:8420/mcp`.

## Configuration

Settings live in `~/.codefreedom/profiles/web.json`:

| Setting          | Default                            | Description     |
| ---------------- | ---------------------------------- | --------------- |
| `image`          | `codefreedom:web`                  | Docker image    |
| `container_name` | `codefreedom-web`                  | Container name  |
| `port`           | `8420`                             | MCP server port |
| `data_dir`       | `~/.codefreedom/sandbox/tools/web` | Persistent data |

## Data Persistence

Browser sessions (cookies, storage) persist in `~/.codefreedom/sandbox/tools/web/` across restarts.
