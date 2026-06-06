---
description: NVIDIA/Kimi-K2.6 — 256K context, vision, with thinking mode.
---

# NVIDIA / Kimi-K2.6

Moonshot Kimi K2.6 routed through NVIDIA AI Endpoints. 256K context window with vision and thinking mode support.

**LiteLLM model:** `openai/moonshotai/kimi-k2.6`
**Context window:** 256,000 tokens
**Max output:** 16,384 tokens

## Capabilities

| Capability       | Supported |
| ---------------- | --------- |
| Vision           | Yes       |
| Reasoning        | Yes       |
| Native streaming | Yes       |
| System messages  | Yes       |
| Tool use         | Yes       |

## Configuration

```yaml
- model_name: NVIDIA/Kimi-K2.6
  litellm_params:
    model: openai/moonshotai/kimi-k2.6
    api_base: os.environ/NVIDIA_BASE_URL
    api_key: os.environ/NVIDIA_API_KEY
    timeout: 300
    drop_params: true
    extra_body:
      # Enable chain-of-thought. Without this, the model returns
      # direct answers without showing reasoning.
      chat_template_kwargs:
        thinking: true
      # Request usage metadata in the streaming response.
      stream_options:
        include_usage: true
  model_info:
    id: "nvidia-openai-kimi-k2-6"
    db_model: false
    supports_reasoning: true
    mode: chat
    context_window: 256000
    max_tokens: 256000
    max_input_tokens: 256000
    max_output_tokens: 16384
    limit:
      context: 256000
      output: 16384
    supports_system_messages: true
    supports_native_streaming: true
    supports_vision: true
    # Full list of OpenAI parameters this model accepts. Repeated
    # inline in every model file so each page is self-contained —
    # copy/paste a single model block without re-defining anchors.
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
      - thinking
      - reasoning_effort
```

## Notes

- Use for: long-context reasoning, document analysis, multi-step planning.
- **`chat_template_kwargs.thinking: true`** — Kimi-specific. Enables the chain-of-thought mode where the model shows its reasoning before the final answer.
- **`max_input_tokens: 256000` equals `max_tokens`** — the entire context window is available as input. The model is tuned for "stuff the whole context" use cases.
- Source: [build.nvidia.com/moonshotai/kimi-k2.6](https://build.nvidia.com/moonshotai/kimi-k2.6/modelcard)

See [NVIDIA provider](index.md) for the generic schema and enabling steps.
