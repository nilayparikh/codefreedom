---
title: Tools
description: Docker-based tools your code agent can use — browser automation, web search, GitHub access.
---

Tools are persistent Docker containers that code agents connect to via MCP (Model Context Protocol). They run independently of agents — start once, use from any agent session.

## Available Tools

| Tool | Purpose | MCP Endpoint | Port |
| --- | --- | --- | --- |
| [Chrome](chrome.md) | Headless browser automation via CDP | `http://127.0.0.1:9223/mcp` | 9222 (CDP), 9223 (MCP) |
| [Web](web.md) | Web search and page fetching via Camoufox | `http://127.0.0.1:8420/mcp` | 8420 |
| [GitHub](github.md) | GitHub API access (repos, issues, PRs) | `http://127.0.0.1:8129/mcp` | 8129 |
| [Web Bridge](web-bridge.md) | SearXNG bridge for LiteLLM web search interception | `http://127.0.0.1:8500/search` | 8500 |

## Manage All Tools

```bash
cf run tools start              # Start all tools
cf run tools stop               # Stop all tools
cf run tools restart            # Restart all tools
cf run tools status             # Show status
```

Short aliases:

```bash
cf r tl start                   # Start all
cf r tl stop                    # Stop all
cf r tl status                  # Status
```

## How Tools Connect to Agents

When you launch an agent ([`cf r ag cc`](../agents/index.md)), CodeFreedom:

1. Reads the agent profile's `tools` list (e.g., `[chrome, web, github]`)
2. Ensures each tool's Docker container is running
3. Builds an MCP server config pointing to each tool's endpoint
4. Writes the config to the agent's workspace (e.g., `.mcp.json` for Claude Code)

The agent sees tools as native MCP servers. No manual wiring needed.

## Tool Profiles

Each tool's config lives in `~/.codefreedom/profiles/<tool>.yaml`:

```yaml
chrome:
  image: docker.io/nilayparikh/codefreedom:chrome-latest
  container_name: codefreedom-tools-chrome
  port: 9222
  mcp_port: 9223
  mcp_path: /mcp
  bind_host: "0.0.0.0"
  remote_url: "http://192.168.1.5:9223"
  env:
    CHROME_DEBUG_PORT: '9222'
    MCP_PORT: '9223'
```

### Common Settings

| Setting | Default | Description |
| --- | --- | --- |
| `bind_host` | `0.0.0.0` | Bind address (all interfaces) |
| `remote_url` | `None` | Remote tool endpoint URL |

**Bind address:** Controls which network interface the tool listens on. Default `0.0.0.0` makes it accessible from any network. Set to `127.0.0.1` for loopback-only.

**Remote URL:** When set, MCP endpoints use this URL instead of the local container. Lifecycle commands (`start`/`stop`/`restart`) are refused for remote tools — use `--local` to override.

Profiles are deployed by recipes. Use `cf s i` to initialize.

## Data Directories

Each tool stores persistent data under `~/.codefreedom/tools/<tool>/`:

```text
~/.codefreedom/tools/
├── chrome/          # Chrome profile, cookies, extensions
├── web/             # Camoufox profile data
├── github/          # GitHub MCP cache
└── web-bridge/      # Bridge state
```

## Third-Party Notices

Each tool container includes third-party components. CodeFreedom is not responsible for their behavior, security, or privacy practices. See individual tool pages for details.
