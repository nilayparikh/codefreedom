---
description: OpenCodeZen/MiniMax-M3-FREE — 512K context, vision, with internal reasoning parser.
---

# OpenCode Zen / MiniMax-M3-FREE

MiniMax M3 with 512K context window and vision support. Uses an internal reasoning parser — the `drop_params: false` and `modify_params: true` settings keep the `reasoning_effort` parameter intact for that parser.

**LiteLLM model:** `minimax/minimax-m3-free`
**Context window:** 512,000 tokens
**Max output:** 128,000 tokens

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
- model_name: OpenCodeZen/MiniMax-M3-FREE
  litellm_params:
    # Full block — every field shown inline. Copy/paste this entry
    # into your opencode-zen.yaml without needing any anchor.
    model: minimax/minimax-m3-free
    api_base: os.environ/OPENCODE_ZEN_BASE_URL
    api_key: os.environ/OPENCODE_ZEN_API_KEY
    timeout: 300
    # Keep these parameters to enable the internal reasoning parser
    drop_params: false
    modify_params: true
    stream_options:
      include_usage: true
    extra_body:
      temperature: 0.0
      top_p: 1.0
      reasoning_effort: "high"
  model_info:
    id: "opencode-minimax-m3-free"
    db_model: false
    supports_reasoning: true
    mode: chat
    supports_system_messages: true
    supports_native_streaming: true
    supports_vision: true
    context_window: 512000
    max_tokens: 512000
    max_input_tokens: 384000
    max_output_tokens: 128000
    limit:
      context: 512000
      output: 128000
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

- Use for: vision + reasoning tasks at mid-range cost.
- **`drop_params: false`** — Different from the rest of the provider. Required so the `reasoning_effort` parameter survives to the upstream reasoning parser.
- **`modify_params: true`** — Lets LiteLLM rewrite the request body to match the upstream format.
- Source: [models.dev/minimax/MiniMax-M3](https://models.dev/models/minimax/MiniMax-M3)

See [OpenCode Zen provider](index.md) for the generic schema and enabling steps.
