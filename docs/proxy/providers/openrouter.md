---
description: OpenRouter — aggregated models from multiple providers, including free-tier.
---

# OpenRouter

[OpenRouter](https://openrouter.ai/) aggregates hundreds of models from multiple providers into one API. Supports paid and free-tier models, including automatic routing via the `openrouter/free` endpoint.

**File:** `~/.codefreedom/proxy/config/providers/openrouter.yaml`

## Environment Variables

| Variable | Description | Default |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | API key from [OpenRouter](https://openrouter.ai/) | (required) |
| `OPENROUTER_BASE_URL` | API base URL | `https://openrouter.ai/api/v1` |

## Example Configuration

```yaml
model_list:
  - model_name: OpenRouter/Nemotron-3-Ultra-550B-A55B
    litellm_params:
      model: openrouter/nvidia/nemotron-3-ultra-550b-a55b:free
      api_base: os.environ/OPENROUTER_BASE_URL
      api_key: os.environ/OPENROUTER_API_KEY
      timeout: 300
      drop_params: true
      extra_body:
        stream_options:
          include_usage: true
    model_info:
      mode: chat
      supports_system_messages: true
      supports_native_streaming: true
      supports_vision: true
```

- **`model: openrouter/provider/model`** — Uses LiteLLM's OpenRouter integration with the full path. Append `:free` for free-tier models. See [LiteLLM OpenRouter docs](https://docs.litellm.ai/docs/providers/openrouter).
- **`OpenRouter/FreeRouter`** — The `openrouter/openrouter/free` model lets OpenRouter choose the best available free model automatically.

## Enabling

1. Uncomment the model entries in `openrouter.yaml`.
2. Ensure `providers/openrouter.yaml` is in the `include` list.
3. Set `OPENROUTER_API_KEY` in `~/.codefreedom/.env.proxy.secrets`.
