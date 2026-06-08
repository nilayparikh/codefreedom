---
description: OpenRouter provider — aggregated models from multiple sources.
---

# OpenRouter

[OpenRouter](https://openrouter.ai/) aggregates hundreds of models from multiple providers into one API. Supports paid and free-tier models.

**Provider file:** `~/.codefreedom/proxy/config/providers/openrouter.yaml`

## Environment Variables

| Variable              | Description                                       | Required                                     |
| --------------------- | ------------------------------------------------- | -------------------------------------------- |
| `OPENROUTER_API_KEY`  | API key from [OpenRouter](https://openrouter.ai/) | Yes                                          |
| `OPENROUTER_BASE_URL` | API base URL                                      | No (default: `https://openrouter.ai/api/v1`) |

## Models

| Model                      | LiteLLM Identifier                                  | Vision | Reasoning |
| -------------------------- | --------------------------------------------------- | ------ | --------- |
| Nemotron-3-Ultra-550B-A55B | `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free` | Yes    | Yes       |
| FreeRouter                 | `openrouter/openrouter/free`                        | Yes    | No        |

## Configuration

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
      id: "openrouter-nemotron-3-ultra-550b-a55b"
      mode: chat
      supports_system_messages: true
      supports_native_streaming: true
      supports_vision: true
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
        - reasoning_effort
```

Append `:free` for free-tier routing. The `openrouter/openrouter/free` endpoint picks the best available model at request time. See the [source YAML](https://github.com/nilayparikh/codefreedom/tree/main/src/codefreedom/examples/proxy/config/providers/openrouter.yaml) for the full file.

## Enabling

1. Uncomment model entries in `openrouter.yaml`.
2. Ensure `providers/openrouter.yaml` is in the `include` list in `config.yaml`.
3. Set `OPENROUTER_API_KEY` in `~/.codefreedom/.env.proxy.secrets`.
4. Restart the proxy.
