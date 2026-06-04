---
description: Provider YAML system — enabling, disabling, and adding custom providers.
---

# Providers

Each provider is a YAML file in `~/.codefreedom/proxy/config/providers/` that defines one or more models. The proxy loads them via the `include` list in `config.yaml`.

## Available Providers

| Provider | File | Description |
| --- | --- | --- |
| [DeepSeek](deepseek.md) | `deepseek.yaml` | DeepSeek-V4-Flash and V4-Pro |
| [Azure Foundry](azure-foundry.md) | `azure-foundry.yaml` | Kimi-K2.6, GLM-5.1, DeepSeek-V4-Pro via Azure |
| [NVIDIA](nvidia.md) | `nvidia.yaml` | Models via NVIDIA AI Endpoints |
| [OpenCode Zen](opencode-zen.md) | `opencode-zen.yaml` | Free-tier models (Mimo, Nemotron, DeepSeek) |
| [OpenRouter](openrouter.md) | `openrouter.yaml` | Aggregated models via OpenRouter |
| [OpenAI Compatible](openai-compatible.md) | `openai-compatible.yaml` | Any OpenAI-compatible endpoint |
| [Anthropic Compatible](anthropic-compatible.md) | `anthropic-compatible.yaml` | Any Anthropic-compatible endpoint |
| [Local](local.md) | `local.yaml` | Self-hosted inference servers |

## How a Provider YAML Works

Each file defines a `model_list`. Every entry has two parts:

```yaml
model_list:
  - model_name: Provider/ModelName          # Name used by aliases and clients
    litellm_params:                         # How to call the API
      model: deepseek/deepseek-v4-flash     # LiteLLM model identifier
      api_base: os.environ/DEEPSEEK_BASE_URL
      api_key: os.environ/DEEPSEEK_API_KEY
      timeout: 300
      drop_params: true
    model_info:                             # Capabilities and limits
      mode: chat
      context_window: 1000000
      supports_reasoning: true
      supports_vision: false
```

- **`model_name`** — The name clients use. Model aliases (`CodeFreedom/Pro`) point to this.
- **`litellm_params`** — API details. `model` uses LiteLLM's provider prefix (e.g., `deepseek/`, `openai/`, `openrouter/`). API keys and bases come from env vars via `os.environ/VAR_NAME`.
- **`model_info`** — Capabilities (reasoning, vision, streaming) and token limits. Used for routing decisions and fallbacks.

## Enabling a Provider

Three steps:

1. **Uncomment** the model entries in the provider YAML file.
2. **Ensure** the file is in the `include` list in `config.yaml`.
3. **Set the API key** in `~/.codefreedom/.env.proxy.secrets`.

```bash
# Example: enable DeepSeek
echo 'DEEPSEEK_API_KEY=sk-your-key' >> ~/.codefreedom/.env.proxy.secrets
```

Restart the proxy for changes to take effect.

## Disabling a Provider

Comment out the `include` line in `config.yaml`:

```yaml
include:
  - providers/deepseek.yaml
  # - providers/nvidia.yaml    # disabled
```

You can also leave the API key empty — LiteLLM skips models with missing keys — but commenting the include is cleaner.

## Adding a Custom Provider

1. Create `~/.codefreedom/proxy/config/providers/my-provider.yaml`:

```yaml
model_list:
  - model_name: MyProvider/ModelName
    litellm_params:
      model: openai/my-model
      api_base: os.environ/MY_PROVIDER_BASE_URL
      api_key: os.environ/MY_PROVIDER_API_KEY
      timeout: 300
      drop_params: true
    model_info:
      mode: chat
      context_window: 131072
      supports_system_messages: true
      supports_native_streaming: true
```

2. Add to `include` in `config.yaml`:

```yaml
include:
  # ... existing providers ...
  - providers/my-provider.yaml
```

3. Set `MY_PROVIDER_BASE_URL` and `MY_PROVIDER_API_KEY` in `.env.proxy.secrets`.

LiteLLM supports [100+ providers](https://docs.litellm.ai/docs/providers). Use the appropriate provider prefix in the `model` field (e.g., `anthropic/`, `openai/`, `deepseek/`, `openrouter/`).
