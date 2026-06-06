---
description: NVIDIA/GLM-5.1 — 204K context with custom sampling parameters.
---

# NVIDIA / GLM-5.1

Z-AI GLM 5.1 routed through NVIDIA AI Endpoints. 204K context window, 8K max output. Uses custom sampling parameters.

**LiteLLM model:** `openai/z-ai/glm-5.1`
**Context window:** 204,800 tokens
**Max output:** 8,192 tokens

## Capabilities

| Capability       | Supported |
| ---------------- | --------- |
| Vision           | No        |
| Reasoning        | Yes       |
| Native streaming | Yes       |
| System messages  | Yes       |
| Tool use         | Yes       |

## Configuration

```yaml
- model_name: NVIDIA/GLM-5.1
  litellm_params:
    model: openai/z-ai/glm-5.1
    api_base: os.environ/NVIDIA_BASE_URL
    api_key: os.environ/NVIDIA_API_KEY
    timeout: 300
    drop_params: true
    extra_body:
      # GLM uses a different sampling distribution than the OpenAI
      # default. The model works best with these specific values.
      temperature: 1.0
      top_p: 0.95
      top_k: 40
      # Request usage metadata in the streaming response.
      stream_options:
        include_usage: true
  model_info:
    id: "nvidia-glm-5-1"
    db_model: false
    supports_reasoning: true
    mode: chat
    context_window: 204800
    max_tokens: 204800
    max_input_tokens: 196608
    max_output_tokens: 8192
    limit:
      context: 204800
      output: 8192
    supports_system_messages: true
    supports_native_streaming: true
    supports_vision: false
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

- Use for: code generation, math, structured reasoning in Chinese and English.
- **`temperature: 1.0`**, **`top_p: 0.95`**, **`top_k: 40`** — GLM's recommended sampling. The OpenAI default (`temperature: 1.0`, `top_p: 1.0`) works less well on this model.
- **`max_output_tokens: 8192`** is small relative to the 204K context. Plan for short generations.
- Source: [build.nvidia.com/z-ai/glm-5.1](https://build.nvidia.com/z-ai/glm-5.1/modelcard)

See [NVIDIA provider](index.md) for the generic schema and enabling steps.
