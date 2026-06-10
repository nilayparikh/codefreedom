---
description: DeepSeek provider — V4-Flash and V4-Pro via deepseek.com.
---

# DeepSeek

[DeepSeek](https://www.deepseek.com/) offers fast, cost-effective reasoning models. Both V4-Flash and V4-Pro support extended context (1M tokens) and structured reasoning.

**Provider file:** `~/.codefreedom/proxy/config/providers/deepseek.yaml`

## Environment Variables

| Variable            | Description                                        | Required                                 |
| ------------------- | -------------------------------------------------- | ---------------------------------------- |
| `DEEPSEEK_API_KEY`  | API key from [DeepSeek](https://www.deepseek.com/) | Yes                                      |
| `DEEPSEEK_BASE_URL` | API base URL                                       | No (default: `https://api.deepseek.com`) |

## Models

| Model             | Context   | Max Output | Reasoning | Input $/1M | Output $/1M |
| ----------------- | --------- | ---------- | --------- | ---------- | ----------- |
| DeepSeek-V4-Flash | 1,000,000 | 384,000    | Yes       | $0.14      | $0.28       |
| DeepSeek-V4-Pro   | 1,000,000 | 384,000    | Yes       | $1.74      | $3.48       |

## Configuration

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
      db_model: false
      supports_reasoning: true
      mode: chat
      context_window: 1000000
      max_tokens: 1000000
      max_input_tokens: 616000
      max_output_tokens: 384000
      supports_system_messages: true
      supports_native_streaming: true
      supports_vision: false
      input_cost_per_token: 0.00000014
      output_cost_per_token: 0.00000028
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

See the [recipe YAML](https://github.com/nilayparikh/codefreedom-recipes/tree/main/deepseek/proxy/config/providers/deepseek.yaml) for the full file with both models.

## Enabling

1. Uncomment model entries in `deepseek.yaml`.
2. Ensure `providers/deepseek.yaml` is in the `include` list in `config.yaml`.
3. Set `DEEPSEEK_API_KEY` in `~/.codefreedom/.env.proxy.secrets`.
4. Restart the proxy.
