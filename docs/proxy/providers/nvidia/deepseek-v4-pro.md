---
description: NVIDIA/DeepSeek-V4-Pro — 1M context, 384K output, text-only.
---

# NVIDIA / DeepSeek-V4-Pro

DeepSeek V4-Pro routed through NVIDIA AI Endpoints. 1M context window, 384K max output. Stronger reasoning than V4-Flash.

**LiteLLM model:** `openai/deepseek-ai/deepseek-v4-pro`
**Context window:** 1,000,000 tokens
**Max output:** 384,000 tokens

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
- model_name: NVIDIA/DeepSeek-V4-Pro
  litellm_params:
    # Upstream org + model slug. Same path pattern as V4-Flash.
    model: openai/deepseek-ai/deepseek-v4-pro
    api_base: os.environ/NVIDIA_BASE_URL
    api_key: os.environ/NVIDIA_API_KEY
    timeout: 300
    drop_params: true
    extra_body:
      # Request usage metadata in the streaming response.
      stream_options:
        include_usage: true
  model_info:
    id: "nvidia-deepseek-v4-pro"
    db_model: false
    supports_reasoning: true
    mode: chat
    context_window: 1000000
    max_tokens: 1000000
    max_input_tokens: 616000
    max_output_tokens: 384000
    limit:
      context: 1000000
      output: 384000
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

- Use for: complex reasoning, architecture decisions, long-context analysis.
- Source: [build.nvidia.com/deepseek-ai/deepseek-v4-pro](https://build.nvidia.com/deepseek-ai/deepseek-v4-pro/modelcard)
- Same capabilities as the direct DeepSeek provider, but routed through NVIDIA's catalog.

See [NVIDIA provider](index.md) for the generic schema and enabling steps.
