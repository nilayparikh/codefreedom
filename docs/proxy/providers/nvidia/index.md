---
description: NVIDIA AI Endpoints provider — DeepSeek, GLM, Kimi, Step via build.nvidia.com.
---

# NVIDIA

[NVIDIA AI Endpoints](https://build.nvidia.com/explore/discover) provides API access to a range of models through a unified OpenAI-compatible interface. Each model lives behind a different organization prefix (e.g., `deepseek-ai/`, `z-ai/`, `moonshotai/`, `stepfun-ai/`).

**Provider file:** `~/.codefreedom/proxy/config/providers/nvidia.yaml`

## Environment Variables

| Variable          | Description                                            | Required                                            |
| ----------------- | ------------------------------------------------------ | --------------------------------------------------- |
| `NVIDIA_API_KEY`  | API key from [NVIDIA Build](https://build.nvidia.com/) | Yes                                                 |
| `NVIDIA_BASE_URL` | API base URL                                           | No (default: `https://integrate.api.nvidia.com/v1`) |

## Available Models

| Model                                     | Context   | Max Output | Vision | Reasoning |
| ----------------------------------------- | --------- | ---------- | ------ | --------- |
| [DeepSeek-V4-Flash](deepseek-v4-flash.md) | 1,000,000 | 384,000    | No     | Yes       |
| [DeepSeek-V4-Pro](deepseek-v4-pro.md)     | 1,000,000 | 384,000    | No     | Yes       |
| [GLM-5.1](glm-5.1.md)                     | 204,800   | 8,192      | No     | Yes       |
| [Kimi-K2.6](kimi-k2.6.md)                 | 256,000   | 16,384     | Yes    | Yes       |
| [Step-3.7-Flash](step-3.7-flash.md)       | 262,144   | 16,384     | Yes    | Yes       |

## Generic Configuration

All NVIDIA models share the same `supported_openai_params` list. Each model file inlines the full list (rather than referencing a shared anchor) so the block is self-contained and can be copy/pasted standalone.

```yaml
model_list:
  # https://build.nvidia.com/deepseek-ai/deepseek-v4-flash/modelcard
  - model_name: NVIDIA/DeepSeek-V4-Flash
    litellm_params:
      # LiteLLM's openai/ prefix with the full "organization/model" path.
      # NVIDIA's API is OpenAI-compatible, but the model identifier
      # is owned by the upstream org, not NVIDIA.
      model: openai/deepseek-ai/deepseek-v4-flash
      api_base: os.environ/NVIDIA_BASE_URL
      api_key: os.environ/NVIDIA_API_KEY
      timeout: 300
      drop_params: true
      extra_body:
        # Ask the upstream to include usage metadata in the streaming
        # response so token accounting works.
        stream_options:
          include_usage: true
    model_info:
      id: "nvidia-deepseek-v4-flash"
      db_model: false
      supports_reasoning: true
      mode: chat
      context_window: 1000000
      max_tokens: 1000000
      max_input_tokens: 616000
      max_output_tokens: 384000
      limit:
        context: 1000000
        output: 384000
      supports_system_messages: true
      supports_native_streaming: true
      supports_vision: false
      # Full list of OpenAI parameters this model accepts. Repeated
      # inline in every model file so each page is self-contained —
      # copy/paste a single model block without re-defining anchors.
      supported_openai_params:
        - tools
        - tool_choice
        - parallel_tool_calls
        - response_format
        - max_tokens
        - max_completion_tokens
        - stream
        - stream_options
        - temperature
        - top_p
        - stop
        - thinking
        - reasoning_effort
```

### Common Field Notes

- **`model: openai/org/model`** — NVIDIA exposes models through an OpenAI-compatible interface, but each model is owned by its own organization. The full `organization/model` path is required.
- **`supported_openai_params` (inlined in each model)** — Each model file inlines the full list of OpenAI-compatible parameters it accepts. This keeps every model page self-contained — copy/paste a single block into your `nvidia.yaml` without needing to chase an anchor.
- **Model-specific `extra_body`** — Some models need extra parameters:
  - GLM-5.1: `temperature`, `top_p`, `top_k` for its sampling distribution.
  - Kimi-K2.6: `chat_template_kwargs.thinking: true` to enable chain-of-thought.
- **`db_model: false`** — These models are not stored in the LiteLLM database. Set to `true` only if you have a PostgreSQL backend and want spend tracking by model.

## Enabling

1. Uncomment the model entries in `nvidia.yaml` (commented by default in the example).
2. Ensure `providers/nvidia.yaml` is in the `include` list in `config.yaml`.
3. Set `NVIDIA_API_KEY` in `~/.codefreedom/.env.proxy.secrets`.

## Per-Model Details

See each model's dedicated page for full `model_info`, `extra_body`, and supported parameters:

- [DeepSeek-V4-Flash](deepseek-v4-flash.md) — 1M context, 384K output
- [DeepSeek-V4-Pro](deepseek-v4-pro.md) — 1M context, 384K output
- [GLM-5.1](glm-5.1.md) — 204K context, custom sampling
- [Kimi-K2.6](kimi-k2.6.md) — 256K context, vision, thinking mode
- [Step-3.7-Flash](step-3.7-flash.md) — 262K context, vision
