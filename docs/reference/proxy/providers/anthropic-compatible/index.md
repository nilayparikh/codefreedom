---
description: Anthropic-compatible endpoint — connect any /v1/messages server.
---

# Anthropic Compatible

Connect any service that exposes an Anthropic-compatible `/v1/messages` endpoint. This includes self-hosted backends with Anthropic API compatibility, third-party proxies, or gateways that speak the Anthropic protocol.

**Provider file:** `~/.codefreedom/proxy/config/providers/anthropic-compatible.yaml`

## Environment Variables

| Variable                    | Description                                        | Required |
| --------------------------- | -------------------------------------------------- | -------- |
| `ANTHROPIC_COMPAT_BASE_URL` | Your endpoint URL (e.g. `http://localhost:8000`)   | Yes      |
| `ANTHROPIC_COMPAT_API_KEY`  | API key (or placeholder like `sk-dummy`)           | Yes      |
| `ANTHROPIC_COMPAT_MODEL`    | Model identifier (e.g. `claude-sonnet-4-20250514`) | Yes      |

## Available Models

| Model                 | Configuration Style                             |
| --------------------- | ----------------------------------------------- |
| [Default](default.md) | Single template model — copy/extend to add more |

The "Default" model is a template entry you copy to register additional endpoints.

## Generic Configuration

```yaml
model_list:
  - model_name: Anthropic-Compatible/Default
    litellm_params: &anthropic_compat_params
      # Use the "anthropic/" provider prefix so LiteLLM sends the
      # request in Anthropic Messages format, not OpenAI format.
      # The model name is fully env-driven for flexibility.
      model: anthropic/os.environ/ANTHROPIC_COMPAT_MODEL
      api_base: os.environ/ANTHROPIC_COMPAT_BASE_URL
      api_key: os.environ/ANTHROPIC_COMPAT_API_KEY
      timeout: 300
      drop_params: true
      max_tokens: 4096
    model_info: &anthropic_compat_model_info
      id: "anthropic-compat-default"
      db_model: false
      mode: chat
      context_window: 200000
      max_tokens: 200000
      max_input_tokens: 190000
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
        - top_p
        - stop
```

### Common Field Notes

- **`model: anthropic/os.environ/ANTHROPIC_COMPAT_MODEL`** — The `anthropic/` prefix tells LiteLLM to send the request in Anthropic Messages API format. Change the env var to swap models without editing YAML.
- **`max_tokens: 4096`** — Conservative default. The Anthropic Messages API requires `max_tokens` in every request, so this sets a baseline. Adjust to match the model's actual capacity.
- **`supports_vision: true`** — Default-on for Anthropic-compatible endpoints. Set to `false` for text-only servers.
- **Anthropic-to-OpenAI translation** — The proxy's `use_chat_completions_url_for_anthropic_messages: true` setting (in `config.yaml`) translates Anthropic format to OpenAI for non-Anthropic backends. See [Configuration](../../config.md).

## Enabling

1. Uncomment the model entries in `anthropic-compatible.yaml` (commented by default in the example).
2. Uncomment `providers/anthropic-compatible.yaml` in the `include` list in `config.yaml`.
3. Set `ANTHROPIC_COMPAT_BASE_URL`, `ANTHROPIC_COMPAT_API_KEY`, and `ANTHROPIC_COMPAT_MODEL` in `~/.codefreedom/.env.proxy.secrets`.

## Per-Model Details

See the dedicated page for the template model:

- [Default](default.md) — single template entry, copy to extend
