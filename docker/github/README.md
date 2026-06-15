# docker/github

HTTP MCP bridge over GitHub's official `github-mcp-server`. Wraps the Go stdio binary with a Python HTTP server so coding agents can connect via a clean HTTP endpoint.

## Overview

- Extracts `github-mcp-server` from the official `ghcr.io/github/github-mcp-server` image
- Runs a Python bridge that translates HTTP JSON-RPC requests to stdio
- Exposes MCP tools (issues, PRs, repos, search) on port 8082

## Files

| File | Description |
| --- | --- |
| `Dockerfile.Github` | Multi-stage Dockerfile (amd64 + arm64) |
| `bridge.py` | Python stdio-to-HTTP MCP bridge |

## Build

```bash
docker build \
  -t docker.io/nilayparikh/codefreedom:github-latest \
  -f docker/github/Dockerfile.Github docker/github/
```

## Run

```bash
docker run -d --name codefreedom-tools-github \
  -p 8082:8082 \
  -e GITHUB_PERSONAL_ACCESS_TOKEN=ghp_... \
  docker.io/nilayparikh/codefreedom:github-latest
```

## Usage with CodeFreedom

Managed automatically by the tool registry. The host port (default 8129) is mapped to container port 8082.

```bash
codefreedom run tools github start     # start container
codefreedom run tools github status    # check status
codefreedom run tools github stop      # stop container
```

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/mcp` | MCP JSON-RPC endpoint |
| `GET` | `/healthz` | Liveness probe |

## Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | _(required)_ | GitHub PAT for API access |
| `MCP_LISTEN_HOST` | `0.0.0.0` | Bind address |
| `MCP_LISTEN_PORT` | `8082` | Bind port |

## Registry

Published images:

- `docker.io/nilayparikh/codefreedom:github-latest`
- `ghcr.io/nilayparikh/codefreedom:github-latest`
