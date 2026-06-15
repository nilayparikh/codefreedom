---
title: Tools
description: Browser automation, web search, and GitHub API as Docker containers.
---

Browser automation, web search, and GitHub API — all as Docker containers your code agent can use.

## Available Tools

| Tool | Flag | Short | Port | Description |
| ---- | ---- | ----- | ---- | ----------- |
| Chrome | `--chrome` | `-c` | 9223 | Headless Chrome browser |
| Web | `--web` | `-w` | 8420 | Web search and fetch |
| GitHub | `--github` | `-g` | 8129 | GitHub API access |
| Web Bridge | `--web-bridge` | — | 8421 | Web bridge |

## Quick Start

```bash
# Start all tools
cf run tools start
# or
cf r tl start

# Start specific tools
cf run tools start --chrome --web
# or
cf r tl start -c -w

# Check status
cf run tools status
# or
cf r tl status

# Stop all tools
cf run tools stop
# or
cf r tl stop
```

## How It Works

```text
Agent → MCP → Docker Container → Tool
```

Each tool runs in its own Docker container. Your code agent connects via MCP (Model Context Protocol).

### Chrome

Headless Chrome browser for web automation.

```bash
cf run tools start --chrome
# or
cf r tl start -c
```

### Web Search

Web search and fetch for research tasks.

```bash
cf run tools start --web
# or
cf r tl start -w
```

### GitHub

GitHub API access for repository operations.

```bash
cf run tools start --github
# or
cf r tl start -g
```

## MCP Configuration

Tools register themselves via MCP. The config is at `~/.codefreedom/.mcp.json`:

```json
{
  "mcpServers": {
    "codefreedom-chrome": {
      "url": "http://localhost:9223/mcp"
    },
    "codefreedom-web": {
      "url": "http://localhost:8420/mcp"
    },
    "codefreedom-github": {
      "url": "http://localhost:8129/mcp"
    }
  }
}
```

## Troubleshooting

### Container Won't Start

```bash
# Check Docker
docker ps -a

# Check logs
docker logs codefreedom-chrome
```

### Agent Can't Connect

```bash
# Check MCP config
cat ~/.codefreedom/.mcp.json

# Test connectivity
curl http://localhost:9223/mcp
```

## Command Reference

### `cf run tools`

```text
usage: codefreedom run tools [-h] [-c] [-w] [-g] [--web-bridge] {start,stop,restart,status} ...

positional arguments:
  start                 Start tool containers
  stop                  Stop tool containers
  restart               Restart tool containers
  status                Show tool status

options:
  -h, --help            show this help message and exit
  -c, --chrome          Include Chrome browser
  -w, --web             Include Web search
  -g, --github          Include GitHub MCP
  --web-bridge          Include Web bridge
```
