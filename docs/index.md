---
title: Getting Started
layout: default
nav_order: 1
permalink: /
---

# CodeFreedom

**Claude Code launcher and LiteLLM proxy — AI-augmented coding, anywhere.**

CodeFreedom gives you a single CLI tool (`codefreedom` / `cf`) that runs Claude Code natively or inside Docker with GPU passthrough, and manages a LiteLLM proxy for model routing to any provider.

---

## Getting Started

This guide walks you through installing and configuring CodeFreedom.

## Prerequisites

| Dependency             | Required For                | Installation                                               |
| ---------------------- | --------------------------- | ---------------------------------------------------------- |
| Python 3.10+           | CLI                         | `python3 --version`                                        |
| Docker                 | Docker mode + LiteLLM proxy | [docs.docker.com](https://docs.docker.com/engine/install/) |
| Node.js + `claude` CLI | Native/local mode           | `npm install -g @anthropic-ai/claude-code`                 |

## Installation

### From PyPI (Recommended)

```bash
pip install codefreedom
```

### From Source

```bash
git clone https://github.com/nilayparikh/codefreedom.git
cd codefreedom
pip install -e .
```

Verify the installation:

```bash
codefreedom --help
cf --help
```

## Initialize CodeFreedom

```bash
# Creates ~/.codefreedom/ with default profiles, schema, and proxy configs
codefreedom --init

# Force overwrite existing configs
codefreedom --init --force
```

This populates:

```
~/.codefreedom/
├── profiles/
│   ├── claude-code.json                  # Profile definitions
│   └── claude-code-profiles.schema.json  # JSON Schema
└── proxy/
    ├── docker-compose.yaml                # Docker Compose for LiteLLM
    └── config/
        ├── config.yaml                   # LiteLLM configuration
        └── providers/                    # Provider-specific configs
            ├── deepseek.yaml
            ├── azure-foundry.yaml
            ├── nvidia.yaml
            ├── local.yaml
            ├── openai-compatible.yaml
            ├── anthropic-compatible.yaml
            └── opencode-zen.yaml
```

## I want to use...

| Your use case                                 | Jump to                                                                                          |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| **Cloud APIs only** (DeepSeek, Azure, etc.)   | [Configuration → Adding a cloud provider](configuration.md#adding-a-cloud-provider)              |
| **Self-hosted OpenAI-compatible endpoint**    | [Configuration → OpenAI-compatible](configuration.md#adding-an-openai-compatible-endpoint)       |
| **Self-hosted Anthropic-compatible endpoint** | [Configuration → Anthropic-compatible](configuration.md#adding-an-anthropic-compatible-endpoint) |
| **Anthropic API directly** (no proxy)         | Use `codefreedom claude --native-models` or `codefreedom claude --profile bare`                  |

### Configuration

Edit the proxy config files in `~/.codefreedom/proxy/config/`:

```bash
# Edit the main proxy config
vim ~/.codefreedom/proxy/config/config.yaml

# Add provider-specific configs
vim ~/.codefreedom/proxy/config/providers/deepseek.yaml
vim ~/.codefreedom/proxy/config/providers/azure-foundry.yaml
```

Every provider is **opt-in**. If you don't configure it, it stays disabled.

Set your API keys as environment variables or in a `.env.secrets` file:

```bash
# Required
export LITELLM_MASTER_KEY="sk-your-proxy-key"

# Optional — set only for providers you use
export DEEPSEEK_API_KEY="sk-your-key"
export AZURE_FOUNDRY_API_KEY="your-key"
export NVIDIA_API_KEY="nvapi-your-key"
export OPENCODE_ZEN_API_KEY="your-key"
```

### Start the Proxy

```bash
# Via Docker Compose (recommended)
codefreedom proxy --up --docker

# Or natively (requires: pip install codefreedom[litellm])
codefreedom proxy --up

# Validate config before starting
codefreedom proxy --validate

# Check status
codefreedom proxy --status
```

Verify it's running:

```bash
curl http://localhost:4000/v1/models \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"
```

### Database (Optional)

The proxy runs **stateless by default** — no database, no Prisma, no persistence.
Model routing works out of the box. The LiteLLM Admin UI, spend tracking, and
key management require a PostgreSQL database.

To add PostgreSQL later, edit `~/.codefreedom/proxy/config/config.yaml`:

```yaml
# Uncomment and set:
database_url: "postgresql://user:pass@host:5432/litellm"
store_model_in_db: true
store_prompts_in_spend_logs: true
```

See [Proxy → Database](proxy.md#database-backends) for details.

To connect codefreedom to an existing PostgreSQL on a shared Docker network,
add this to `~/.codefreedom/proxy/docker-compose.yaml`:

```bash
networks:
  default:
    external: true
    name: your_shared_network
```

## Launching Claude Code

```bash
# Basic invocation (native mode, Flash model)
codefreedom claude

# Or with the short alias
cf cc

# Pick a model profile
cf cc --profile pro      # Implementation work
cf cc --profile ultra    # Architecture/planning
cf cc --profile bare     # Minimal — no model aliases

# Run inside a sandboxed Docker container
cf cc --sandbox

# Use native Anthropic /login auth (bypass proxy)
cf cc --native-models

# Pass arguments to Claude
cf cc -p "Write a function that..."
cf cc --resume "<session-id>"

# Manage the persistent container
cf cc --stop             # Stop and remove container
cf cc --status           # Show container status
cf cc --list-profiles    # List available profiles
```

## CLI Reference

All commands have short aliases. Use `codefreedom` or `cf` interchangeably.

| Command                  | Alias              | Action                       | Equivalent Docker Compose            |
| ------------------------ | ------------------ | ---------------------------- | ------------------------------------ |
| `cf proxy --up`          | `cf px --up`       | Start LiteLLM proxy (Docker) | `docker compose --profile all up -d` |
| `cf proxy --down`        | `cf px --down`     | Stop LiteLLM proxy           | `docker compose --profile all down`  |
| `cf proxy --status`      | `cf px --status`   | Show proxy status            | `docker compose ps`                  |
| `cf proxy --validate`    | `cf px --validate` | Validate LiteLLM config      | —                                    |
| `cf proxy --up --native` | —                  | Run litellm without Docker   | —                                    |
| `cf claude`              | `cf cc`            | Launch Claude Code (native)  | —                                    |
| `cf cc --sandbox`        | —                  | Run Claude Code in sandbox   | —                                    |
| `cf cc --profile NAME`   | —                  | Use named profile            | —                                    |
| `cf cc --stop`           | —                  | Stop Claude container        | —                                    |

## Profiles

Profiles are defined in `~/.codefreedom/profiles/claude-code.json`. The default profile routes through your local LiteLLM proxy at `http://localhost:4000`.

To create a custom profile, add an entry:

```json
{
  "profiles": {
    "my-remote": {
      "description": "Routes through a remote LiteLLM proxy",
      "env": {
        "ANTHROPIC_BASE_URL": "https://my-proxy.example.com",
        "ANTHROPIC_AUTH_TOKEN": "sk-remote-key",
        "CLAUDE_MODEL": "CodeFreedom/Ultra"
      }
    }
  }
}
```

Custom profiles automatically inherit all settings from `default` — you only need to specify what's different.

## Provider Setup

> **Not sure which providers you need?** See the [Configuration Guide](configuration.md)
> for step-by-step walkthroughs — including how to add OpenAI-compatible and
> Anthropic-compatible endpoints, and how to **disable providers you don't need**.

### DeepSeek (Default Cloud Provider)

Set your API key in `.env.secrets`:

```bash
DEEPSEEK_API_KEY=sk-your-deepseek-key
```

### Microsoft Foundry (Azure)

```bash
MICROSOFT_FOUNDRY_API_KEY=your-azure-key
```

### NVIDIA AI Endpoints

```bash
NVIDIA_API_KEY=nvapi-your-key
```

### OpenCode Zen (Free Tier)

```bash
OPENCODE_ZEN_API_KEY=your-zen-key
```

### Local (Self-Hosted)

If you have an OpenAI-compatible backend running locally, see
[Adding an OpenAI-compatible endpoint](configuration.md#adding-an-openai-compatible-endpoint)
in the Configuration Guide.

## Next Steps

- **[Configuration Guide](configuration.md)** — add OpenAI/Anthropic-compatible endpoints, cloud providers, model aliases
- [Proxy Configuration](proxy.md) — providers, model aliases, database setup
- [Claude Code Launcher](claude-code.md) — profiles, Docker lifecycle, advanced usage
