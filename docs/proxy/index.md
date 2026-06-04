---
description: LiteLLM proxy overview, CLI commands, and environment setup.
---

# Proxy

CodeFreedom runs a [LiteLLM](https://docs.litellm.ai/) proxy between your code agent and LLM providers. One endpoint (`http://localhost:4000`), multiple backends — switch providers by changing environment variables, not code.

## Why LiteLLM

LiteLLM is an open-source proxy that translates between different LLM APIs. CodeFreedom uses it for:

- **Unified routing** — Claude Code talks to one URL. The proxy decides which provider handles each request.
- **Model aliases** — `CodeFreedom/Pro`, `CodeFreedom/Ultra`, etc. map to whichever provider you choose. Change the target without touching your agent config.
- **Retry and fallback** — automatic retries on timeouts and rate limits. Context-window fallbacks route to a larger model when a request is too big.
- **Spend tracking** — with a [PostgreSQL database](database.md), track costs across all providers from one dashboard.
- **Prometheus metrics** — request counts, latency, and token usage at `/metrics/`.

For the full LiteLLM reference, see the [LiteLLM docs](https://docs.litellm.ai/docs/simple_proxy).

## Quick Start

```bash
# Initialize proxy config files
codefreedom proxy init

# Set your API keys in ~/.codefreedom/.env.proxy.secrets
# (copy from ~/.codefreedom/.env.proxy.example)

# Start the proxy (native Python)
codefreedom proxy start

# Or start via Docker Compose
codefreedom proxy start --docker
```

The proxy is available at `http://localhost:4000`.

## CLI Reference

Short alias: `cf px` is equivalent to `codefreedom proxy`.

### Initialize

```bash
codefreedom proxy init              # Copy example configs to ~/.codefreedom/
```

Copies `config.yaml`, provider YAMLs, `docker-compose.yaml`, and `.env` examples into `~/.codefreedom/proxy/`. Skips if files already exist — delete existing configs first, or merge changes manually from the [bundled examples](https://github.com/nilayparikh/codefreedom/tree/main/src/codefreedom/examples/proxy/).

### Start

```bash
codefreedom proxy start             # Native Python (requires litellm package)
codefreedom proxy start --docker    # Docker Compose
codefreedom proxy start --port 4001 # Custom port
codefreedom proxy start --host 127.0.0.1  # Bind to localhost only
```

| Flag       | Default  | Description                              |
| ---------- | -------- | ---------------------------------------- |
| `--port`   | `4000`   | Proxy listen port                        |
| `--host`   | `0.0.0.0`| Bind address (`127.0.0.1` for local-only) |
| `--docker` | off      | Use Docker Compose instead of native      |

### Stop & Status

```bash
codefreedom proxy stop              # Stop Docker Compose container
codefreedom proxy status            # Show Docker Compose container status
```

These only work for Docker Compose mode. For native mode, stop with `Ctrl+C` or kill the process.

### Validate

```bash
codefreedom proxy validate          # Check config for missing keys, broken includes
```

Parses `config.yaml`, checks that included provider files exist, and warns about unset environment variables.

## Endpoints

| Endpoint                                      | Description                       |
| --------------------------------------------- | --------------------------------- |
| `http://localhost:4000/v1/chat/completions`   | OpenAI chat completions           |
| `http://localhost:4000/v1/models`             | List available models             |
| `http://localhost:4000/v1/messages`           | Anthropic messages (translated)   |
| `http://localhost:4000/metrics/`              | Prometheus metrics                |
| `http://localhost:4000/ui`                    | Admin UI (requires database)      |

Authentication uses a bearer token (`LITELLM_MASTER_KEY` from `.env.proxy.secrets`).

> **Auth errors in logs:** LiteLLM logs unauthenticated requests at ERROR level. This is normal — health checks and requests without the `Authorization` header will appear as errors. Set `LITELLM_LOG_LEVEL=WARNING` to reduce noise.

## Environment Files

The proxy loads two component-specific env files before the shared chain:

1. `~/.codefreedom/.env.proxy` — proxy settings (ports, aliases, base URLs)
2. `~/.codefreedom/.env.proxy.secrets` — API keys, master key

See the full [environment chain](environment.md) for how these merge with workspace and system env vars.

## File Layout

```
~/.codefreedom/
├── .env.proxy                  # Proxy settings (generated from .env.proxy.example)
├── .env.proxy.secrets          # API keys (generated from .env.proxy.secrets.example)
└── proxy/
    ├── docker-compose.yaml     # Docker Compose deployment
    └── config/
        ├── config.yaml         # Core LiteLLM config (aliases, retry, fallbacks)
        └── providers/          # One YAML per provider
            ├── deepseek.yaml
            ├── azure-foundry.yaml
            ├── nvidia.yaml
            ├── opencode-zen.yaml
            ├── openrouter.yaml
            ├── openai-compatible.yaml
            ├── anthropic-compatible.yaml
            └── local.yaml
```
