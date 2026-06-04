---
description: Anthropic-compatible endpoint — connect any /v1/messages server.
---

# Anthropic Compatible

Connect any service that exposes an Anthropic-compatible `/v1/messages` endpoint — self-hosted backends, third-party proxies, or gateways that speak the Anthropic protocol.

**File:** `~/.codefreedom/proxy/config/providers/anthropic-compatible.yaml`

## Environment Variables

| Variable | Description | Default |
| --- | --- | --- |
| `ANTHROPIC_COMPAT_BASE_URL` | Your endpoint URL | `http://localhost:8000` |
| `ANTHROPIC_COMPAT_API_KEY` | API key (or placeholder) | `sk-dummy` |
| `ANTHROPIC_COMPAT_MODEL` | Model identifier | `claude-sonnet-4-20250514` |

## Example Configuration

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
      mode: chat
      context_window: 200000
      max_tokens: 200000
      supports_system_messages: true
      supports_native_streaming: true
      supports_vision: true
```

- **`model: anthropic/os.environ/...`** — Uses LiteLLM's Anthropic integration. The model name comes from env vars for flexibility.
- **Anthropic-to-OpenAI translation** — The proxy's `use_chat_completions_url_for_anthropic_messages: true` setting (in `config.yaml`) translates Anthropic format to OpenAI for non-Anthropic backends. See [Configuration](../config.md).

## Enabling

1. Uncomment the model entries in `anthropic-compatible.yaml`.
2. Uncomment `providers/anthropic-compatible.yaml` in the `include` list.
3. Set `ANTHROPIC_COMPAT_BASE_URL`, `ANTHROPIC_COMPAT_API_KEY`, and `ANTHROPIC_COMPAT_MODEL` in `.env.proxy.secrets`.
