---
title: GitHub
description: GitHub MCP server for repository, issue, and pull request access.
---

## Overview

Runs the GitHub MCP Server in Docker with an HTTP bridge. Provides code agents access to GitHub APIs for reading repos, creating issues, reviewing PRs, and searching code.

**Third-party components:** GitHub MCP Server (GitHub, Inc.)

**Warning:** This tool requires a `GITHUB_PERSONAL_ACCESS_TOKEN` with appropriate repository permissions.

## Endpoints

| Endpoint | URL | Purpose |
| --- | --- | --- |
| MCP | `http://127.0.0.1:8129/mcp` | MCP server for agent integration |

## Configuration

Profile: `~/.codefreedom/profiles/github.yaml`

```yaml
github:
  image: docker.io/nilayparikh/codefreedom:github-latest
  container_name: codefreedom-tools-github
  port: 8129
  bind_host: "0.0.0.0"
  remote_url: "http://192.168.1.5:8129"
  env:
    GITHUB_PERSONAL_ACCESS_TOKEN: ${GITHUB_PERSONAL_ACCESS_TOKEN}
```

| Setting | Default | Description |
| --- | --- | --- |
| `image` | `codefreedom:github-latest` | Docker image (wraps `ghcr.io/github/github-mcp-server`) |
| `container_name` | `codefreedom-tools-github` | Docker container name |
| `port` | `8129` | Host port (`0` = auto-pick from 8100–8199) |
| `bind_host` | `0.0.0.0` | Bind address (all interfaces) |
| `remote_url` | `None` | Remote GitHub MCP endpoint URL |
| `env.GITHUB_PERSONAL_ACCESS_TOKEN` | — | Required. GitHub PAT |

## Environment Variables

| Variable | Description |
| --- | --- |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | Required. GitHub personal access token |
| `CF_CLI_GITHUB_PERSONAL_ACCESS_TOKEN` | Machine env var override (strips `CF_CLI_` prefix) |

Get a token at: <https://github.com/settings/tokens>

## Docker

Data directory: `~/.codefreedom/tools/github/` mounted to `/data`.

## MCP Server Name

Registered as `github` in agent MCP configs.

## Commands

```bash
cf run tools github start       # Start GitHub container
cf run tools github stop        # Stop and remove
cf run tools github restart     # Restart
cf run tools github status      # Show status
```

Short:

```bash
cf r tl github start
cf r tl github status
```
