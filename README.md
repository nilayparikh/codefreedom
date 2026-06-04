# CodeFreedom

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](pyproject.toml)
[![Integration Tests](https://github.com/nilayparikh/codefreedom/actions/workflows/integration-test.yml/badge.svg)](https://github.com/nilayparikh/codefreedom/actions/workflows/integration-test.yml)
[![PyPI](https://img.shields.io/pypi/v/codefreedom.svg)](https://pypi.org/project/codefreedom/)

**Unified interface for all code agents. Simple LLM routing. Sandboxing just a click away.**

CodeFreedom solves three problems:

1. **Model lock-in** — you want to switch models across providers without reconfiguring your code agent each time.
2. **Environment chaos** — you want isolated, reproducible environments per project with GPU support.
3. **Config sprawl** — you want profiles, proxy routing, and sandbox settings managed from one place (`~/.codefreedom`).

It does this by orchestrating code agents through their **publicly supported interfaces** (environment variables, CLI flags, API endpoints). No patching, no reverse-engineering.

### Supported Agents

| Agent       | Status     | Subcommand           | Notes                                       |
| ----------- | ---------- | -------------------- | ------------------------------------------- |
| Claude Code | ✅ Ready   | `codefreedom claude` | Local + sandbox modes, full profile support |
| Cursor      | 🚧 Roadmap | —                    | Coming — same profile + proxy pattern       |
| Codex       | 🚧 Roadmap | —                    | Coming — same profile + proxy pattern       |

The architecture is agent-agnostic: each agent gets a subcommand, profile, and routes through the same proxy. Claude Code is the first implementation.

## Principles

CodeFreedom integrates with code agents through their **publicly supported features only** — environment variables, CLI flags, config files, and API endpoints. No reverse-engineering, no patching, no vendor lock-in.

- **Just configuration.** Profiles are environment variables. Proxy routing is standard LiteLLM config.
- **Opt-in providers.** Set an API key to enable a provider. Leave it empty to disable. Nothing phones home by default.
- **All config in one place.** `~/.codefreedom` is the single source of truth for profiles, proxy settings, and sandbox configuration.
- **Trademarks belong to their owners.** See [NOTICE](NOTICE) for attributions.

## Disclaimer

**CodeFreedom is provided "as is" without warranty of any kind.** Use at your own risk.

- **Supported methods only.** CodeFreedom integrates with code agents exclusively through their publicly documented interfaces — environment variables, CLI flags, config files, and API endpoints. It does **not** reverse-engineer, patch, modify, or tamper with any code agent. No binary patching, no MITM, no internal API abuse.
- **Third-party responsibility.** CodeFreedom orchestrates upstream tools (LiteLLM, Claude Code, Docker, etc.) but does not control their behavior. You are responsible for evaluating the suitability, security, and terms of service of every upstream tool and provider you configure.
- **Security.** The proxy handles API keys and tokens. Sandbox mode mounts host directories (`~/.ssh`, `~/.gitconfig`) into containers. Configure these according to your organization's security policies.
- **No warranty.** This software is provided under the Apache 2.0 License without warranty or guarantee of any kind. The author is not liable for any damages arising from its use.
- **Trademarks.** CodeFreedom is not affiliated with, endorsed by, or sponsored by Anthropic, Microsoft, Anysphere, OpenAI, BerriAI, Docker, or any other third-party mentioned in this project. All trademarks belong to their respective owners.

## Features

| Feature             | codefreedom                                         |
| ------------------- | --------------------------------------------------- |
| LLM proxy           | ✅ Stateless model routing (Docker or native)       |
| Code agent launcher | ✅ `codefreedom claude` CLI                         |
| Sandboxing          | ✅ Pre-configured containers (CUDA, ROCm, Ubuntu)   |
| Profile management  | ✅ Model switching & isolation                      |
| Browser tools       | ✅ Chrome (CDP) + Camoufox (MCP) for web automation |
| PostgreSQL          | ✅ Optional — Admin UI, spend tracking              |
| pip installable     | ✅ `pip install codefreedom`                        |

## Quick Start

### Installation

**From PyPI (recommended):**

```bash
pip install codefreedom
```

**From source:**

```bash
git clone https://github.com/nilayparikh/codefreedom.git
cd codefreedom
pip install -e .
```

Now you can run `codefreedom` or `cf` from anywhere:

```bash
codefreedom --help
cf --help
```

### Initialize

```bash
# Creates ~/.codefreedom/ with default profiles and proxy configs
codefreedom --init

# Overwrite existing files
codefreedom --init --force
```

This creates:

```
~/.codefreedom/
├── profiles/
│   ├── claude-code.json                  # Profile definitions
│   └── claude-code.schema.json           # JSON Schema for validation
└── proxy/
    ├── docker-compose.yaml                # Docker Compose for LiteLLM
    └── config/
        ├── config.yaml                   # LiteLLM proxy configuration
        └── providers/                    # Provider-specific configs
            ├── deepseek.yaml
            ├── azure-foundry.yaml
            ├── nvidia.yaml
            ├── local.yaml
            ├── openai-compatible.yaml
            ├── anthropic-compatible.yaml
            └── opencode-zen.yaml
```

### 1. Start the Proxy

```bash
# Start via Docker Compose
codefreedom proxy start --docker

# Or start natively (requires: pip install codefreedom[litellm])
codefreedom proxy start

# Validate config
codefreedom proxy validate
```

The proxy starts stateless — no database, no Prisma, just model routing.
See [Proxy → Database](docs/proxy.md#database-backends) for PostgreSQL setup.

### 2. Launch a Code Agent

```bash
# Default: native mode with Flash model
codefreedom claude

# Pick a different built-in profile (bare = minimal, no model aliases)
codefreedom claude --profile bare

# Or use a custom profile you created in claude-code.json
codefreedom claude --profile my-profile

# Run in sandboxed Docker container
codefreedom claude --sandbox

# Use GPU images (with --sandbox)
codefreedom claude --sandbox --cuda   # NVIDIA GPU
codefreedom claude --sandbox --rocm   # AMD GPU

# Use native Anthropic /login auth (bypass proxy)
codefreedom claude --native-models

# List available profiles
codefreedom claude --list-profiles

# Manage the container
codefreedom claude --status
codefreedom claude --stop
```

Short aliases: `cf cc` is equivalent to `codefreedom claude`.

### 3. Pass Arguments Through

```bash
codefreedom claude -p "Explain this codebase"
codefreedom claude --resume "<session-id>"
codefreedom claude --profile my-profile --worktree feature-branch
```

## Sandbox Containers

Three pre-configured images (CUDA, ROCm, Ubuntu) on `docker.io/nilayparikh/codefreedom`. (Also available on `ghcr.io/nilayparikh/codefreedom` as a mirror.)
See [Sandbox Mode → Available Images](docs/claude-code/sandbox.md#available-images) for the full tag reference and Dockerfile examples.

## Browser Tools

CodeFreedom provides containerized browser tools for coding agents:

| Tool                           | Purpose                           | Interface             | Command                          |
| ------------------------------ | --------------------------------- | --------------------- | -------------------------------- |
| [Chrome](docs/tools/chrome.md) | Headed browser automation via CDP | `ws://localhost:9222` | `codefreedom tools chrome start` |
| [Camoufox](docs/tools/web.md)  | Stealth web search & scraping     | MCP on port 8420      | `codefreedom tools web start`    |

```bash
# Initialize and start Chrome
codefreedom tools chrome init
codefreedom tools chrome start

# Initialize and start Camoufox
codefreedom tools web init
codefreedom tools web start
```

See [Tools](docs/tools/index.md) for full documentation.

## CLI Reference

See [Architecture → CLI Design](docs/architecture.md#cli-design) for the full command tree.

## Profiles

Profiles control which model a code agent uses and which API endpoint it routes through. All profiles live in `~/.codefreedom/profiles/claude-code.json`.

| Profile   | Model               | Description                                      |
| --------- | ------------------- | ------------------------------------------------ |
| `default` | `CodeFreedom/Flash` | Base profile — routes through proxy              |
| `bare`    | _(default)_         | Minimal — no model aliases, routes through proxy |

Create custom profiles by editing `~/.codefreedom/profiles/claude-code.json`:

```json
{
  "profiles": {
    "my-profile": {
      "description": "Custom profile — override model and endpoint",
      "env": {
        "CLAUDE_MODEL": "CodeFreedom/Ultra",
        "ANTHROPIC_BASE_URL": "http://localhost:4000"
      }
    }
  }
}
```

A JSON Schema is provided at `~/.codefreedom/profiles/claude-code.schema.json`.

## Database (Optional)

The proxy runs **stateless by default** — no database, no Prisma, no persistence.
Model routing works out of the box.

| Backend            | Use Case                                           |
| ------------------ | -------------------------------------------------- |
| **None** (default) | Dev/CI — stateless model routing, zero persistence |
| **PostgreSQL**     | Admin UI, spend tracking, key management, teams    |

See [Proxy → Database](docs/proxy.md#database-backends) for setup.

## Documentation

- [Getting Started](docs/index.md) — Install, init, launch
- [Environment](docs/environment.md) — `.env` chain, variable interpolation, workspace overrides
- [Code Agents](docs/claude-code.md) — Profiles, sandbox mode, local mode
- [Proxy](docs/proxy.md) — Provider setup, database, configuration
- [Architecture](docs/architecture.md) — System design, data flow (Mermaid diagrams)
- [Browser Tools](docs/tools/index.md) — Chrome and Camoufox browser automation
- [VS Code](docs/vscode.md) — Proxy integration with VS Code extensions
- [Troubleshooting](docs/troubleshooting.md) — Common issues and diagnostics
- [License & Contributions](docs/license-contributions.md) — License, contributing guide

## Requirements

- Python 3.10+
- Docker — optional, for sandbox mode and Docker Compose proxy
- Node.js + `@anthropic-ai/claude-code` (for local mode only)

## License

Apache 2.0 — see [LICENSE](LICENSE).

---

_Claude Code is a trademark of Anthropic. VS Code is a trademark of Microsoft. Cursor is a trademark of Anysphere. Codex is a trademark of OpenAI. Other trademarks are property of their respective owners. See [NOTICE](NOTICE)._
