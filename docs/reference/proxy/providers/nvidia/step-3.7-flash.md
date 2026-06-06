---
description: NVIDIA/Step-3.7-Flash — 262K context, vision, fast variant.
---

# NVIDIA / Step-3.7-Flash

StepFun Step 3.7 Flash routed through NVIDIA AI Endpoints. 262K context window with vision support. Fast-tier variant of the Step-3.7 family.

**LiteLLM model:** `openai/stepfun-ai/step-3.7-flash`
**Context window:** 262,144 tokens
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
- model_name: NVIDIA/Step-3.7-Flash
  litellm_params:
    model: openai/stepfun-ai/step-3.7-flash
    api_base: os.environ/NVIDIA_BASE_URL
    api_key: os.environ/NVIDIA_API_KEY
    timeout: 300
    drop_params: true
    extra_body:
      # Request usage metadata in the streaming response.
      stream_options:
        include_usage: true
  model_info:
    id: "nvidia-step-3-7-flash"
    db_model: false
    supports_reasoning: true
    mode: chat
    context_window: 262144
    max_tokens: 262144
    max_input_tokens: 245760
    max_output_tokens: 16384
    limit:
      context: 262144
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

- Use for: vision + reasoning at mid-range speed, code generation with image inputs.
- **`model: openai/stepfun-ai/step-3.7-flash`** — Uses the `openai/` prefix like other NVIDIA models, with the full `stepfun-ai/step-3.7-flash` path as the model identifier.
- **Flash tier** — Lower latency than the full Step-3.7 model. Suitable for interactive use.
- Source: [build.nvidia.com/stepfun-ai/step-3.7-flash](https://build.nvidia.com/stepfun-ai/step-3.7-flash/modelcard)

See [NVIDIA provider](index.md) for the generic schema and enabling steps.
