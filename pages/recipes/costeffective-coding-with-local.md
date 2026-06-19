---
title: costeffective-coding-with-local
description: Cloud + local inference recipe — Azure Foundry, OpenCode Zen, OpenRouter, and local backends via LiteLLM proxy.
---

## Overview

Everything in `costeffective-coding`, plus local model backends (Qwen models via Ollama-compatible servers). Routes cloud and local inference through the same LiteLLM proxy.

```bash
cf s i -pa costeffective-coding-with-local
```

## What's Added

This recipe extends `costeffective-coding` with:

- **Local provider** — two Qwen models on separate ports
- **Local secrets** — `LOCAL_M_API_KEY` and `LOCAL_S_API_KEY`
- **Custom alias** — `custom` maps to `Qwen3.6-27B` instead of `DeepSeek-V4-Flash`
- **Image router** — `Qwen3.6-35B-A3B` added to text-only image routing

## Local Provider

Routes to any OpenAI-compatible inference server running on the host machine. Two pre-configured models on separate ports.

| Variable | Description |
| --- | --- |
| `LOCAL_M_BASE_URL` | Primary model endpoint (default: port 8000) |
| `LOCAL_M_API_KEY` | Primary model key (any non-empty value) |
| `LOCAL_S_BASE_URL` | Secondary model endpoint (default: port 8001) |
| `LOCAL_S_API_KEY` | Secondary model key (any non-empty value) |

**Models:**

| Model | ID | Context | Output | Notes |
| --- | --- | --- | --- | --- |
| Qwen3.6-27B | `openai/qwen3.6_27b` | 131K | 16K | Reasoning enabled, seed 42 |
| Qwen3.6-35B-A3B | `openai/qwen3.6_35b_a3b` | 262K | 41K | Vision-capable, reasoning enabled |

**Local model parameters:**

| Parameter | Value |
| --- | --- |
| Temperature | 0.0 |
| Top-p | 1.0 |
| Top-k | 1 |
| Max thinking tokens | 1,536 |
| Seed | 42 |
| Repetition penalty | 1.0 |
| Thinking | Enabled (`enable_thinking: true`) |

Local models use the `system-message-merger` plugin to handle system messages correctly.

## Changed Secrets

| Secret | Description |
| --- | --- |
| `LOCAL_M_API_KEY` | Primary local model key (any non-empty value) |
| `LOCAL_S_API_KEY` | Secondary local model key (any non-empty value) |

All `costeffective-coding` secrets are also required:

| Secret | Description |
| --- | --- |
| `LITELLM_MASTER_KEY` | Proxy auth key |
| `MICROSOFT_FOUNDRY_API_KEY` | Azure Foundry API key |
| `OPENCODE_ZEN_API_KEY` | OpenCode API key |
| `OPENROUTER_API_KEY` | OpenRouter API key |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | GitHub token for MCP |

Set up all secrets:

```bash
bash ~/.codefreedom/scripts/costeffective-coding-with-local/setup-secrets.sh
```

## Changed Model Aliases

| Alias | costeffective-coding | costeffective-coding-with-local |
| --- | --- | --- |
| `fable` | Qwen3.7-Max | Qwen3.7-Max |
| `opus` | Qwen3.7-Plus | Qwen3.7-Plus |
| `sonnet` | DeepSeek-V4-Pro | DeepSeek-V4-Pro |
| `haiku` | DeepSeek-V4-Flash | DeepSeek-V4-Flash |
| `custom` | DeepSeek-V4-Flash | **Qwen3.6-27B** |

The `custom` alias points to the local Qwen3.6-27B model instead of cloud.

## Providers (Inherited)

All providers from `costeffective-coding` are included:

- **Azure Foundry** — GPT-5.x models
- **OpenCode Zen** — MiMo, DeepSeek, Qwen, MiniMax, Kimi (free + subscription)
- **OpenRouter** — DeepSeek, MiMo, Qwen, MiniMax, Kimi, FreeRouter

## Agent Profiles

Identical to `costeffective-coding`. See [costeffective-coding profiles](costeffective-coding.md#agent-profiles).

## Tools

Inherited from `_default`. See [costeffective-coding tools](costeffective-coding.md#tools).

## Files Deployed

```text
~/.codefreedom/
├── .env.claude.secrets          # Claude Code secrets
├── .env.mimo.secrets            # MiMo Code secrets
├── .env.opencode.secrets        # OpenCode secrets
├── .env.proxy.secrets           # Proxy provider secrets (includes LOCAL_*)
├── profiles/
│   ├── claude-code.yaml         # Claude Code agent profiles
│   ├── mimo-code.yaml           # MiMo Code agent profiles
│   ├── open-code.yaml           # OpenCode agent profiles
│   ├── chrome.yaml              # Chrome tool config
│   ├── web.yaml                 # Web search tool config
│   ├── github.yaml              # GitHub tool config
│   └── web-bridge.yaml          # Web bridge tool config
├── proxy/
│   ├── docker-compose.yaml      # Container orchestration
│   └── config/
│       ├── config.yaml          # LiteLLM main config (includes local.yaml)
│       ├── providers/
│       │   ├── azure-foundry.yaml
│       │   ├── opencode.yaml
│       │   ├── openrouter.yaml
│       │   └── local.yaml       # ← NEW: local Qwen models
│       └── plugins/
│           └── reasoning-efforts/
│               └── reasoning-efforts-mapping.yaml
└── scripts/
    └── costeffective-coding-with-local/
        ├── setup-secrets.sh
        └── setup-secrets.ps1
```

## Differences from costeffective-coding

| Aspect | costeffective-coding | costeffective-coding-with-local |
| --- | --- | --- |
| Providers | Azure, OpenCode, OpenRouter | Azure, OpenCode, OpenRouter, **Local** |
| `custom` alias | DeepSeek-V4-Flash | **Qwen3.6-27B** |
| Local secrets | — | `LOCAL_M_API_KEY`, `LOCAL_S_API_KEY` |
| Image router models | FreeRouter | FreeRouter, **Qwen3.6-35B-A3B** |
| `config.yaml` includes | 3 providers | 4 providers (+ `local.yaml`) |
| Setup script path | `scripts/costeffective-coding/` | `scripts/costeffective-coding-with-local/` |
