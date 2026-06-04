---
description: OpenAI-compatible endpoint — connect any /v1/chat/completions server.
---

# OpenAI Compatible

Connect any service that exposes an OpenAI-compatible `/v1/chat/completions` endpoint — self-hosted backends (llama.cpp, Ollama, vLLM), third-party proxies, or custom inference servers.

**File:** `~/.codefreedom/proxy/config/providers/openai-compatible.yaml`

## Environment Variables

| Variable | Description | Default |
| --- | --- | --- |
| `OPENAI_COMPAT_BASE_URL` | Your endpoint URL | `http://localhost:8000/v1` |
| `OPENAI_COMPAT_API_KEY` | API key (or placeholder) | `sk-dummy` |
| `OPENAI_COMPAT_MODEL` | Model identifier | `openai/your-model` |

## Example Configuration

```yaml
model_list:
  - model_name: OpenAI-Compatible/Default
    litellm_params:
      model: openai/os.environ/OPENAI_COMPAT_MODEL
      api_base: os.environ/OPENAI_COMPAT_BASE_URL
      api_key: os.environ/OPENAI_COMPAT_API_KEY
      timeout: 300
      drop_params: true
      max_tokens: 131072
      max_completion_tokens: 16384
      extra_body:
        stream_options:
          include_usage: true
    model_info:
      mode: chat
      context_window: 131072
      max_tokens: 131072
      supports_system_messages: true
      supports_native_streaming: true
      supports_vision: false
```

- **`model: openai/os.environ/...`** — The model name is fully configurable via env vars, so you can swap models without editing the YAML.
- Copy the block to add more models, adjusting `model_name`, `model`, and `model_info` for each.

## Enabling

1. Uncomment the model entries in `openai-compatible.yaml`.
2. Uncomment `providers/openai-compatible.yaml` in the `include` list.
3. Set `OPENAI_COMPAT_BASE_URL`, `OPENAI_COMPAT_API_KEY`, and `OPENAI_COMPAT_MODEL` in `.env.proxy.secrets`.
