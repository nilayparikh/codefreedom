---
description: OpenAI-compatible endpoint — connect any /v1/chat/completions server.
---

# OpenAI Compatible

Connect any service that exposes an OpenAI-compatible `/v1/chat/completions` endpoint: self-hosted backends (llama.cpp, Ollama, vLLM), third-party proxies, or custom inference servers.

**Provider file:** `~/.codefreedom/proxy/config/providers/openai-compatible.yaml`

## Environment Variables

| Variable                 | Description                                         | Required |
| ------------------------ | --------------------------------------------------- | -------- |
| `OPENAI_COMPAT_BASE_URL` | Your endpoint URL (e.g. `http://localhost:8000/v1`) | Yes      |
| `OPENAI_COMPAT_API_KEY`  | API key (or placeholder like `sk-dummy`)            | Yes      |
| `OPENAI_COMPAT_MODEL`    | Model identifier (e.g. `openai/llama-3-70b`)        | Yes      |

## Configuration

```yaml
model_list:
  - model_name: OpenAI-Compatible/Default
    litellm_params:
      model: openai/os.environ/OPENAI_COMPAT_MODEL
      api_base: os.environ/OPENAI_COMPAT_BASE_URL
      api_key: os.environ/OPENAI_COMPAT_API_KEY
      timeout: 300
      drop_params: true
      extra_body:
        stream_options:
          include_usage: true
    model_info:
      id: "openai-compat-default"
      db_model: false
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
        - frequency_penalty
        - presence_penalty
        - response_format
        - seed
```

Copy this block for each additional endpoint, adjusting `model_name`, `model`, `api_base`, and `model_info` as needed.

## Enabling

1. Ensure `providers/openai-compatible.yaml` is in the `include` list in `config.yaml`.
2. Set `OPENAI_COMPAT_BASE_URL`, `OPENAI_COMPAT_API_KEY`, and `OPENAI_COMPAT_MODEL` in `~/.codefreedom/.env.proxy.secrets`.
3. Restart the proxy.
