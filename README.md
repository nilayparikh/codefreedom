# CodeFreedom

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](pyproject.toml)

**Claude Code launcher and LiteLLM proxy — AI-augmented coding, anywhere.**

CodeFreedom gives you a single CLI tool (`codefreedom` / `cf`) that:

1. **Runs Claude Code** inside a persistent Docker container with GPU passthrough, profile-based model routing, and multi-session support.
2. **Manages a LiteLLM proxy** — stateless by default, with optional PostgreSQL for the Admin UI, spend tracking, and key management.
3. **Routes to any provider** — local self-hosted models, cloud APIs (DeepSeek, Azure, NVIDIA, OpenCode Zen), or any OpenAI/Anthropic-compatible endpoint.

## Why CodeFreedom?

CodeFreedom extracts the **LiteLLM proxy** and **Claude Code launcher** from the [`.init`](https://github.com/nilayparikh/spark-init) stack into a standalone, portable tool. Where `.init` is a full Docker Compose stack with PostgreSQL, observability, and llama.cpp backends, CodeFreedom is the lightweight companion you can install anywhere and use with any LiteLLM-compatible backend.

| Feature              | `.init`                 | `codefreedom`                             |
| -------------------- | ----------------------- | ----------------------------------------- |
| LiteLLM proxy        | ✅ (part of full stack) | ✅ (standalone, stateless)                |
| Claude Code launcher | ✅ (`claude-code.py`)   | ✅ (`codefreedom claude`)                 |
| PostgreSQL           | ✅ (bundled)            | ✅ (optional — connect external Postgres) |
| llama.cpp backends   | ✅ (bundled)            | ❌ (use .init for local inference)        |
| Observability        | ✅ (Grafana/Mimir/Loki) | ❌ (use .init)                            |
| pip installable      | ❌                      | ✅                                        |

## Quick Start

### Installation

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

### 1. Start the LiteLLM Proxy

```bash
# Copy the example config and environment files
cp -r litellm.examples/config litellm/
cp litellm.examples/.env.example .env
cp litellm.examples/.env.secrets.example .env.secrets

# Set your master key in .env.secrets (required)
# LITELLM_MASTER_KEY=sk-your-proxy-key

# Start the proxy (stateless — no database needed)
codefreedom proxy --up

# Or with Docker Compose directly
docker compose --profile all up -d
```

The proxy starts stateless — no database, no Prisma, just model routing.
To add PostgreSQL for the Admin UI, spend tracking, and key management,
see [LiteLLM Proxy → Database](docs/litellm.md#database-backends).

### 2. Launch Claude Code

```bash
# Default: Docker mode, Flash model
codefreedom claude

# Short alias
cf cc

# Pick a model profile
codefreedom claude --profile pro
codefreedom claude --profile ultra

# Run natively (no Docker)
codefreedom claude --local

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
├── claude | cc       Launch Claude Code
│   ├── --profile NAME       Model profile (default: 'default')
│   ├── --local              Run natively (no Docker)
│   ├── --stop               Stop the container
│   ├── --status             Show container status
│   └── --list-profiles      List available profiles
│
└── proxy | px         Manage LiteLLM proxy
    ├── --up                 Start the proxy (Docker)
    ├── --down               Stop the proxy
    ├── --status             Show proxy status
    ├── --validate           Validate LiteLLM config
    └── --up --native        Run litellm without Docker
```

## Profiles

Profiles control which model Claude Code uses and which API endpoint it routes through. Defined in `profiles/claude-code-profiles.json`.

| Profile   | Model               | Description                                       |
| --------- | ------------------- | ------------------------------------------------- |
| `default` | `CodeFreedom/Flash` | Base profile — routes through local LiteLLM proxy |
| `ultra`   | `CodeFreedom/Ultra` | Architecture, planning, complex reasoning         |
| `pro`     | `CodeFreedom/Pro`   | Bounded implementation, precise code writing      |
| `air`     | `CodeFreedom/Air`   | Mechanical scanning, large-file reading           |
| `bare`    | _(none)_            | Minimal — uses Anthropic's native auth            |

Create custom profiles by adding entries to `profiles/claude-code-profiles.json`.

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

- [Getting Started](docs/getting-started.md) — detailed setup guide
- [LiteLLM Proxy](docs/litellm.md) — configuration and provider setup
- [Claude Code Launcher](docs/claude-code.md) — profiles, Docker, and advanced usage

## Requirements

- Python 3.10+
- Docker (for Docker mode and LiteLLM proxy)
- NVIDIA Container Toolkit (for GPU passthrough)
- Node.js + `@anthropic-ai/claude-code` (for `--local` mode only)

## License

Apache 2.0 — see [LICENSE](LICENSE).
