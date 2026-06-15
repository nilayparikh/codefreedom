# CodeFreedom

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](pyproject.toml)
[![Integration Tests](https://github.com/nilayparikh/codefreedom/actions/workflows/integration-test.yml/badge.svg)](https://github.com/nilayparikh/codefreedom/actions/workflows/integration-test.yml)
[![PyPI](https://img.shields.io/pypi/v/codefreedom.svg)](https://pypi.org/project/codefreedom/)

**Unified interface for all code agents. Simple LLM routing. Sandboxing just a click away.**

> **Full documentation:** [https://nilayparikh.github.io/codefreedom/](https://nilayparikh.github.io/codefreedom/)

## What is CodeFreedom?

CodeFreedom is a CLI that sits between you and your code agent (Claude Code, MiMoCode, OpenCode, etc.). It solves three problems:

1. **Model lock-in** -- switch models across providers without reconfiguring your agent.
2. **Environment chaos** -- isolated, reproducible sandboxed environments per project with GPU support.
3. **Config sprawl** -- profiles, proxy routing, and sandbox settings managed from one place (`~/.codefreedom`).

It orchestrates agents through their **publicly supported interfaces** (environment variables, CLI flags, API endpoints). No patching, no reverse-engineering.

## Supported Agents

| Agent | Alias | Description |
|-------|-------|-------------|
| **Claude Code** | `cc` | Anthropic's code agent |
| **MiMoCode** | `mc` | Xiaomi's code agent |
| **OpenCode** | `oc` | OpenCode code agent |

All agents share the same proxy, sandbox, and tooling layers.

## Quick Start

### Install

```bash
pip install codefreedom
```

### Pick a recipe and set up

```bash
# See available recipes
cf s i -l

# Plan + apply a recipe (recommended -- shows preview, prompts to confirm)
cf s i -pa costeffective-coding
```

A **recipe** is a pre-built configuration bundle that wires up proxy, profiles, and provider settings in one step. See [recipes/](recipes/) for options.

### Start the proxy and launch an agent

```bash
# Start the LiteLLM proxy (auto-starts browser tools)
cf r px start

# Launch your agent
cf r ag cc          # Claude Code
cf r ag mc          # MiMoCode
cf r ag oc          # OpenCode

# Or launch in a sandboxed container
cf r ag cc --sandbox
cf r ag cc --sandbox --cuda   # NVIDIA GPU
cf r ag cc --sandbox --rocm   # AMD GPU
```

### Common commands

| Command | What it does |
|---------|-------------|
| `cf s i -l` | List available recipes |
| `cf s i -pa <recipe>` | Plan + apply a recipe |
| `cf r px start` | Start proxy + tools |
| `cf r px stop` | Stop proxy + tools |
| `cf r px status` | Check proxy health |
| `cf r ag cc` | Launch Claude Code |
| `cf r ag mc` | Launch MiMoCode |
| `cf r ag oc` | Launch OpenCode |
| `cf run tools status` | Check tool container status |
| `cf manage admin backup` | Backup config |
| `cf manage doctor` | Diagnose issues |

See the [full documentation](https://nilayparikh.github.io/codefreedom/) for proxy setup, custom profiles, browser tools, and more.

## Features

| Feature | Details |
|---------|---------|
| LLM proxy | Self-hosted LiteLLM image (embedded PostgreSQL, multi-provider routing) |
| Agent launcher | Claude Code, MiMoCode, OpenCode -- local + sandbox modes |
| Sandboxing | Pre-configured containers (CPU, CUDA, ROCm) for each agent |
| Profiles | Model switching, env inheritance, isolation |
| Browser tools | Chrome (CDP + MCP), Camoufox stealth browser (MCP), GitHub MCP, Web Bridge |
| Backup & restore | Config backups with diff preview and selective restore |

## Requirements

- Python 3.10+
- Docker -- required for sandbox mode and the proxy
- Node.js -- for local mode (agent-specific)

## Principles

- **Just configuration.** Profiles are environment variables. Proxy routing is standard LiteLLM config.
- **Opt-in providers.** Set an API key to enable a provider. Leave it empty to disable. Nothing phones home.
- **All config in one place.** `~/.codefreedom` is the single source of truth.

## Data Privacy

CodeFreedom is a **local configuration tool**. It does not collect telemetry, connect to external servers, or store/transmit your prompts, code, or API keys.

All configuration lives on your machine in `~/.codefreedom/`. You are responsible for reviewing the privacy policies of every provider and tool you configure.

## Disclaimer

CodeFreedom is provided **"as is" without warranty of any kind**. Use at your own risk. See [NOTICE](NOTICE) for trademark and third-party disclaimers.

## License

Apache 2.0 -- see [LICENSE](LICENSE).
