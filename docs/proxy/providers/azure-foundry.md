---
description: Azure Foundry provider — Kimi, GLM, DeepSeek via Microsoft Foundry.
---

# Azure Foundry

[Microsoft Azure AI Foundry](https://www.azure.ai/) provides access to open-source models through a unified API. Models use the `openai/FW-*` LiteLLM format.

**File:** `~/.codefreedom/proxy/config/providers/azure-foundry.yaml`

## Environment Variables

| Variable | Description | Default |
| --- | --- | --- |
| `MICROSOFT_FOUNDRY_API_KEY` | API key from Azure AI Foundry | (required) |
| `MICROSOFT_FOUNDRY_API_BASE` | Project API base URL | `https://<project>.services.ai.azure.com/openai/v1` |

## Example Configuration

```yaml
model_list:
  - model_name: Azure/Kimi-K2.6
    litellm_params:
      model: openai/FW-Kimi-K2.6
      api_base: os.environ/MICROSOFT_FOUNDRY_API_BASE
      api_key: os.environ/MICROSOFT_FOUNDRY_API_KEY
      timeout: 300
      drop_params: true
      extra_body:
        stream_options:
          include_usage: true
    model_info:
      mode: chat
      context_window: 262144
      max_tokens: 262144
      supports_reasoning: true
      supports_vision: true
      input_cost_per_token: 0.00000095
      output_cost_per_token: 0.00000400
```

- **`model: openai/FW-*`** — Azure Foundry uses the OpenAI-compatible endpoint with `FW-` prefixed model names.
- **`extra_body.stream_options`** — Requests usage metadata in the streaming response for cost tracking.
- Other models (GLM-5.1, DeepSeek-V4-Pro) follow the same pattern with different `FW-*` names.

## Enabling

1. Uncomment the model entries in `azure-foundry.yaml`.
2. Ensure `providers/azure-foundry.yaml` is in the `include` list.
3. Set `MICROSOFT_FOUNDRY_API_BASE` and `MICROSOFT_FOUNDRY_API_KEY` in `.env.proxy.secrets`.
