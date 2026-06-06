---
description: DeepSeek/DeepSeek-V4-Flash — fast, cheap 1M context model.
---

# DeepSeek / DeepSeek-V4-Flash

Fast, cost-effective DeepSeek variant. 1M context, 384K output, with reasoning support.

**LiteLLM model:** `deepseek/deepseek-v4-flash`
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

## Pricing (per token)

| Type   | Cost        |
| ------ | ----------- |
| Input  | $0.00000014 |
| Output | $0.00000028 |

## Configuration

```yaml
- model_name: DeepSeek/DeepSeek-V4-Flash
  litellm_params:
    model: deepseek/deepseek-v4-flash
    api_base: os.environ/DEEPSEEK_BASE_URL
    api_key: os.environ/DEEPSEEK_API_KEY
    timeout: 300
    drop_params: true
  model_info:
    id: "deepseek-openai-deepseek-v4-flash"
    db_model: false
    supports_reasoning: true
    mode: chat
    context_window: 1000000
    max_tokens: 1000000
    max_input_tokens: 616000
    max_output_tokens: 384000
    limit:
      context: 1000000
      output: 384000
    supports_system_messages: true
    supports_native_streaming: true
    supports_streaming: true
    supports_vision: false
    input_cost_per_token: 0.00000014
    output_cost_per_token: 0.00000028
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

- Use for: fast iteration, scanning, mechanical code edits, large output tasks.
- Suitable as `CodeFreedom/Flash` alias target.
- Lowest-cost DeepSeek model — 12x cheaper input than V4-Pro.
- 384K max output supports very large refactor operations.

See [DeepSeek provider](index.md) for the generic schema and enabling steps.
