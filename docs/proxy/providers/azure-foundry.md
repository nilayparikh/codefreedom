---
description: Azure Foundry provider — GPT-5.4, GPT-5.4-mini, GPT-5.4-nano via Microsoft Foundry.
---

# Azure Foundry

[Microsoft Azure AI Foundry](https://www.azure.ai/) provides access to GPT-5.4 family models through a unified API. Models use the `openai/gpt-*` LiteLLM format.

**File:** `~/.codefreedom/proxy/config/providers/azure-foundry.yaml`

## Environment Variables

| Variable | Description | Default |
| --- | --- | --- |
| `MICROSOFT_FOUNDRY_API_KEY` | API key from Azure AI Foundry | (required) |
| `MICROSOFT_FOUNDRY_API_BASE` | Project API base URL | `https://<project>.services.ai.azure.com/openai/v1` |

## Available Models

| Model | LiteLLM ID | Context | Max Output | Vision | Reasoning |
| --- | --- | --- | --- | --- | --- |
| GPT-5.4 | `openai/gpt-5.4` | 1,050,000 | 128,000 | Yes | Yes |
| GPT-5.4-mini | `openai/gpt-5.4-mini` | 400,000 | 128,000 | Yes | Yes |
| GPT-5.4-nano | `openai/gpt-5.4-nano` | 400,000 | 128,000 | Yes | Yes |

## Example Configuration

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
```

- **`model: openai/gpt-*`** — Azure Foundry uses the OpenAI-compatible endpoint with standard GPT model names.
- **`extra_body.stream_options`** — Requests usage metadata in the streaming response for cost tracking.
- **`drop_params: true`** — Strips unsupported params to prevent 400 errors.
- **`cached_input_cost_per_token`** — Tracks discounted pricing for cached input.

All three models share the same structure with different `model`, `id`, and capacity values.

## Enabling

1. Ensure the model entries in `azure-foundry.yaml` are uncommented (they are by default).
2. Ensure `providers/azure-foundry.yaml` is in the `include` list.
3. Set `MICROSOFT_FOUNDRY_API_BASE` and `MICROSOFT_FOUNDRY_API_KEY` in `.env.proxy.secrets`.
