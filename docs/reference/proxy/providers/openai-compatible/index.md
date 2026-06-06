---
description: OpenAI-compatible endpoint — connect any /v1/chat/completions server.
---

# OpenAI Compatible

Connect any service that exposes an OpenAI-compatible `/v1/chat/completions` endpoint. This includes self-hosted backends (llama.cpp, Ollama, vLLM), third-party proxies, or custom inference servers.

**Provider file:** `~/.codefreedom/proxy/config/providers/openai-compatible.yaml`

## Environment Variables

| Variable                 | Description                                         | Required |
| ------------------------ | --------------------------------------------------- | -------- |
| `OPENAI_COMPAT_BASE_URL` | Your endpoint URL (e.g. `http://localhost:8000/v1`) | Yes      |
| `OPENAI_COMPAT_API_KEY`  | API key (or placeholder like `sk-dummy`)            | Yes      |
| `OPENAI_COMPAT_MODEL`    | Model identifier (e.g. `openai/llama-3-70b`)        | Yes      |

## Available Models

| Model                 | Configuration Style                             |
| --------------------- | ----------------------------------------------- |
| [Default](default.md) | Single template model — copy/extend to add more |

The "Default" model is a template entry you copy to register additional endpoints.

## Generic Configuration

```yaml
model_list:
  - model_name: OpenAI-Compatible/Default
    litellm_params: &openai_compat_params
      # The model identifier is fully env-driven, so you can swap
      # models without editing the YAML. LiteLLM reads the value
      # from the env var at request time.
      model: openai/os.environ/OPENAI_COMPAT_MODEL
      api_base: os.environ/OPENAI_COMPAT_BASE_URL
      api_key: os.environ/OPENAI_COMPAT_API_KEY
      timeout: 300
      drop_params: true
      max_tokens: 131072
      max_completion_tokens: 16384
      extra_body:
        # Request usage metadata in the streaming response.
        stream_options:
          include_usage: true
    model_info: &openai_compat_model_info
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

### Common Field Notes

- **`model: openai/os.environ/OPENAI_COMPAT_MODEL`** — Special syntax where the value of `OPENAI_COMPAT_MODEL` is substituted at runtime. Change the env var to swap models without restarting the proxy.
- **`api_key: sk-dummy`** — Many self-hosted servers don't actually validate the key but still require a non-empty value. `sk-dummy` is the conventional placeholder.
- **`max_tokens: 131072` and `max_completion_tokens: 16384`** — Reasonable defaults for a 128K-context local model. Adjust to match your actual model's spec.
- **Adding more models** — Copy the block, set a unique `model_name`, override `model`/`api_base`/`api_key`, and adjust `model_info` per model.

## Enabling

1. Uncomment the model entries in `openai-compatible.yaml` (commented by default in the example).
2. Uncomment `providers/openai-compatible.yaml` in the `include` list in `config.yaml`.
3. Set `OPENAI_COMPAT_BASE_URL`, `OPENAI_COMPAT_API_KEY`, and `OPENAI_COMPAT_MODEL` in `~/.codefreedom/.env.proxy.secrets`.

## Per-Model Details

See the dedicated page for the template model:

- [Default](default.md) — single template entry, copy to extend
