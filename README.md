# CodeFreedom

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](pyproject.toml)
[![CI](https://github.com/nilayparikh/codefreedom/actions/workflows/ci.yml/badge.svg)](https://github.com/nilayparikh/codefreedom/actions/workflows/ci.yml)
[![Trivy Security Scan](https://github.com/nilayparikh/codefreedom/actions/workflows/trivy.yml/badge.svg)](https://github.com/nilayparikh/codefreedom/actions/workflows/trivy.yml)
[![PyPI](https://img.shields.io/pypi/v/codefreedom.svg)](https://pypi.org/project/codefreedom/)
[![Downloads](https://static.pepy.tech/badge/codefreedom)](https://pepy.tech/project/codefreedom)
[![Docker Hub](https://img.shields.io/badge/Docker%20Hub-nilayparikh%2Fcodefreedom-2496ED?logo=docker&logoColor=white)](https://hub.docker.com/r/nilayparikh/codefreedom)
[![GHCR Image](https://img.shields.io/badge/GHCR-ghcr.io%2Fnilayparikh%2Fcodefreedom-2496ED?logo=docker&logoColor=white)](https://ghcr.io/nilayparikh/codefreedom)

**Unified interface for all code agents. Simple LLM routing. Profile management.**

> **Full documentation:** [https://nilayparikh.github.io/codefreedom/](https://nilayparikh.github.io/codefreedom/)

## What is CodeFreedom?

### The Problem

AI code agents are powerful, but the ecosystem around them is fragmented. Each agent carries its own configuration, model preferences, and runtime dependencies. There is no portable layer that lets you move between agents, models, or providers without starting over.

That fragmentation creates three compounding risks:

- **Vendor lock-in** -- choosing a provider today can constrain your choices tomorrow. As the model landscape evolves, being tied to one ecosystem means missing better capabilities, pricing, or reliability from competitors.
- **Unmanaged cost** -- without visibility across providers, there is no way to route work to the most cost-effective model. Token spend grows unchecked because switching providers is a manual, error-prone process.
- **Complexity as a barrier** -- setting up proxies and provider integrations demands infrastructure expertise. Developers who should be building products spend time plumbing tooling, or avoid the tools altogether.

### The Solution

CodeFreedom is a CLI that sits between you and your code agent (Claude Code, MiMoCode, OpenCode, etc.). It provides a portable abstraction layer so you can:

1. **Switch models and providers** -- change your backend without reconfiguring your agent.
2. **Manage everything from one place** -- profiles, proxy routing, and tool settings live in `~/.codefreedom`.

It orchestrates agents through their **publicly supported interfaces** (environment variables, CLI flags, API endpoints). No patching, no reverse-engineering.

## Supported Agents

| Agent | Alias | Description |
|-------|-------|-------------|
| **Claude Code** | `cc` | Anthropic's code agent |
| **MiMo Code** | `mc` | Xiaomi's code agent |
| **OpenCode** | `oc` | OpenCode code agent |
| **Pi Code** | `pc` | Earendil's code agent with extension-based model discovery |
| **Codex** | `cx` | OpenAI's code agent with 0-click proxy config |

All agents share the same proxy and tooling layers.

## Video Walkthrough

[![Video Walkthrough](https://img.youtube.com/vi/6tgVffZwSrU/maxresdefault.jpg)](https://www.youtube.com/watch?v=6tgVffZwSrU)

## Quick Start

### Install

```bash
uv tool install codefreedom              # Recommended (uv)
# or
pip install codefreedom                  # Alternative (pip)
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
| `cf r ag mc` | Launch MiMo Code |
| `cf r ag oc` | Launch OpenCode |
| `cf r ag pc` | Launch Pi Code |
| `cf r ag cx` | Launch Codex |
| `cf run tools status` | Check tool container status |
| `cf manage admin backup` | Backup config |
| `cf manage doctor` | Diagnose issues |

See the [full documentation](https://nilayparikh.github.io/codefreedom/) for proxy setup, custom profiles, browser tools, and more.

## Features

| Feature | Details |
|---------|---------|
| LLM proxy | Self-hosted LiteLLM image (embedded PostgreSQL, multi-provider routing) |
| Agent launcher | Claude Code, MiMoCode, OpenCode |
| Profiles | Model switching, env inheritance, isolation |
| Browser tools | Chrome (CDP + MCP), Camoufox stealth browser (MCP), GitHub MCP, Web Bridge |
| Backup & restore | Config backups with diff preview and selective restore |

## Requirements

- Python 3.10+
- Docker -- required for the proxy
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
