---
description: Azure Foundry provider — GPT-5.4 family via Microsoft Foundry.
---

# Azure Foundry

[Microsoft Azure AI Foundry](https://www.azure.ai/) provides access to OpenAI's GPT-5.4 family through a unified, OpenAI-compatible API. All models use the `openai/gpt-*` LiteLLM format.

**Provider file:** `~/.codefreedom/proxy/config/providers/azure-foundry.yaml`

## Environment Variables

| Variable                     | Description                                                                | Required |
| ---------------------------- | -------------------------------------------------------------------------- | -------- |
| `MICROSOFT_FOUNDRY_API_BASE` | Project API base URL (`https://<project>.services.ai.azure.com/openai/v1`) | Yes      |
| `MICROSOFT_FOUNDRY_API_KEY`  | API key from Azure AI Foundry                                              | Yes      |

## Available Models

| Model                           | Context   | Max Output | Vision | Reasoning |
| ------------------------------- | --------- | ---------- | ------ | --------- |
| [GPT-5.4](gpt-5.4.md)           | 1,050,000 | 128,000    | Yes    | Yes       |
| [GPT-5.4-Mini](gpt-5.4-mini.md) | 400,000   | 128,000    | Yes    | Yes       |
| [GPT-5.4-Nano](gpt-5.4-nano.md) | 400,000   | 128,000    | Yes    | Yes       |

## Generic Configuration

The three GPT-5.4 family models share the same shape. Each entry in `azure-foundry.yaml` looks like:

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

### Common Field Notes

- **`model: openai/gpt-*`** — Azure Foundry uses the OpenAI-compatible endpoint with standard GPT model names.
- **`extra_body.stream_options`** — Requests usage metadata in streaming responses for cost tracking.
- **`drop_params: true`** — Strips unsupported params to prevent 400 errors from upstream.
- **`cached_input_cost_per_token`** — Tracks discounted pricing for cached input, which is significant for repeated context.
- **Per-model overrides** — `model_name`, `model`, `id`, context window, and pricing differ across the three models.

## Enabling

1. Uncomment the model entries in `azure-foundry.yaml` (commented by default in the example).
2. Ensure `providers/azure-foundry.yaml` is in the `include` list in `config.yaml`.
3. Set `MICROSOFT_FOUNDRY_API_BASE` and `MICROSOFT_FOUNDRY_API_KEY` in `~/.codefreedom/.env.proxy.secrets`.

## Per-Model Details

See each model's dedicated page for full `model_info`, pricing, and supported parameters:

- [GPT-5.4](gpt-5.4.md) — flagship, 1.05M context
- [GPT-5.4-Mini](gpt-5.4-mini.md) — mid-tier, 400K context
- [GPT-5.4-Nano](gpt-5.4-nano.md) — fast/small, 400K context
