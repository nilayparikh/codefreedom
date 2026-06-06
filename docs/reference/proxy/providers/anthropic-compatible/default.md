---
description: Anthropic-Compatible/Default — template entry, copy to add more endpoints.
---

# Anthropic-Compatible / Default

Template entry for a single Anthropic-compatible endpoint. Copy the block to register additional endpoints with different `model_name`, `model`, `api_base`, and `model_info`.

**LiteLLM model:** `anthropic/${ANTHROPIC_COMPAT_MODEL}` (resolved at request time)
**Default context window:** 200,000 tokens
**Default max output:** 4,096 tokens

## Capabilities (defaults — adjust to your model)

| Capability       | Supported |
| ---------------- | --------- |
| Vision           | Yes       |
| Reasoning        | No        |
| Native streaming | Yes       |
| System messages  | Yes       |
| Tool use         | Yes       |

## Configuration

```yaml
- model_name: Anthropic-Compatible/Default
  litellm_params:
    # The "anthropic/os.environ/VAR" form reads the model name from
    # the env var at request time. Change ANTHROPIC_COMPAT_MODEL in
    # .env.proxy and restart to swap models without editing YAML.
    model: anthropic/os.environ/ANTHROPIC_COMPAT_MODEL
    api_base: os.environ/ANTHROPIC_COMPAT_BASE_URL
    api_key: os.environ/ANTHROPIC_COMPAT_API_KEY
    timeout: 300
    drop_params: true
    # Anthropic Messages API requires max_tokens in every request.
    # Set this to the model's actual max output, not the context.
    max_tokens: 4096
  model_info:
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

## Notes

- Use for: self-hosted Anthropic-API-compatible servers, third-party gateways that speak the Anthropic protocol.
- **`api_key: sk-dummy`** — Required even when the server doesn't validate, because LiteLLM checks for a non-empty value.
- **`max_tokens: 4096`** — Anthropic API requirement. Most compatible servers will reject requests without it. Adjust per the upstream model's spec.
- **Adding more models** — Copy this block, change `model_name`, point `model`/`api_base` at the new endpoint, and adjust `model_info` to match the new model's spec.

See [Anthropic-Compatible provider](index.md) for the generic schema and enabling steps.
