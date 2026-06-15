---
title: GitHub
description: GitHub API access for repository operations.
---

GitHub API access for repository operations.

## Quick Start

```bash
# Start GitHub
cf run tools start --github
# or
cf r tl start -g

# Check status
cf run tools status
# or
cf r tl status

# Stop GitHub
cf run tools stop --github
# or
cf r tl stop -g
```

## How It Works

```text
Agent → MCP → Docker Container → GitHub
```

GitHub runs in a Docker container on port 8129. Your code agent connects via MCP.

## Configuration

GitHub is configured in your profile's `tools` section:

```yaml
tools:
  - github
```

## Troubleshooting

### Container Won't Start

```bash
# Check Docker
docker ps -a

# Check logs
docker logs codefreedom-github
```

### Agent Can't Connect

```bash
# Test connectivity
curl http://localhost:8129/mcp
```
