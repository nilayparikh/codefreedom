---
description: OpenRouter provider — aggregated models from multiple sources.
---

# OpenRouter

[OpenRouter](https://openrouter.ai/) aggregates hundreds of models from multiple providers into one API. Supports paid and free-tier models, including automatic routing via the `openrouter/free` endpoint.

**Provider file:** `~/.codefreedom/proxy/config/providers/openrouter.yaml`

## Environment Variables

| Variable              | Description                                       | Required                                     |
| --------------------- | ------------------------------------------------- | -------------------------------------------- |
| `OPENROUTER_API_KEY`  | API key from [OpenRouter](https://openrouter.ai/) | Yes                                          |
| `OPENROUTER_BASE_URL` | API base URL                                      | No (default: `https://openrouter.ai/api/v1`) |

## Available Models

| Model                                                       | LiteLLM Identifier                                  | Vision | Reasoning |
| ----------------------------------------------------------- | --------------------------------------------------- | ------ | --------- |
| [Nemotron-3-Ultra-550B-A55B](nemotron-3-ultra-550b-a55b.md) | `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free` | Yes    | Yes       |
| [FreeRouter](freerouter.md)                                 | `openrouter/openrouter/free`                        | Yes    | No        |

## Generic Configuration

Both OpenRouter models share the `litellm_params` block via a YAML anchor. The first model defines the anchor; the second reuses it.

```yaml
model_list:
  - model_name: OpenRouter/Nemotron-3-Ultra-550B-A55B
    litellm_params:
      # The full upstream path. Append :free for free-tier models.
      # OpenRouter handles the routing to the actual provider (NVIDIA here).
      model: openrouter/nvidia/nemotron-3-ultra-550b-a55b:free
      api_base: os.environ/OPENROUTER_BASE_URL
      api_key: os.environ/OPENROUTER_API_KEY
      timeout: 300
      drop_params: true
      extra_body:
        # Request usage metadata in the streaming response.
        stream_options:
          include_usage: true
    model_info:
      id: "openrouter-nemotron-3-ultra-550b-a55b"
      mode: chat
      supports_system_messages: true
      supports_native_streaming: true
      supports_vision: true
      # Full list of OpenAI parameters this model accepts. Inlined
      # (rather than referencing a shared anchor) so the block is
      # self-contained and can be copy/pasted standalone.
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

### Common Field Notes

- **`model: openrouter/org/model`** — LiteLLM's OpenRouter integration. Append `:free` for free-tier routing. See [LiteLLM OpenRouter docs](https://docs.litellm.ai/docs/providers/openrouter).
- **`openrouter/openrouter/free`** — A special endpoint where OpenRouter picks the best available free model at request time. Useful for `CodeFreedom/Air` when you don't care which model answers.
- **`supported_openai_params` (inlined in each model)** — Each model file inlines the full list of OpenAI-compatible parameters it accepts. This keeps every model page self-contained — copy/paste a single block into your `openrouter.yaml` without needing to chase an anchor.
- **FreeRouter param difference** — FreeRouter drops `reasoning_effort` from `supported_openai_params` because the dynamic endpoint has no native reasoning gradient.

## Enabling

1. Uncomment the model entries in `openrouter.yaml` (commented by default in the example).
2. Ensure `providers/openrouter.yaml` is in the `include` list in `config.yaml`.
3. Set `OPENROUTER_API_KEY` in `~/.codefreedom/.env.proxy.secrets`.

## Per-Model Details

See each model's dedicated page for full `model_info`, supported parameters, and any model-specific overrides:

- [Nemotron-3-Ultra-550B-A55B](nemotron-3-ultra-550b-a55b.md) — specific free-tier model pinned
- [FreeRouter](freerouter.md) — dynamic free model selection
