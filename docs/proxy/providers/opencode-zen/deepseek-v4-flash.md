---
description: OpenCodeZen/DeepSeek-V4-Flash-FREE — text-only 1M context, 384K output.
---

# OpenCode Zen / DeepSeek-V4-Flash-FREE

DeepSeek V4-Flash on the free tier. Text-only, with 1M context and 384K max output (largest output in the provider).

**LiteLLM model:** `openai/deepseek-v4-flash-free`
**Context window:** 1,000,000 tokens
**Max output:** 384,000 tokens

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
- model_name: OpenCodeZen/DeepSeek-V4-Flash-FREE
  litellm_params:
    # Full block — every field shown inline. Copy/paste this entry
    # into your opencode-zen.yaml without needing any anchor.
    model: openai/deepseek-v4-flash-free
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
    id: "opencode-deepseek-v4-flash-free"
    db_model: false
    supports_reasoning: true
    mode: chat
    supports_system_messages: true
    supports_native_streaming: true
    supports_vision: false
    context_window: 1000000
    max_tokens: 1000000
    max_input_tokens: 616000
    max_output_tokens: 384000
    limit:
      context: 1000000
      output: 384000
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

- Use for: long-output tasks (large refactors, multi-file generation), long-context coding.
- Largest max output among the free-tier models in this provider.
- Source: [models.dev/deepseek/deepseek-v4-flash](https://models.dev/models/deepseek/deepseek-v4-flash)
- Capabilities: reasoning, tools, thinking, temperature.

See [OpenCode Zen provider](index.md) for the generic schema and enabling steps.
