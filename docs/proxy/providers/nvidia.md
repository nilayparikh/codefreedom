---
description: NVIDIA AI Endpoints — DeepSeek, MiniMax, Kimi via nvidia.com.
---

# NVIDIA

[NVIDIA AI Endpoints](https://build.nvidia.com/explore/discover) provides API access to a range of models through a unified OpenAI-compatible interface.

**File:** `~/.codefreedom/proxy/config/providers/nvidia.yaml`

## Environment Variables

| Variable | Description | Default |
| --- | --- | --- |
| `NVIDIA_API_KEY` | API key from [NVIDIA Build](https://build.nvidia.com/) | (required) |
| `NVIDIA_BASE_URL` | API base URL | `https://integrate.api.nvidia.com/v1` |

## Example Configuration

```yaml
model_list:
  - model_name: NVIDIA/DeepSeek-V4-Flash
    litellm_params:
      model: openai/deepseek-ai/deepseek-v4-flash
      api_base: os.environ/NVIDIA_BASE_URL
      api_key: os.environ/NVIDIA_API_KEY
      timeout: 300
      drop_params: true
      extra_body:
        stream_options:
          include_usage: true
    model_info:
      mode: chat
      context_window: 1000000
      max_tokens: 1000000
      supports_reasoning: false
      supports_vision: false
```

- **`model: openai/provider/model`** — NVIDIA uses the OpenAI-compatible format with the full `organization/model` path.
- **`extra_body`** — Some models (MiniMax, Kimi) need additional parameters like `temperature`, `top_p`, or `chat_template_kwargs.thinking: true`. See the template file for model-specific settings.

## Enabling

1. Uncomment the model entries in `nvidia.yaml`.
2. Ensure `providers/nvidia.yaml` is in the `include` list.
3. Set `NVIDIA_API_KEY` in `~/.codefreedom/.env.proxy.secrets`.
