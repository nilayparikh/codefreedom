---
description: OpenCodeZen/Nemotron-3-Ultra-FREE — NVIDIA 1M context model with vision.
---

# OpenCode Zen / Nemotron-3-Ultra-FREE

NVIDIA Nemotron-3-Ultra with 1M context window and vision support.

**LiteLLM model:** `openai/nemotron-3-ultra-free`
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
- model_name: OpenCodeZen/Nemotron-3-Ultra-FREE
  litellm_params:
    # Full block — every field shown inline. Copy/paste this entry
    # into your opencode-zen.yaml without needing any anchor.
    model: openai/nemotron-3-ultra-free
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
    id: "opencode-nemotron-3-ultra-free"
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
    # Full list of OpenAI parameters this model accepts. Inlined
    # (rather than referencing a shared anchor) so the block is
    # self-contained and can be copy/pasted standalone.
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

- Use for: long-context reasoning, vision tasks, large codebase analysis.
- Source: [models.dev/nvidia/nemotron-3-ultra-550b-a55b](https://models.dev/models/nvidia/nemotron-3-ultra-550b-a55b)
- Capabilities: reasoning, tools, temperature.

See [OpenCode Zen provider](index.md) for the generic schema and enabling steps.
