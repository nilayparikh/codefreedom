---
title: Web
description: Web search and fetch for research tasks.
---

Web search and fetch for research tasks.

## Quick Start

```bash
# Start Web
cf run tools start --web
# or
cf r tl start -w

# Check status
cf run tools status
# or
cf r tl status

# Stop Web
cf run tools stop --web
# or
cf r tl stop -w
```

## How It Works

```text
Agent → MCP → Docker Container → Web
```

Web runs in a Docker container on port 8420. Your code agent connects via MCP.

## Configuration

Web is configured in your profile's `tools` section:

```yaml
tools:
  - web
```

## Troubleshooting

### Container Won't Start

```bash
# Check Docker
docker ps -a

# Check logs
docker logs codefreedom-web
```

### Agent Can't Connect

```bash
# Test connectivity
curl http://localhost:8420/mcp
```
