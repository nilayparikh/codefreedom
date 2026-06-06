---
description: OpenAI-Compatible/Default — template entry, copy to add more endpoints.
---

# OpenAI-Compatible / Default

Template entry for a single OpenAI-compatible endpoint. Copy the block to register additional endpoints with different `model_name`, `model`, `api_base`, and `model_info`.

**LiteLLM model:** `openai/${OPENAI_COMPAT_MODEL}` (resolved at request time)
**Default context window:** 131,072 tokens
**Default max output:** 16,384 tokens

## Capabilities (defaults — adjust to your model)

| Capability       | Supported |
| ---------------- | --------- |
| Vision           | No        |
| Reasoning        | No        |
| Native streaming | Yes       |
| System messages  | Yes       |
| Tool use         | Yes       |

## Configuration

```yaml
- model_name: OpenAI-Compatible/Default
  litellm_params:
    # The "openai/os.environ/VAR" form reads the model name from
    # the env var at request time. Change OPENAI_COMPAT_MODEL in
    # .env.proxy and restart to swap models without editing YAML.
    model: openai/os.environ/OPENAI_COMPAT_MODEL
    api_base: os.environ/OPENAI_COMPAT_BASE_URL
    api_key: os.environ/OPENAI_COMPAT_API_KEY
    timeout: 300
    drop_params: true
    max_tokens: 131072
    max_completion_tokens: 16384
    extra_body:
      # Ask the upstream to include usage metadata in the streaming
      # response. Most OpenAI-compatible servers respect this flag;
      # drop it if your server returns an error.
      stream_options:
        include_usage: true
  model_info:
    id: "openai-compat-default"
    db_model: false
    mode: chat
    context_window: 131072
    max_tokens: 131072
    max_input_tokens: 114688
    max_output_tokens: 16384
    supports_system_messages: true
    supports_native_streaming: true
    supports_vision: false
    supported_openai_params:
      - tools
      - tool_choice
      - parallel_tool_calls
      - response_format
      - max_tokens
      - max_completion_tokens
      - stream
      - stream_options
      - temperature
      - top_p
      - stop
```

## Notes

- Use for: llama.cpp server, Ollama, vLLM, LM Studio, third-party proxies, any `/v1/chat/completions` endpoint.
- **`api_key: sk-dummy`** — Required even when the server doesn't validate, because LiteLLM checks for a non-empty value.
- **Adding more models** — Copy this block, change `model_name`, point `model`/`api_base` at the new endpoint, and adjust `model_info` to match the new model's spec.
- **`drop_params: true`** — Strips unsupported params before forwarding. Useful when the local server has a partial OpenAI implementation.

See [OpenAI-Compatible provider](index.md) for the generic schema and enabling steps.
