---
description: Azure/GPT-5.4-Mini — mid-tier 400K context model via Azure Foundry.
---

# Azure / GPT-5.4-Mini

Mid-tier GPT-5.4 deployment via Microsoft Foundry. 400K context window with vision and reasoning support, at lower cost than the flagship.

**LiteLLM model:** `openai/gpt-5.4-mini`
**Context window:** 400,000 tokens
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
| Input        | $0.00000100 |
| Cached input | $0.00000008 |
| Output       | $0.00001500 |

## Configuration

```yaml
- model_name: Azure/GPT-5.4-Mini
  litellm_params:
    model: openai/gpt-5.4-mini
    api_base: os.environ/MICROSOFT_FOUNDRY_API_BASE
    api_key: os.environ/MICROSOFT_FOUNDRY_API_KEY
    timeout: 300
    drop_params: true
    extra_body:
      stream_options:
        include_usage: true
  model_info:
    id: "azure-gpt-5-4-mini"
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
    input_cost_per_token: 0.00000100
    cached_input_cost_per_token: 0.00000008
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

- Use for: balanced cost/quality coding, vision tasks, medium-context work.
- 60% cheaper input than flagship, same output price.
- 400K context is sufficient for most Claude Code sessions.
- Output is the same quality tier — this is a smaller, faster, cheaper input encoder.

See [Azure Foundry provider](index.md) for the generic schema and enabling steps.
