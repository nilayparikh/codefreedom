---
title: costeffective-coding
description: Cloud-only inference recipe — Azure Foundry, OpenCode Zen, OpenRouter via LiteLLM proxy.
---

## Overview

Cloud-only recipe. Routes through Azure AI Foundry, OpenCode Zen, and OpenRouter. No local model backends.

```bash
cf s i -pa costeffective-coding
```

## Providers

### Azure Foundry

Routes to Azure AI Foundry / Azure OpenAI deployments.

| Variable | Description | Example |
| --- | --- | --- |
| `MICROSOFT_FOUNDRY_API_BASE` | Azure AI Foundry workspace endpoint | `https://<ws>.services.ai.azure.com/openai/v1` |
| `MICROSOFT_FOUNDRY_API_KEY` | Azure AI Foundry API key | `sk-...` |

**Models:**

| Model | ID | Context |
| --- | --- | --- |
| GPT-5.5 | `openai/gpt-5.5` | 1,050K |
| GPT-5.4 | `openai/gpt-5.4` | 1,050K |
| GPT-5.4-Mini | `openai/gpt-5.4-mini` | 400K |
| GPT-5.4-Nano | `openai/gpt-5.4-nano` | 400K |

All models support reasoning, vision, streaming, and tool use.

### OpenCode Zen

Free-tier and subscription models via OpenCode.

| Variable | Description | Default |
| --- | --- | --- |
| `OPENCODE_ZEN_API_KEY` | OpenCode API key | — |
| `OPENCODE_ZEN_BASE_URL` | Zen free-tier endpoint | `https://opencode.ai/zen/v1` |
| `OPENCODE_GO_BASE_URL` | GO subscription endpoint | `https://opencode.ai/zen/go/v1` |
| `OPENCODE_GO_ANTHROPIC_BASE_URL` | GO Anthropic-format endpoint | `https://opencode.ai/zen/go` |

**Free models (Zen):**

| Model | ID | Context |
| --- | --- | --- |
| MiMo-V2.5 | `openai/mimo-v2.5-free` | 1,000K |
| DeepSeek-V4-Flash | `openai/deepseek-v4-flash-free` | 1,000K |

Free models have a 12-hour cooldown after hitting rate limits.

**Subscription models (GO):**

| Model | ID | API Format | Context |
| --- | --- | --- | --- |
| MiniMax-M3 | `anthropic/minimax-m3` | Anthropic | 512K |
| Qwen3.7-Max | `anthropic/qwen3.7-max` | Anthropic | 1,000K |
| Qwen3.7-Plus | `anthropic/qwen3.7-plus` | Anthropic | 1,000K |
| DeepSeek-V4-Flash | `openai/deepseek-v4-flash` | OpenAI | 1,000K |
| Kimi-K2.7 | `openai/kimi-k2.7` | OpenAI | 262K |
| MiMo-V2.5 | `openai/mimo-v2.5` | OpenAI | 1,000K |
| MiMo-V2.5-Pro | `openai/mimo-v2.5-pro` | OpenAI | 1,000K |

### OpenRouter

Multi-provider access via OpenRouter.

| Variable | Description |
| --- | --- |
| `OPENROUTER_API_KEY` | OpenRouter API key |

**Models:**

| Model | ID | Context |
| --- | --- | --- |
| DeepSeek-V4-Pro | `openrouter/deepseek/deepseek-v4-pro` | 1,000K |
| DeepSeek-V4-Flash | `openrouter/deepseek/deepseek-v4-flash` | 1,000K |
| MiMo-V2.5 | `openrouter/xiaomi/mimo-v2.5` | 1,000K |
| MiMo-V2.5-Pro | `openrouter/xiaomi/mimo-v2.5-pro` | 1,000K |
| Qwen3.7-Plus | `openrouter/qwen/qwen3.7-plus` | 1,000K |
| Qwen3.7-Max | `openrouter/qwen/qwen3.7-max` | 1,000K |
| MiniMax-M3 | `openrouter/minimax/minimax-m3` | 1,000K |
| Kimi-K2.7 | `openrouter/moonshotai/kimi-k2.7` | 1,000K |
| FreeRouter | `openrouter/openrouter/free` | 256K |

FreeRouter routes to OpenRouter's free model pool. All other models pin to a specific provider (`only: ["deepseek"]`) with no fallbacks.

## Model Aliases

Claude Code uses alias names. The proxy maps them to model groups:

| Alias | Default Model | Behavior |
| --- | --- | --- |
| `fable` | Qwen3.7-Max | Hardest/longest tasks |
| `opus` | Qwen3.7-Plus | Complex reasoning |
| `sonnet` | DeepSeek-V4-Pro | Daily coding |
| `haiku` | DeepSeek-V4-Flash | Fast/simple tasks |
| `custom` | DeepSeek-V4-Flash | User's choice |

Override aliases via `LITELLM_MODEL_ALIAS_*` env vars.

## Required Secrets

| Secret | Description | How to get |
| --- | --- | --- |
| `PROXY_API_KEY` | Proxy auth key | `openssl rand -hex 32` (default: `sk-codefreedom-local`) |
| `MICROSOFT_FOUNDRY_API_KEY` | Azure Foundry API key | Azure AI Foundry portal |
| `OPENCODE_ZEN_API_KEY` | OpenCode API key | OpenCode dashboard |
| `OPENROUTER_API_KEY` | OpenRouter API key | <https://openrouter.ai/keys> |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | GitHub token for MCP | <https://github.com/settings/tokens> |

Set as machine env vars with `CF_CLI_` prefix or run the setup script:

```bash
bash ~/.codefreedom/scripts/costeffective-coding/setup-secrets.sh
```

## Agent Profiles

### Claude Code

Routes through the proxy. Environment variables set `ANTHROPIC_BASE_URL=http://localhost:4000` and model aliases.

| Profile | Description |
| --- | --- |
| `default` | Base profile with full alias set |
| `bare` | Minimal — no aliases, no preferences |
| `ui-ux` | Vision-capable models for frontend/design work |

### MiMo Code

Proxy auto-config: reads `PROXY_BASE_URL` and `PROXY_API_KEY`, generates `mimocode.json`.

| Profile | Description |
| --- | --- |
| `default` | Base profile with tools |
| `bare` | Minimal — pure mimo mode, no proxy |
| `ui-ux` | Image attachment support, question tool |

### OpenCode

Proxy auto-config: reads `PROXY_BASE_URL` and `PROXY_API_KEY`, generates `opencode.json`.

| Profile | Description |
| --- | --- |
| `default` | Base profile with tools |
| `bare` | Minimal — no proxy config |
| `ui-ux` | Experimental features |

## Tools

Inherited from `_default`:

| Tool | Image | Port | Purpose |
| --- | --- | --- | --- |
| Chrome | `codefreedom:chrome-latest` | 9222 (CDP), 9223 (MCP) | Headless browser automation |
| Web | `codefreedom:web-latest` | 8420 | Camoufox stealth browser for web scraping |
| GitHub | `codefreedom:github-latest` | 8129 | GitHub MCP server for repo operations |
| Web Bridge | `codefreedom:web-bridge-latest` | 8500 | SearXNG bridge for web search interception |
| Codebase Memory | `codefreedom:codebase-memory-latest` | 8330 | Local code knowledge graph (14 MCP tools) |

### Default Tools for OpenCode

OpenCode is configured with these default tools:

| Tool | Description |
| --- | --- |
| GitHub | GitHub MCP server for repo operations |
| Codebase Memory | Local code knowledge graph (14 MCP tools) |
| Web | Camoufox stealth browser for web search/scraping |

To add more tools, edit `~/.codefreedom/config/profiles.yaml`:

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

See [Tools](https://github.com/nilayparikh/codefreedom#tools) for the full list of available tools and configuration options.

## Proxy Configuration

The LiteLLM proxy runs at `localhost:4000` via Docker Compose.

**Key settings:**

| Setting | Value |
| --- | --- |
| Routing strategy | `simple-shuffle` |
| Retries | 3 |
| Rate limit cooldown | Immediate (0 failures tolerated) |
| Timeout retries | 5 |
| Auth error retries | 2 |
| Drop unsupported params | Yes |
| Anthropic → OpenAI translation | Yes |
| Prometheus metrics | `/metrics/` |
| Embedded PostgreSQL | 18.4 (Unix socket only) |

**Callbacks:**

- `prometheus` — metrics export
- `websearch_interception` — routes WebSearch tool calls to web-bridge
- `reasoning-efforts` — translates reasoning level strings per model
- `system-message-merger` — merges system messages for local models
- `image-router` — routes image-only requests to vision-capable models

## Files Deployed

```text
~/.codefreedom/
├── config/
│   ├── override.yaml           # User overrides (vars, common, tools, …)
│   ├── profiles.yaml           # Unified agent + tool profiles
│   └── proxy/
│       ├── docker-compose.yaml  # Container orchestration
│       └── config/
│           ├── config.yaml          # LiteLLM main config
│           ├── providers/
│           │   ├── azure-foundry.yaml
│           │   ├── opencode.yaml
│           │   └── openrouter.yaml
│           └── plugins/
│               └── reasoning-efforts/
│                   └── reasoning-efforts-mapping.yaml
└── scripts/
    └── costeffective-coding/
        ├── setup-secrets.sh
        └── setup-secrets.ps1
```

Secrets are sourced from `CF_CLI_*` machine environment variables — no
`.env.*.secrets` files are created or read by the recipe flow.

## Bind Address & Remote Access

All services (proxy and tools) bind to `0.0.0.0` by default, making them accessible from any network interface. This allows remote clients to connect using the host's IP address.

To restrict to loopback-only (local access only):

```bash
# Via CLI
cf setup config bind --address 127.0.0.1

# Or via override.yaml
common:
  bind_address: "127.0.0.1"

# Or via env var
export CF_CLI_BIND_ADDRESS=127.0.0.1
```

**Remote proxy:** Configure clients to use a remote proxy instead of the local one:

```bash
cf setup config proxy --remote-url http://192.168.1.5:4000
```

**Remote tools:** Configure MCP to use remote tool endpoints:

```bash
cf setup config tools chrome --remote-url http://192.168.1.5:9223
cf setup config tools web --remote-url http://192.168.1.5:8420
cf setup config tools github --remote-url http://192.168.1.5:8129
```

When a component is configured remote, local lifecycle commands (`start`/`stop`/`restart`) are refused — use `--local` to override.
