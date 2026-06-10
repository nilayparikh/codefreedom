---
description: NVIDIA AI Endpoints provider — DeepSeek, GLM, Kimi, Step via build.nvidia.com.
---

# NVIDIA

[NVIDIA AI Endpoints](https://build.nvidia.com/explore/discover) provides API access to a range of models through a unified OpenAI-compatible interface.

**Provider file:** `~/.codefreedom/proxy/config/providers/nvidia.yaml`

## Environment Variables

| Variable          | Description                                            | Required                                            |
| ----------------- | ------------------------------------------------------ | --------------------------------------------------- |
| `NVIDIA_API_KEY`  | API key from [NVIDIA Build](https://build.nvidia.com/) | Yes                                                 |
| `NVIDIA_BASE_URL` | API base URL                                           | No (default: `https://integrate.api.nvidia.com/v1`) |

## Models

| Model             | Context   | Max Output | Vision | Reasoning |
| ----------------- | --------- | ---------- | ------ | --------- |
| DeepSeek-V4-Flash | 1,000,000 | 384,000    | No     | Yes       |
| DeepSeek-V4-Pro   | 1,000,000 | 384,000    | No     | Yes       |
| GLM-5.1           | 204,800   | 8,192      | No     | Yes       |
| Kimi-K2.6         | 256,000   | 16,384     | Yes    | Yes       |
| Step-3.7-Flash    | 262,144   | 16,384     | Yes    | Yes       |

## Configuration

All NVIDIA models share a common pattern. Example for DeepSeek-V4-Flash:

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
      id: "nvidia-deepseek-v4-flash"
      db_model: false
      supports_reasoning: true
      mode: chat
      context_window: 1000000
      max_tokens: 1000000
      max_output_tokens: 384000
      supports_system_messages: true
      supports_native_streaming: true
      supports_vision: false
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

See the [recipe YAML](https://github.com/nilayparikh/codefreedom-recipes/tree/main/nvidia/proxy/config/providers/nvidia.yaml) for all model entries including model-specific `extra_body` overrides (GLM-5.1 uses `temperature`/`top_p`/`top_k`; Kimi-K2.6 uses `chat_template_kwargs.thinking: true`).

## Enabling

1. Uncomment model entries in `nvidia.yaml`.
2. Ensure `providers/nvidia.yaml` is in the `include` list in `config.yaml`.
3. Set `NVIDIA_API_KEY` in `~/.codefreedom/.env.proxy.secrets`.
4. Restart the proxy.
