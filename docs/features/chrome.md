---
title: Chrome
description: Headless Chrome browser for web automation.
---

# Chrome

Headless Chrome browser for web automation.

## Quick Start

```bash
# Start Chrome
cf run tools start --chrome
# or
cf r tl start -c

# Check status
cf run tools status
# or
cf r tl status

# Stop Chrome
cf run tools stop --chrome
# or
cf r tl stop -c
```

## How It Works

```
Agent → MCP → Docker Container → Chrome
```

Chrome runs in a Docker container on port 9223. Your code agent connects via MCP.

## Configuration

Chrome is configured in your profile's `tools` section:

```yaml
tools:
  - chrome
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
# Test connectivity
curl http://localhost:9223/mcp
```
