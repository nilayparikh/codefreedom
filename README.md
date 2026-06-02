# CodeFreedom

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](pyproject.toml)
[![Integration Tests](https://github.com/nilayparikh/codefreedom/actions/workflows/integration-test.yml/badge.svg)](https://github.com/nilayparikh/codefreedom/actions/workflows/integration-test.yml)
[![PyPI](https://img.shields.io/pypi/v/codefreedom.svg)](https://pypi.org/project/codefreedom/)

**Claude Code launcher and LiteLLM proxy — AI-augmented coding, anywhere.**

CodeFreedom gives you a single CLI tool (`codefreedom` / `cf`) that:

1. **Runs Claude Code** natively or inside a Docker container with GPU passthrough, profile-based model routing, and multi-session support.
2. **Manages a LiteLLM proxy** — stateless by default, with optional PostgreSQL for the Admin UI, spend tracking, and key management.
3. **Routes to any provider** — local self-hosted models, cloud APIs (DeepSeek, Azure, NVIDIA, OpenCode Zen), or any OpenAI/Anthropic-compatible endpoint.

## Features

| Feature              | codefreedom                                 |
| -------------------- | ------------------------------------------- |
| LiteLLM proxy        | ✅ Standalone, stateless proxy              |
| Claude Code launcher | ✅ `codefreedom claude` CLI                 |
| PostgreSQL           | ✅ Optional — connect any external Postgres |
| pip installable      | ✅ `pip install codefreedom`                |

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
│   └── claude-code-profiles.schema.json  # JSON Schema for validation
└── proxy/
    ├── docker-compose.yml                # Docker Compose for LiteLLM
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

### 1. Start the LiteLLM Proxy

```bash
# Edit ~/.codefreedom/proxy/config/config.yaml to configure providers
# Set LITELLM_MASTER_KEY in your environment

# Start via Docker Compose
codefreedom proxy --up --docker

# Or start natively (requires: pip install codefreedom[litellm])
codefreedom proxy --up

# Validate config
codefreedom proxy --validate
```

The proxy starts stateless — no database, no Prisma, just model routing.
See [LiteLLM Proxy → Database](docs/litellm.md#database-backends) for PostgreSQL setup.

### 2. Launch Claude Code

```bash
# Default: native mode with Flash model
codefreedom claude

# Short alias
cf cc

# Pick a model profile
codefreedom claude --profile pro
codefreedom claude --profile ultra

# Run in sandboxed Docker container
codefreedom claude --sandbox

# Use native Anthropic /login auth (bypass proxy)
codefreedom claude --native-models

# List available profiles
codefreedom claude --list-profiles

# Manage the container
codefreedom claude --status
codefreedom claude --stop
```

### 3. Pass Arguments to Claude

```bash
cf cc -p "Explain this codebase"
cf cc --resume "<session-id>"
cf cc --profile pro --worktree feature-branch
```

## CLI Reference

```
codefreedom | cf
│
├── --init                    Initialize ~/.codefreedom/ with default profiles
│   └── --force               Overwrite existing configs
│
├── claude | cc               Launch Claude Code
│   ├── --profile NAME        Model profile (default: 'default')
│   ├── --sandbox             Run in sandboxed Docker container
│   ├── --native-models       Use native Anthropic /login auth (bypass proxy)
│   ├── --stop                Stop the container
│   ├── --status              Show container status
│   └── --list-profiles       List available profiles
│
└── proxy | px                Manage LiteLLM proxy
    ├── --up                  Start the proxy (default: native)
    ├── --up --docker         Start via Docker Compose
    ├── --down                Stop the proxy
    ├── --status              Show proxy status
    └── --validate            Validate LiteLLM config
```

## Profiles

Profiles control which model Claude Code uses and which API endpoint it routes through. Defined in `~/.codefreedom/profiles/claude-code.json`.

| Profile   | Model               | Description                                              |
| --------- | ------------------- | -------------------------------------------------------- |
| `default` | `CodeFreedom/Flash` | Base profile — routes through LiteLLM proxy              |
| `bare`    | _(default)_         | Minimal — no model aliases, routes through LiteLLM proxy |

Create custom profiles by editing `~/.codefreedom/profiles/claude-code.json`:

```json
{
  "profiles": {
    "my-custom": {
      "description": "Custom profile — override model and endpoint",
      "env": {
        "CLAUDE_MODEL": "CodeFreedom/Ultra",
        "ANTHROPIC_BASE_URL": "http://localhost:4000"
      }
    }
  }
}
```

A JSON Schema is provided at `~/.codefreedom/profiles/claude-code-profiles.schema.json`.

## Database (Optional)

The proxy runs **stateless by default** — no database, no Prisma, no persistence.
Model routing works out of the box.

| Backend            | Use Case                                           |
| ------------------ | -------------------------------------------------- |
| **None** (default) | Dev/CI — stateless model routing, zero persistence |
| **PostgreSQL**     | Admin UI, spend tracking, key management, teams    |

See [LiteLLM Proxy → Database](docs/litellm.md#database-backends) for setup.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    codefreedom CLI                        │
│  codefreedom claude  |  codefreedom proxy                │
└──────────┬───────────────────────┬───────────────────────┘
           │                       │
           ▼                       ▼
   ┌───────────────┐     ┌─────────────────┐
   │ Claude Code   │     │  LiteLLM Proxy  │
   │  (Docker)     │────▶│   (Docker)      │
   │  GPU passthru │     │   :4000          │
   └───────────────┘     └────────┬────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
              ┌──────────┐ ┌──────────┐ ┌──────────┐
              │ DeepSeek │ │  Azure   │ │  DGX     │
              │  (cloud) │ │ (cloud)  │ │ (local)  │
              └──────────┘ └──────────┘ └──────────┘
```

## Documentation

- [Getting Started](https://nilayparikh.github.io/codefreedom/getting-started) — detailed setup guide
- [LiteLLM Proxy](https://nilayparikh.github.io/codefreedom/litellm) — configuration and provider setup
- [Claude Code Launcher](https://nilayparikh.github.io/codefreedom/claude-code) — profiles, Docker, and advanced usage

## Requirements

- Python 3.10+
- Docker (for Docker mode and LiteLLM proxy)
- Node.js + `@anthropic-ai/claude-code` (for native/local mode only)

## License

Apache 2.0 — see [LICENSE](LICENSE).
