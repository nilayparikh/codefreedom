---
description: OpenCodeZen/Big-Pickle — general purpose 262K context, text-only.
---

# OpenCode Zen / Big-Pickle

General purpose model with reasoning and tool support. Specs are conservative defaults.

**LiteLLM model:** `openai/big-pickle`
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
- model_name: OpenCodeZen/Big-Pickle
  litellm_params:
    # Full block — every field shown inline. Copy/paste this entry
    # into your opencode-zen.yaml without needing any anchor.
    model: openai/big-pickle
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
    id: "opencode-big-pickle"
    db_model: false
    supports_reasoning: true
    mode: chat
    supports_system_messages: true
    supports_native_streaming: true
    supports_vision: false
    # Conservative: similar to mid-tier models
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

- Use for: text-only coding and reasoning tasks.
- Specs are conservative defaults; the working configuration may differ from real upstream capabilities.
- Suitable as a general-purpose fallback or for `CodeFreedom/Flash` aliasing.

See [OpenCode Zen provider](index.md) for the generic schema and enabling steps.
