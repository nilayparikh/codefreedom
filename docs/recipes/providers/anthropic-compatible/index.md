---
description: Anthropic-compatible endpoint — connect any /v1/messages server.
---

# Anthropic Compatible

Connect any service that exposes an Anthropic-compatible `/v1/messages` endpoint: self-hosted backends, third-party proxies, or gateways that speak the Anthropic protocol.

**Provider file:** `~/.codefreedom/proxy/config/providers/anthropic-compatible.yaml`

## Environment Variables

| Variable                    | Description                                        | Required |
| --------------------------- | -------------------------------------------------- | -------- |
| `ANTHROPIC_COMPAT_BASE_URL` | Your endpoint URL (e.g. `http://localhost:8000`)   | Yes      |
| `ANTHROPIC_COMPAT_API_KEY`  | API key (or placeholder like `sk-dummy`)           | Yes      |
| `ANTHROPIC_COMPAT_MODEL`    | Model identifier (e.g. `claude-sonnet-4-20250514`) | Yes      |

## Configuration

```yaml
model_list:
  - model_name: Anthropic-Compatible/Default
    litellm_params:
      model: anthropic/os.environ/ANTHROPIC_COMPAT_MODEL
      api_base: os.environ/ANTHROPIC_COMPAT_BASE_URL
      api_key: os.environ/ANTHROPIC_COMPAT_API_KEY
      timeout: 300
      drop_params: true
      max_tokens: 4096
    model_info:
      id: "anthropic-compat-default"
      db_model: false
      mode: chat
      context_window: 200000
      max_tokens: 200000
      max_output_tokens: 4096
      supports_system_messages: true
      supports_native_streaming: true
      supports_vision: true
      supported_openai_params:
        - tools
        - tool_choice
        - max_tokens
        - max_completion_tokens
        - stream
        - stream_options
        - temperature
```

Use the `anthropic/` provider prefix so LiteLLM sends the request in Anthropic Messages format. Copy this block for each additional endpoint, adjusting `model`, `api_base`, and `model_info` as needed.

## Enabling

1. Ensure `providers/anthropic-compatible.yaml` is in the `include` list in `config.yaml`.
2. Set `ANTHROPIC_COMPAT_BASE_URL`, `ANTHROPIC_COMPAT_API_KEY`, and `ANTHROPIC_COMPAT_MODEL` in `~/.codefreedom/.env.proxy.secrets`.
3. Restart the proxy.
