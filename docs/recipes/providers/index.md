---
description: Provider YAML reference — env vars, model tables, and configuration examples.
---

# Provider Configuration Reference

Detailed configuration reference for every provider. For step-by-step setup guides, see the [Recipes](../index.md) overview.

## Provider Index

| Provider                                              | File                        | Description                                             |
| ----------------------------------------------------- | --------------------------- | ------------------------------------------------------- |
| [DeepSeek](deepseek/index.md)                         | `deepseek.yaml`             | V4-Flash and V4-Pro via DeepSeek API                    |
| [Azure Foundry](azure-foundry/index.md)               | `azure-foundry.yaml`        | GPT-5.4 family via Microsoft Foundry                    |
| [NVIDIA](nvidia/index.md)                             | `nvidia.yaml`               | DeepSeek, GLM, Kimi, Step via NVIDIA AI Endpoints       |
| [OpenCode Zen](opencode-zen/index.md)                 | `opencode-zen.yaml`         | Free-tier models (Mimo, Nemotron, DeepSeek, MiniMax-M3) |
| [OpenRouter](openrouter/index.md)                     | `openrouter.yaml`           | Aggregated models via OpenRouter                        |
| [OpenAI Compatible](openai-compatible/index.md)       | `openai-compatible.yaml`    | Any OpenAI-compatible `/v1/chat/completions` endpoint   |
| [Anthropic Compatible](anthropic-compatible/index.md) | `anthropic-compatible.yaml` | Any Anthropic-compatible `/v1/messages` endpoint        |
| [Local](local/index.md)                               | `local.yaml`                | Self-hosted inference servers on two ports              |

## How a Provider YAML Works

Each provider YAML defines a `model_list`. Every entry has two parts:

```yaml
model_list:
  - model_name: Provider/ModelName # Name used by aliases and clients
    litellm_params: # How to call the API
      model: deepseek/deepseek-v4-flash
      api_base: os.environ/DEEPSEEK_BASE_URL
      api_key: os.environ/DEEPSEEK_API_KEY
    model_info: # Capabilities and limits
      mode: chat
      context_window: 1000000
```

Source YAML files live at `~/.codefreedom/proxy/config/providers/` (after init) or in the [codefreedom examples](https://github.com/nilayparikh/codefreedom/tree/main/src/codefreedom/examples/proxy/config/providers).

## Enabling a Provider

1. **Uncomment** the model entries in the provider YAML file.
2. **Ensure** the file is in the `include` list in `config.yaml`.
3. **Set the API key** in `~/.codefreedom/.env.proxy.secrets`.
4. **Restart** the proxy: `codefreedom proxy restart`.
