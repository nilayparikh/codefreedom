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
| Remote proxy | Configure clients to use a remote proxy via `proxy.remote_url` |
| Agent launcher | Claude Code, MiMoCode, OpenCode |
| Profiles | Model switching, env inheritance, isolation |
| Browser tools | Chrome (CDP + MCP), Camoufox stealth browser (MCP), GitHub MCP, Web Bridge |
| Remote tools | Configure MCP endpoints to use remote tool servers |
| Backup & restore | Config backups with diff preview and selective restore |

## Tools

CodeFreedom provides Docker-based tools that run as MCP servers. Each tool is managed via the unified tool group commands:

```bash
cf run tools start     # Start all tools
cf run tools stop      # Stop all tools
cf run tools restart   # Restart all tools
cf run tools status    # Show status of all tools
```

### Available Tools

| Tool | Image | Port | Purpose |
|------|-------|------|---------|
| **chrome** | `codefreedom:chrome-latest` | 9222 (CDP), 9223 (MCP) | Headless Chrome browser automation |
| **web** | `codefreedom:web-latest` | 8420 | Camoufox stealth browser for web search/scraping |
| **github** | `codefreedom:github-latest` | 8129 | GitHub MCP server for repo operations |
| **web-bridge** | `codefreedom:web-bridge-latest` | 8500 | SearXNG bridge for web search interception |
| **codebase-memory** | `codefreedom:codebase-memory-latest` | 8330 | Local code knowledge graph (14 MCP tools) |

#### Chrome

Headless Chromium browser for automation tasks. Provides both CDP (Chrome DevTools Protocol) and MCP endpoints.

- **CDP endpoint:** `http://127.0.0.1:9222`
- **MCP endpoint:** `http://127.0.0.1:9223/mcp`
- **Use case:** Browser automation, screenshots, DOM manipulation

#### Web (Camoufox)

Stealth browser based on Camoufox that bypasses anti-bot detection. Provides two MCP tools:

- **`web_search(query)`** — Search configured engines
- **`web_fetch(url)`** — Fetch a page (bypasses Cloudflare, Akamai, etc.)
- **MCP endpoint:** `http://127.0.0.1:8420/mcp`

#### GitHub

GitHub MCP server for repository operations (create issues, PRs, search code, etc.).

- **MCP endpoint:** `http://127.0.0.1:8129/mcp`
- **Required:** `GITHUB_PERSONAL_ACCESS_TOKEN` env var
- **Use case:** GitHub API interactions, code search, PR management

#### Web Bridge

SearXNG-shaped HTTP bridge that translates web search requests into MCP calls against the Camoufox web_search tool.

- **Endpoint:** `http://127.0.0.1:8500`
- **Use case:** LiteLLM's websearch_interception routes Claude Code's native WebSearch through this bridge

#### Codebase Memory

Local code knowledge graph that indexes your codebase and provides 14 MCP tools for code search, architecture analysis, and more.

- **MCP endpoint:** `http://127.0.0.1:8330/mcp`
- **Use case:** Code understanding, architecture analysis, finding functions/classes

### Configuring Tools for OpenCode

Tools are configured per-agent in `~/.codefreedom/config/profiles.yaml`. Each agent profile has a `tools` list that determines which tools are started when the agent launches.

#### Default OpenCode Tools

By default, OpenCode is configured with these tools:

```yaml
agents:
  open-code:
    profiles:
      default:
        tools:
          - github
          - codebase-memory
          - web
```

#### Adding More Tools

To add additional tools to OpenCode, edit `~/.codefreedom/config/profiles.yaml`:

```yaml
agents:
  open-code:
    profiles:
      default:
        tools:
          - github
          - codebase-memory
          - web
          - chrome          # Add Chrome for browser automation
          - web-bridge      # Add Web Bridge for search interception
```

#### Custom Profile with Tools

Create a custom profile with specific tools:

```yaml
agents:
  open-code:
    profiles:
      default:
        tools:
          - github
          - codebase-memory
          - web
      browser-focused:
        description: Profile with full browser automation
        tools:
          - github
          - codebase-memory
          - web
          - chrome
          - web-bridge
```

Then launch with:

```bash
cf r ag oc --profile browser-focused
```

### Tool Configuration Reference

Each tool can be configured in the `tools` section of `profiles.yaml`:

```yaml
tools:
  chrome:
    image: docker.io/nilayparikh/codefreedom:chrome-latest
    container_name: codefreedom-chrome
    port: 9222
    remote_url: http://192.168.1.5:9223  # Optional: use remote tool
  web:
    image: docker.io/nilayparikh/codefreedom:web-latest
    container_name: codefreedom-web
    port: 8420
  github:
    image: docker.io/nilayparikh/codefreedom:github-latest
    container_name: codefreedom-tools-github
    port: 8129
  web-bridge:
    image: docker.io/nilayparikh/codefreedom:web-bridge-latest
    container_name: codefreedom-web-bridge
    port: 8500
  codebase-memory:
    image: docker.io/nilayparikh/codefreedom:codebase-memory-latest
    container_name: codefreedom-tools-codebase-memory
    port: 8330
```

### Remote Tools

Configure MCP endpoints to use remote tool servers:

```bash
cf setup config tools chrome --remote-url http://192.168.1.5:9223
cf setup config tools web --remote-url http://192.168.1.5:8420
cf setup config tools github --remote-url http://192.168.1.5:8129
```

When a tool is configured remote, the local Docker container is not started — the remote endpoint is used verbatim.

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
