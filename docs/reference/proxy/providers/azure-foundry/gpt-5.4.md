---
description: Azure/GPT-5.4 — flagship 1.05M context model via Azure Foundry.
---

# Azure / GPT-5.4

Flagship GPT-5.4 deployment via Microsoft Foundry. 1.05M context window with vision and reasoning support.

**LiteLLM model:** `openai/gpt-5.4`
**Context window:** 1,050,000 tokens
**Max output:** 128,000 tokens

## Capabilities

| Capability       | Supported |
| ---------------- | --------- |
| Vision           | Yes       |
| Reasoning        | Yes       |
| Native streaming | Yes       |
| System messages  | Yes       |
| Tool use         | Yes       |

## Pricing (per token)

| Type         | Cost        |
| ------------ | ----------- |
| Input        | $0.00000250 |
| Cached input | $0.00000025 |
| Output       | $0.00001500 |

## Configuration

```yaml
- model_name: Azure/GPT-5.4
  litellm_params:
    model: openai/gpt-5.4
    api_base: os.environ/MICROSOFT_FOUNDRY_API_BASE
    api_key: os.environ/MICROSOFT_FOUNDRY_API_KEY
    timeout: 300
    drop_params: true
    extra_body:
      stream_options:
        include_usage: true
  model_info:
    id: "azure-gpt-5-4"
    db_model: false
    mode: chat
    context_window: 1050000
    max_tokens: 1050000
    max_input_tokens: 922000
    max_output_tokens: 128000
    limit:
      context: 1050000
      output: 128000
    supports_reasoning: true
    supports_vision: true
    supports_system_messages: true
    supports_native_streaming: true
    input_cost_per_token: 0.00000250
    cached_input_cost_per_token: 0.00000025
    output_cost_per_token: 0.00001500
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

- Use for: long-context reasoning, vision tasks, code review, planning.
- The 1.05M context window is among the largest available through this proxy.
- Pricing reflects the standard tier; cached input is ~10x cheaper — beneficial for repeated context.

See [Azure Foundry provider](index.md) for the generic schema and enabling steps.
