---
title: Recipes
description: Configuration examples and provider setup guides for CodeFreedom.
---

# Recipes

Step-by-step configuration guides for every supported provider. Each recipe covers API keys, model aliases, proxy routing, and profile setup.

## Provider Reference

Detailed YAML configuration reference for each provider — env vars, model tables, and setup steps.

<div class="grid cards" markdown>

- :material-flask:{ .lg .middle } **DeepSeek**

  V4-Flash and V4-Pro via DeepSeek API. Enable reasoning, configure profiles.

  [:octicons-arrow-right-24: DeepSeek](providers/deepseek/index.md)

- :material-microsoft-azure:{ .lg .middle } **Azure Foundry**

  GPT-5.4 family via Microsoft Foundry. Deploy, configure, and route.

  [:octicons-arrow-right-24: Azure Foundry](providers/azure-foundry/index.md)

- :material-nvidia:{ .lg .middle } **NVIDIA**

  DeepSeek, GLM, Kimi, Step via NVIDIA AI Endpoints. Zero-cost players.

  [:octicons-arrow-right-24: NVIDIA](providers/nvidia/index.md)

- :material-cloud-braces:{ .lg .middle } **OpenCode Zen**

  Free-tier models — Mimo, Nemotron, DeepSeek, MiniMax-M3. Test without spending.

  [:octicons-arrow-right-24: OpenCode Zen](providers/opencode-zen/index.md)

- :material-swap-horizontal-bold:{ .lg .middle } **OpenRouter**

  Aggregated models via OpenRouter. One API key, many providers.

  [:octicons-arrow-right-24: OpenRouter](providers/openrouter/index.md)

- :material-api:{ .lg .middle } **OpenAI Compatible**

  Any OpenAI-compatible `/v1/chat/completions` endpoint. Bring your own backend.

  [:octicons-arrow-right-24: OpenAI Compatible](providers/openai-compatible/index.md)

- :material-chat:{ .lg .middle } **Anthropic Compatible**

  Any Anthropic-compatible `/v1/messages` endpoint. Claude API and beyond.

  [:octicons-arrow-right-24: Anthropic Compatible](providers/anthropic-compatible/index.md)

- :material-server:{ .lg .middle } **Local**

  Self-hosted inference servers on two ports. Run models on your own hardware.

  [:octicons-arrow-right-24: Local](providers/local/index.md)

</div>

## What's in a Recipe

Each provider page covers:

- **Provider YAML** — the `model_list` entries for LiteLLM proxy config
- **Environment variables** — API keys, base URLs, and optional overrides
- **Profile setup** — how to add the provider to your `profiles.json`
- **Quick start** — minimal steps from API key to working session

For the full YAML reference, see the [Provider Configuration Reference](providers/index.md).
