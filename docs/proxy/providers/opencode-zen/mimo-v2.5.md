---
description: OpenCodeZen/MiMo-V2.5-FREE — Xiaomi 1M context model with vision and reasoning.
---

# OpenCode Zen / MiMo-V2.5-FREE

Xiaomi MiMo V2.5 with 1M context window, 131K output, and vision support. Reasoning-capable.

**LiteLLM model:** `openai/mimo-v2.5-free`
**Context window:** 1,048,576 tokens
**Max output:** 131,072 tokens

## Capabilities

| Capability       | Supported |
| ---------------- | --------- |
| Vision           | Yes       |
| Reasoning        | Yes       |
| Native streaming | Yes       |
| System messages  | Yes       |
| Tool use         | Yes       |

## Configuration

```yaml
- model_name: OpenCodeZen/MiMo-V2.5-FREE
  litellm_params:
    model: openai/mimo-v2.5-free
    api_base: os.environ/OPENCODE_ZEN_BASE_URL
    api_key: os.environ/OPENCODE_ZEN_API_KEY
    timeout: 300
    drop_params: true
    stream_options:
      include_usage: true
    extra_body:
      temperature: 0.0
      top_p: 1.0
      reasoning_effort: "high"
  model_info:
    id: "opencode-mimo-v2.5-free"
    db_model: false
    supports_reasoning: true
    mode: chat
    supports_system_messages: true
    supports_native_streaming: true
    supports_vision: true
    context_window: 1048576
    max_tokens: 1048576
    max_input_tokens: 917504
    max_output_tokens: 131072
    limit:
      context: 1048576
      output: 131072
    supported_openai_params:
      - tools
      - tool_choice
      - parallel_tool_calls
      - max_tokens
      - max_completion_tokens
      - stream
      - stream_options
      - temperature
      - top_p
      - stop
      - thinking
      - reasoning_effort
      - response_format
```

## Notes

- Use for: long-context coding sessions, vision tasks, reasoning-heavy planning.
- 1M context is among the largest available in the free tier.
- Source: [models.dev/xiaomi/mimo-v2.5](https://models.dev/models/xiaomi/mimo-v2.5)

See [OpenCode Zen provider](index.md) for the generic schema and enabling steps.
