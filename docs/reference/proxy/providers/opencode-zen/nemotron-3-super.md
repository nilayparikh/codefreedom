---
description: OpenCodeZen/Nemotron-3-Super-FREE — NVIDIA text-only model, 262K context.
---

# OpenCode Zen / Nemotron-3-Super-FREE

NVIDIA Nemotron-3-Super, text-only. Specs are conservative defaults based on the Nemotron-3-Ultra specs (same family).

**LiteLLM model:** `openai/nemotron-3-super-free`
**Context window:** 262,144 tokens
**Max output:** 65,536 tokens

## Capabilities

| Capability       | Supported |
| ---------------- | --------- |
| Vision           | No        |
| Reasoning        | Yes       |
| Native streaming | Yes       |
| System messages  | Yes       |
| Tool use         | Yes       |

## Configuration

```yaml
- model_name: OpenCodeZen/Nemotron-3-Super-FREE
  litellm_params:
    # Full block — every field shown inline. Copy/paste this entry
    # into your opencode-zen.yaml without needing any anchor.
    model: openai/nemotron-3-super-free
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
    id: "opencode-nemotron-3-super-free"
    db_model: false
    supports_reasoning: true
    mode: chat
    supports_system_messages: true
    supports_native_streaming: true
    supports_vision: false
    # Conservative: same as Ultra but smaller
    context_window: 262144
    max_tokens: 262144
    max_input_tokens: 131072
    max_output_tokens: 65536
    limit:
      context: 262144
      output: 65536
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

- Use for: text-only coding tasks where vision is not needed.
- Specs are conservative; the working configuration may differ from real upstream capabilities.
- Suitable as a free-tier replacement for `CodeFreedom/Pro` when vision is not required.

See [OpenCode Zen provider](index.md) for the generic schema and enabling steps.
