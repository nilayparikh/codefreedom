---
description: Local provider — self-hosted inference servers on separate ports.
---

# Local

Route to inference servers running on your machine. Two pre-configured models on separate ports let you run a primary coding model and a fast fallback simultaneously.

**Provider file:** `~/.codefreedom/proxy/config/providers/local.yaml`

## Environment Variables

| Variable           | Description             | Default                               |
| ------------------ | ----------------------- | ------------------------------------- |
| `LOCAL_M_BASE_URL` | Primary model URL       | `http://host.docker.internal:8000/v1` |
| `LOCAL_M_API_KEY`  | Primary model API key   | `sk-dummy`                            |
| `LOCAL_S_BASE_URL` | Secondary model URL     | `http://host.docker.internal:8001/v1` |
| `LOCAL_S_API_KEY`  | Secondary model API key | `sk-dummy`                            |

> **Docker mode:** URLs use `host.docker.internal` to reach host ports (included by default in the compose file).
> **Native mode:** Use `localhost` instead.

## Models

| Model           | Port               | Context | Max Output | Reasoning | Vision |
| --------------- | ------------------ | ------- | ---------- | --------- | ------ |
| Qwen3.6-27B     | 8000 (`LOCAL_M_*`) | 131,072 | 16,384     | Yes       | No     |
| Qwen3.6-35B-A3B | 8001 (`LOCAL_S_*`) | 262,144 | 16,384     | Yes       | No     |

## Configuration

```yaml
model_list:
  - model_name: DGX/Qwen3.6-27B
    litellm_params:
      model: openai/qwen3.6_27b
      api_base: os.environ/LOCAL_M_BASE_URL
      api_key: os.environ/LOCAL_M_API_KEY
      timeout: 300
      include_reasoning: true
      max_tokens: 131072
      extra_body:
        seed: 42
        temperature: 0.0
        top_p: 1.0
        stream_options:
          include_usage: true
    model_info:
      id: "local-qwen3.6-27b"
      db_model: false
      supports_reasoning: true
      mode: chat
      context_window: 131072
      max_tokens: 131072
      supports_system_messages: true
      supports_native_streaming: true
      supports_vision: false
      supported_openai_params:
        - tools
        - tool_choice
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
        - seed
```

See the [recipe YAML](https://github.com/nilayparikh/codefreedom-recipes/tree/main/local/proxy/config/providers/local.yaml) for the full file including model-specific fields like `max_thinking_tokens` and `chat_template_kwargs`.

## Enabling

1. Ensure `providers/local.yaml` is in the `include` list in `config.yaml`.
2. Set `LOCAL_M_BASE_URL` / `LOCAL_S_BASE_URL` in `~/.codefreedom/.env.proxy.secrets` (defaults work for local inference servers).
3. Restart the proxy.
