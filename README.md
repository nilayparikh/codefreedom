# CodeFreedom

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](pyproject.toml)
[![Integration Tests](https://github.com/nilayparikh/codefreedom/actions/workflows/integration-test.yml/badge.svg)](https://github.com/nilayparikh/codefreedom/actions/workflows/integration-test.yml)
[![PyPI](https://img.shields.io/pypi/v/codefreedom.svg)](https://pypi.org/project/codefreedom/)

**Unified interface for all code agents. Simple LLM routing. Sandboxing just a click away.**

CodeFreedom solves three problems:

1. **Model lock-in** — switch models across providers without reconfiguring your code agent.
2. **Environment chaos** — isolated, reproducible environments per project with GPU support.
3. **Config sprawl** — profiles, proxy routing, and sandbox settings managed from one place (`~/.codefreedom`).

It orchestrates code agents through their **publicly supported interfaces** (environment variables, CLI flags, API endpoints). No patching, no reverse-engineering.

> **Full documentation:** [https://nilayparikh.github.io/codefreedom/](https://nilayparikh.github.io/codefreedom/)

## Bring Your Own Agent

CodeFreedom works with any code agent that supports OpenAI-compatible or Anthropic-compatible APIs — Claude Code, Cursor, Codex CLI, VS Code extensions, and more. The architecture is agent-agnostic: each agent gets a subcommand, profile, and routes through the same proxy.

Currently, **Claude Code** and **MiMoCode** are the fully implemented agents. Adding a new agent is a matter of profile + subcommand — the proxy, sandbox, and tooling layers are shared.

## Web Search

Claude Code's built-in `WebSearch` requires Anthropic's internal login and silently fails for most users. The CodeFreedom proxy solves this with a built-in SearXNG-shaped bridge that routes every `WebSearch` call to a local Camoufox stealth browser — transparently, for any model. See [Web Search Interception](https://nilayparikh.github.io/codefreedom/proxy/websearch-interception/).

## Principles

- **Just configuration.** Profiles are environment variables. Proxy routing is standard LiteLLM config.
- **Opt-in providers.** Set an API key to enable a provider. Leave it empty to disable. Nothing phones home by default.
- **All config in one place.** `~/.codefreedom` is the single source of truth.

## Data Privacy

CodeFreedom is a **local configuration tool**. It does not:

- Collect telemetry, analytics, or usage data.
- Connect to any external servers.
- Store or transmit your prompts, code, or API keys.

All configuration lives on your machine in `~/.codefreedom/`. CodeFreedom generates config files that you use with third-party tools (LiteLLM, Claude Code, Docker, etc.). You are responsible for reviewing the privacy policies and terms of service of every provider and tool you configure.

> **Free model endpoints** — Free tiers may log requests, retain conversation data, or use inputs for model improvement. Always read the provider's privacy policy before sending sensitive code. See [Free Models](https://nilayparikh.github.io/codefreedom/free-models/) for a guide.

## Disclaimer

CodeFreedom is provided **"as is" without warranty of any kind**. Use at your own risk.

- **Supported methods only.** CodeFreedom integrates with code agents exclusively through their publicly documented interfaces — environment variables, CLI flags, config files, and API endpoints. It does **not** reverse-engineer, patch, modify, or tamper with any code agent.
- **Third-party responsibility.** CodeFreedom orchestrates upstream tools (LiteLLM, Claude Code, Docker, etc.) but does not control their behavior. You are responsible for evaluating the suitability, security, and terms of service of every upstream tool and provider you configure.
- **Security.** The proxy handles API keys and tokens. Sandbox mode mounts host directories (`~/.ssh`, `~/.gitconfig`) into containers. Configure these according to your organization's security policies.
- **Trademarks.** CodeFreedom is not affiliated with, endorsed by, or sponsored by Anthropic, Microsoft, Anysphere, OpenAI, BerriAI, Docker, or any other third party mentioned in this project. All trademarks belong to their respective owners. See [NOTICE](NOTICE).

## Quick Start

### Install

```bash
pip install codefreedom
```

### Initialize

```bash
cf setup init
```

Creates `~/.codefreedom/` with default profiles, proxy configs, and provider templates.

### Launch

```bash
# Launch Claude Code through the proxy
codefreedom run agent claude-code

# Launch in a sandboxed container
codefreedom run agent claude-code --sandbox

# Use GPU images
codefreedom run agent claude-code --sandbox --cuda   # NVIDIA
codefreedom run agent claude-code --sandbox --rocm   # AMD
```

Short aliases: `cf run agent claude-code` is equivalent to `codefreedom run agent claude-code`.

See the [Getting Started guide](https://nilayparikh.github.io/codefreedom/) for proxy setup, custom profiles, browser tools, and more.

## Features

| Feature             | Details                                                                                     |
| ------------------- | ------------------------------------------------------------------------------------------- |
| LLM proxy           | Self-hosted `codefreedom:litellm-latest` image (embedded PostgreSQL, multi-provider routing)|
| Code agent launcher | `codefreedom run agent claude-code` CLI -- local + sandbox modes                            |
| Sandboxing          | Pre-configured containers (CUDA, ROCm, Ubuntu)                                              |
| Profile management  | Model switching, env inheritance, isolation                                                 |
| Browser tools       | Chrome (CDP) + Camoufox (MCP) for web automation                                            |
| Backup & restore    | Config backups with diff preview and selective restore                                      |

## Requirements

- Python 3.10+
- Docker -- required for sandbox mode and the proxy
- Node.js + `@anthropic-ai/claude-code` -- for local mode only

## License

Apache 2.0 -- see [LICENSE](LICENSE).

---

_Claude Code is a trademark of Anthropic. VS Code is a trademark of Microsoft. Cursor is a trademark of Anysphere. Codex is a trademark of OpenAI. Other trademarks are property of their respective owners. See [NOTICE](NOTICE)._
