---
title: GitHub Tool
description: GitHub API tools (issues, PRs, repos) via MCP server.
---

# GitHub Tool

Exposes GitHub's API as MCP tools. Your code agent can manage repos, issues, pull requests, and more — all through `http://127.0.0.1:8082/mcp`.

## What It Does

- **Repository operations** — create repos, manage branches, view code
- **Issue management** — create, update, search, comment on issues
- **Pull requests** — create, review, merge
- **Code search** — search across repos, code, and users

## Requirements

A **GitHub Personal Access Token (PAT)** with appropriate scopes:
- Classic tokens: `repo` and `read:org`
- Fine-grained tokens: permissions matching your target repos

## Usage

```bash
codefreedom tools github init     # One-time setup
codefreedom tools github start    # Validate token, pull image
codefreedom tools github status   # Check status
codefreedom tools github stop     # No-op (ephemeral)
```

## Add Your Token

Edit `~/.codefreedom/profiles/github.json`:

```json
{
  "github": {
    "env": {
      "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_your_token_here"
    }
  }
}
```

Or reference a system env var:

```json
{
  "github": {
    "env": {
      "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PERSONAL_ACCESS_TOKEN}"
    }
  }
}
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `image` | `docker.io/nilayparikh/codefreedom:github-latest` | Docker image |
| `container_name` | `codefreedom-tools-github` | Container name |
| `port` | `8082` | HTTP MCP port |

## Ephemeral Design

The GitHub tool runs per-session — it pulls the image, validates your token, and exits. No long-running container. `stop` and `restart` are no-ops.
