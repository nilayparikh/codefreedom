---
title: Install
description: Install CodeFreedom and get started in five minutes.
---

Install CodeFreedom and get started in five minutes.

## Prerequisites

- **Python 3.10+** — for the CLI
- **Docker** — for proxy and sandbox containers
- **Docker Compose** — for multi-container setups

## Install

```bash
pip install codefreedom
```

Or install from source:

```bash
git clone https://github.com/nilayparikh/codefreedom.git
cd codefreedom
pip install -e .
```

## Verify

```bash
cf --help
# or
cf -h
```

You should see:

```text
usage: codefreedom [-h] {setup,run,manage} ...

Unified CLI for code agents.
LLM proxy routing, Docker sandboxing, profile management.

commands:
  setup (s)           One-time setup and configuration (init, config, deinit)
  run (r)             Daily workflows (agent, proxy, tools)
  manage (m)          Occasional maintenance (doctor, update, admin)
```

## Quick Start

```bash
cf setup init                    # Set up config
cf run proxy start               # Start the proxy
cf run agent claude-code         # Launch Claude Code
```

Or with short aliases:

```bash
cf s i                           # cf setup init
cf r px start                    # cf run proxy start
cf r ag cc                       # cf run agent claude-code
```

## Next Steps

- **[First Run](first-run.md)** — step-by-step walkthrough
- **[Agents](../features/claude-code.md)** — launch coding agents
- **[Proxy](../features/proxy.md)** — self-hosted LiteLLM proxy
- **[Tools](../features/tools.md)** — browser and API tools
