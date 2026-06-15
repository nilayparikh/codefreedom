---
title: Getting Started
description: Install CodeFreedom and launch your first agent in five minutes.
---

Install CodeFreedom and launch your first agent in five minutes.

## What You'll Need

- **Python 3.10+** — for the CLI
- **Docker** — for proxy and sandbox containers
- **Docker Compose** — for multi-container setups

## Install

```bash
pip install codefreedom
```

## Quick Start

Four commands:

```bash
pip install codefreedom          # Install
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

## Available Agents

| Agent | Full name | Alias | Command |
| --- | --- | --- | --- |
| Claude Code | `claude-code` | `cc` | `cf r ag cc` |
| MiMo Code | `mimo-code` | `mc` | `cf r ag mc` |
| OpenCode | `open-code` | `oc` | `cf r ag oc` |

## Command Aliases

All commands have short aliases for faster workflows:

| Full command | Short form |
| --- | --- |
| `cf setup` | `cf s` |
| `cf run` | `cf r` |
| `cf manage` | `cf m` |
| `cf setup init` | `cf s i` |
| `cf setup config` | `cf s c` |
| `cf setup deinit` | `cf s di` |
| `cf run agent` | `cf r ag` |
| `cf run proxy` | `cf r px` |
| `cf run tools` | `cf r tl` |
| `cf manage doctor` | `cf m dr` |
| `cf manage update` | `cf m up` |
| `cf manage admin` | `cf m ad` |

## Next Steps

- **[First Run](first-run.md)** — step-by-step walkthrough
- **[Agents](../features/claude-code.md)** — launch coding agents
- **[Proxy](../features/proxy.md)** — self-hosted LiteLLM proxy
- **[Tools](../features/tools.md)** — browser and API tools
