---
title: Web
description: Stealth web browser for search and page fetching via Camoufox.
---

## Overview

Runs Camoufox (a stealth Firefox fork) in Docker as an MCP server. Provides two tools to code agents:

- **`web_search(query)`** — search configured engines and return results
- **`web_fetch(url)`** — fetch a page, bypassing anti-bot protections

**Third-party components:** Camoufox (daijro), Firefox (Mozilla Foundation)

**Warning:** The web scraping tool is designed for internal websites or permissible public infrastructure. Do not use or repurpose beyond permissible use cases.

## Endpoints

| Endpoint | URL | Purpose |
| --- | --- | --- |
| MCP | `http://127.0.0.1:8420/mcp` | MCP server for agent integration |

## Configuration

Profile: `~/.codefreedom/profiles/web.yaml`

```yaml
web:
  image: docker.io/nilayparikh/codefreedom:web-latest
  container_name: codefreedom-web
  port: 8420
  bind_host: "0.0.0.0"
  remote_url: "http://192.168.1.5:8420"
  env: {}
  search_cooldown_seconds: 10.0
  search_engines:
    search_engine1:
      url: https://search-engine-1/search?q={q}
      parser: standard
    search_engine2:
      url: https://search-engine-2/search?q={q}
      parser: standard
  parser_registry:
    standard:
      result_selectors: ...
      link_selector: ...
      snippet_selectors: ...
      ai_selectors:
        - .chatllm-content
        - .b_ans
```

| Setting | Default | Description |
| --- | --- | --- |
| `image` | `codefreedom:web-latest` | Docker image |
| `container_name` | `codefreedom-web` | Docker container name |
| `port` | `8420` | MCP server port |
| `bind_host` | `0.0.0.0` | Bind address (all interfaces) |
| `remote_url` | `None` | Remote Web endpoint URL |
| `search_cooldown_seconds` | `10.0` | Delay between searches |
| `search_engines` | Choice of your search engine | Map of engine name → `{url, parser}` |
| `parser_registry` | `standard` | CSS selectors for result extraction |

## Search Engines

Each engine entry has:

- **`url`** — search URL template with `{q}` placeholder
- **`parser`** — key in `parser_registry` defining CSS selectors

The `standard` parser extracts:

| Field | Selectors |
| --- | --- |
| Results | `[data-type='web']`, `.b_algo`, `#res .g`, `.result`, `li:has(h2 a[href])` |
| Links | `h2 a[href]`, `h3 a[href]`, `a[href]` |
| Snippets | `.b_caption p`, `.b_lineclamp2`, `.generic-snippet .content`, `.description` |
| AI summaries | `.chatllm-content`, `.b_ans`, `.rai_content`, `.knowledge-panel` |

## Environment Variables

| Variable | Description |
| --- | --- |
| `CODEFREEDOM_WEB_PORT` | Override host port via env |

## Docker

Data directory: `~/.codefreedom/tools/web/` mounted to `/userdata`.

## MCP Server Name

Registered as `web` in agent MCP configs.

## Commands

```bash
cf run tools web start          # Start Web container
cf run tools web stop           # Stop and remove
cf run tools web restart        # Restart
cf run tools web status         # Show status
```

Short:

```bash
cf r tl web start
cf r tl web status
```
