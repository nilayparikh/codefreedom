---
description: OpenRouter/FreeRouter — dynamic free-tier model selection.
---

# OpenRouter / FreeRouter

Dynamic endpoint that lets OpenRouter pick the best available free model at request time. Useful for `CodeFreedom/Air` when you want cheap answers without pinning a specific model.

**LiteLLM model:** `openrouter/openrouter/free`

## Capabilities

| Capability       | Supported             |
| ---------------- | --------------------- |
| Vision           | Yes (model-dependent) |
| Reasoning        | No — see notes below  |
| Native streaming | Yes                   |
| System messages  | Yes                   |
| Tool use         | Yes                   |

## Configuration

```yaml
- model_name: OpenRouter/FreeRouter
  litellm_params:
    # Full block — every field shown inline. Copy/paste this entry
    # into your openrouter.yaml without needing any anchor.
    model: openrouter/openrouter/free
    api_base: os.environ/OPENROUTER_BASE_URL
    api_key: os.environ/OPENROUTER_API_KEY
    timeout: 300
    drop_params: true
    extra_body:
      # Request usage metadata in the streaming response.
      stream_options:
        include_usage: true
  model_info:
    id: "openrouter-freerouter"
    mode: chat
    supports_system_messages: true
    supports_native_streaming: true
    supports_vision: true
    # FreeRouter is a dynamic load-balanced endpoint with no native
    # reasoning_effort gradient. Drop that param to match the
    # "only none" capability advertised to VS Code.
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
```

## Notes

- Use for: cheapest possible answers, mechanical code edits, classification.
- **Dynamic model** — OpenRouter picks the actual model per request. You don't know which model you'll get.
- **`reasoning_effort` removed** — The `supported_openai_params` here drops `reasoning_effort`. The dynamic endpoint has no native reasoning gradient, so passing the param would either be ignored or fail. Removing it tells VS Code (and any other client) that this model only supports `reasoning_effort: none`.

See [OpenRouter provider](index.md) for the generic schema and enabling steps.
