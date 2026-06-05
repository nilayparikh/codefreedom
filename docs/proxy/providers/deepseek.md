---
description: DeepSeek provider — V4-Flash and V4-Pro via deepseek.com.
---

# DeepSeek

[DeepSeek](https://www.deepseek.com/) offers fast, cost-effective reasoning models. Both V4-Flash and V4-Pro support extended context (1M tokens) and structured reasoning.

**File:** `~/.codefreedom/proxy/config/providers/deepseek.yaml`

## Environment Variables

| Variable | Description | Default |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | API key from [DeepSeek](https://www.deepseek.com/) | (required) |
| `DEEPSEEK_BASE_URL` | API base URL | `https://api.deepseek.com` |

## Available Models

| Model | LiteLLM ID | Context | Max Output | Reasoning | Cost (input) | Cost (output) |
| --- | --- | --- | --- | --- | --- | --- |
| DeepSeek-V4-Flash | `deepseek/deepseek-v4-flash` | 1,000,000 | 384,000 | Yes | $0.00000014/10k | $0.00000028/10k |
| DeepSeek-V4-Pro | `deepseek/deepseek-v4-pro` | 1,000,000 | 384,000 | Yes | $0.00000174/10k | $0.00000348/10k |

## Example Configuration

```yaml
model_list:
  - model_name: DeepSeek/DeepSeek-V4-Flash
    litellm_params:
      model: deepseek/deepseek-v4-flash
      api_base: os.environ/DEEPSEEK_BASE_URL
      api_key: os.environ/DEEPSEEK_API_KEY
      timeout: 300
      drop_params: true
    model_info:
      id: "deepseek-openai-deepseek-v4-flash"
      mode: chat
      context_window: 1000000
      max_tokens: 1000000
      supports_reasoning: true
      supports_vision: false
      input_cost_per_token: 0.00000014
      output_cost_per_token: 0.00000028
```

- **`model: deepseek/...`** — Uses LiteLLM's native DeepSeek integration. See [LiteLLM DeepSeek docs](https://docs.litellm.ai/docs/providers/deepseek).
- **`drop_params: true`** — Strips params DeepSeek doesn't support, preventing 400 errors.
- **`model_info`** — Declares 1M context, reasoning support, and per-token costs for spend tracking.
- **`supported_openai_params`** — Lists which OpenAI API parameters the model accepts (tools, thinking, stream, etc.).

V4-Pro follows the same structure with `deepseek/deepseek-v4-pro` and higher pricing. Both models share a `supported_openai_params` anchor.

## Enabling

1. Ensure the model entries in `deepseek.yaml` are uncommented (they are by default).
2. Ensure `providers/deepseek.yaml` is in the `include` list.
3. Set `DEEPSEEK_API_KEY` in `~/.codefreedom/.env.proxy.secrets`.
