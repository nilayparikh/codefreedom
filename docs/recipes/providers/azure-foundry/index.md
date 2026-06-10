---
description: Azure Foundry provider — GPT-5.4 family via Microsoft Foundry.
---

# Azure Foundry

[Microsoft Azure AI Foundry](https://www.azure.ai/) provides access to OpenAI's GPT-5.4 family through a unified, OpenAI-compatible API.

**Provider file:** `~/.codefreedom/proxy/config/providers/azure-foundry.yaml`

## Environment Variables

| Variable                     | Description                                                                | Required |
| ---------------------------- | -------------------------------------------------------------------------- | -------- |
| `MICROSOFT_FOUNDRY_API_BASE` | Project API base URL (`https://<project>.services.ai.azure.com/openai/v1`) | Yes      |
| `MICROSOFT_FOUNDRY_API_KEY`  | API key from Azure AI Foundry                                              | Yes      |

## Models

| Model        | Context   | Max Output | Vision | Reasoning |
| ------------ | --------- | ---------- | ------ | --------- |
| GPT-5.4      | 1,050,000 | 128,000    | Yes    | Yes       |
| GPT-5.4-Mini | 400,000   | 128,000    | Yes    | Yes       |
| GPT-5.4-Nano | 400,000   | 128,000    | Yes    | Yes       |

## Configuration

All GPT-5.4 family models share the same shape. Example for GPT-5.4:

```yaml
model_list:
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
      mode: chat
      context_window: 1050000
      max_tokens: 1050000
      max_output_tokens: 128000
      supports_reasoning: true
      supports_vision: true
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

See the [recipe YAML](https://github.com/nilayparikh/codefreedom-recipes/tree/main/azure-openai/proxy/config/providers/azure-foundry.yaml) for all model entries (Mini and Nano have smaller context windows and different pricing).

## Enabling

1. Uncomment model entries in `azure-foundry.yaml`.
2. Ensure `providers/azure-foundry.yaml` is in the `include` list in `config.yaml`.
3. Set `MICROSOFT_FOUNDRY_API_BASE` and `MICROSOFT_FOUNDRY_API_KEY` in `~/.codefreedom/.env.proxy.secrets`.
4. Restart the proxy.
