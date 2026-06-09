---
title: Proxy
description: Self-hosted LLM proxy — one endpoint, multiple AI providers.
---

# Proxy

The proxy is a local server (`localhost:4000`) that routes your code agent's requests to AI providers. One endpoint, multiple backends.

## Why Use It

- **Unified routing** — Claude Code talks to one URL. The proxy decides which provider handles each request.
- **Model aliases** — `CodeFreedom/Pro`, `CodeFreedom/Ultra` map to whichever provider you choose.
- **Retry and fallback** — automatic retries on failures. Route to a larger model when context is too big.
- **Switch providers** — change the target without touching your agent config.

## Quick Start

```bash
cf init recipe                       # Install _default recipe (creates proxy config)
codefreedom proxy start              # Start the proxy
codefreedom proxy status             # Check it's running
```

### What It Looks Like

```bash
$ codefreedom proxy start
Pulling proxy...
Starting proxy...
[OK] Proxy ready at http://localhost:4000
```

## Commands

```bash
codefreedom proxy start              # Start
codefreedom proxy stop               # Stop
codefreedom proxy restart            # Restart (preserves state)
codefreedom proxy status             # Check status
codefreedom proxy validate           # Check config
```

Short alias: `cf px` = `codefreedom proxy`.

### Override Port

```bash
codefreedom proxy start --port 4001  # Use port 4001 instead of 4000
codefreedom proxy start --host 127.0.0.1  # Bind to localhost only
```

## How It Routes

```
Claude Code → localhost:4000 → Your chosen AI provider
```

The proxy reads provider config from `~/.codefreedom/proxy/config/providers/`. Each provider is a YAML file. Comment out a line to disable it.

## Model Aliases

Friendly names that map to real models. Change the alias to switch providers:

```bash
# In ~/.codefreedom/.env.proxy
LITELLM_MODEL_ALIAS_BEST="DeepSeek/DeepSeek-V4-Pro"
LITELLM_MODEL_ALIAS_FABLE="DeepSeek/DeepSeek-V4-Pro"
LITELLM_MODEL_ALIAS_SONNET="Azure/GPT-5.4-Mini"
LITELLM_MODEL_ALIAS_OPUS="DeepSeek/DeepSeek-V4-Pro"
LITELLM_MODEL_ALIAS_HAIKU="NVIDIA/DeepSeek-V4-Flash"
LITELLM_MODEL_ALIAS_SONNET_1M="Azure/GPT-5.4-Mini"
LITELLM_MODEL_ALIAS_OPUS_1M="DeepSeek/DeepSeek-V4-Pro"
LITELLM_MODEL_ALIAS_OPUSPLAN="DeepSeek/DeepSeek-V4-Pro"
```

Then in Claude Code, reference these aliases via profile selection (e.g. `codefreedom claude --profile best` or `codefreedom claude --profile sonnet`).

## Add a Provider

1. Add your API key to `~/.codefreedom/.env.proxy.secrets`
2. Uncomment the provider in `~/.codefreedom/proxy/config/config.yaml`
3. Restart: `codefreedom proxy restart`

See [Providers](../recipes/providers/index.md) for step-by-step guides for each provider.

## Endpoints

| Endpoint                                    | What It Does                    |
| ------------------------------------------- | ------------------------------- |
| `http://localhost:4000/v1/chat/completions` | OpenAI chat completions         |
| `http://localhost:4000/v1/models`           | List available models           |
| `http://localhost:4000/v1/messages`         | Anthropic messages (translated) |
| `http://localhost:4000/metrics/`            | Prometheus metrics              |

## Stateless by Default

No database needed. The proxy works out of the box. Optional PostgreSQL unlocks spend tracking and the admin dashboard.

## Auth Errors in Logs

LiteLLM logs unauthenticated requests at `ERROR` level — this is normal. Health checks and requests without the `Authorization` header appear as errors.

To reduce noise:

```bash
export LITELLM_LOG_LEVEL=WARNING
```
