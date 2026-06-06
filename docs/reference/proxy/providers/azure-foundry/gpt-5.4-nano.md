---
description: Azure/GPT-5.4-Nano — fast/small 400K context model via Azure Foundry.
---

# Azure / GPT-5.4-Nano

Smallest GPT-5.4 deployment via Microsoft Foundry. 400K context window, optimized for low-latency / high-volume tasks.

**LiteLLM model:** `openai/gpt-5.4-nano`
**Context window:** 400,000 tokens
**Max output:** 128,000 tokens

## Capabilities

| Capability       | Supported |
| ---------------- | --------- |
| Vision           | Yes       |
| Reasoning        | Yes       |
| Native streaming | No        |
| System messages  | No        |
| Tool use         | Yes       |

## Pricing (per token)

| Type         | Cost        |
| ------------ | ----------- |
| Input        | $0.00000080 |
| Cached input | $0.00000008 |
| Output       | $0.00001250 |

## Configuration

```yaml
- model_name: Azure/GPT-5.4-Nano
  litellm_params:
    model: openai/gpt-5.4-nano
    api_base: os.environ/MICROSOFT_FOUNDRY_API_BASE
    api_key: os.environ/MICROSOFT_FOUNDRY_API_KEY
    timeout: 300
    drop_params: true
    extra_body:
      stream_options:
        include_usage: true
  model_info:
    id: "azure-gpt-5-4-nano"
    db_model: false
    mode: chat
    context_window: 400000
    max_tokens: 400000
    max_input_tokens: 272000
    max_output_tokens: 128000
    limit:
      context: 400000
      output: 128000
    supports_reasoning: true
    supports_vision: true
    supports_system_messages: false
    supports_native_streaming: false
    input_cost_per_token: 0.00000080
    cached_input_cost_per_token: 0.00000008
    output_cost_per_token: 0.00001250
    supported_openai_params:
      - tools
      - tool_choice
      - response_format
      - max_tokens
      - max_completion_tokens
      - stream
      - stream_options
      - temperature
      - top_p
      - stop
      - presence_penalty
      - frequency_penalty
      - logit_bias
      - logprobs
      - top_logprobs
      - reasoning_effort
```

## Notes

- Use for: high-volume tasks, cheap classification, mechanical code edits.
- Lowest input cost in the GPT-5.4 family.
- Suitable as `CodeFreedom/Air` alias target for lightweight tasks.
- Output is 17% cheaper than flagship, with a smaller input encoder.

See [Azure Foundry provider](index.md) for the generic schema and enabling steps.
