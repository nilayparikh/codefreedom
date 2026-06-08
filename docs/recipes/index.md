---
title: Recipes
description: Step-by-step guides for setting up AI providers with CodeFreedom.
---

# Recipes

Step-by-step guides for adding AI providers to your proxy. Pick a provider, follow the steps, start coding.

## Free to Start

| Recipe | What You Get | Cost |
|--------|-------------|------|
| [OpenCode Zen](opencode-zen.md) | Multiple free models (MiMo, Nemotron, DeepSeek) | Free |
| [NVIDIA](nvidia.md) | Free serverless endpoints (DeepSeek, GLM, Kimi) | Free tier |

## Paid Providers

| Recipe | What You Get |
|--------|-------------|
| [Azure Foundry](azure.md) | GPT-5.4 family (GPT, Mini, Nano) |
| [OpenAI Compatible](openai-compatible.md) | Any OpenAI-compatible endpoint |
| [Anthropic Compatible](anthropic-compatible.md) | Any Anthropic-compatible endpoint |

## How All Recipes Work

Every recipe follows the same pattern:

1. **Get an API key** from the provider
2. **Add the key** to `~/.codefreedom/.env.proxy.secrets`
3. **Enable the provider** in `~/.codefreedom/proxy/config/config.yaml`
4. **Restart** the proxy: `codefreedom proxy restart`

## First Time?

If you haven't set up the proxy yet, do this first:

```bash
codefreedom --init              # Creates all config files
codefreedom proxy start         # Start the proxy
```

Then pick a recipe above and follow along.
