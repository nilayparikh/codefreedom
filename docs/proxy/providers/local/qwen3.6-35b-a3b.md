---
description: DGX/Qwen3.6-35B-A3B — secondary local model on port 8001, larger context.
---

# DGX / Qwen3.6-35B-A3B

Secondary local model. Wired to `LOCAL_S_*` env vars (port 8001). 256K context window — larger than the primary 27B. This is the model that maps to `CodeFreedom/Air` by default.

**LiteLLM model:** `openai/qwen3.6_35b_a3b`
**Context window:** 262,144 tokens
**Max output:** 16,384 tokens

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
# ── CodeFreedom/Air alias maps here ──────────────────────────────────────
# Fast, large-context model on port 8001
- model_name: DGX/Qwen3.6-35B-A3B
  litellm_params:
    # Full block — every field shown inline. Copy/paste this entry
    # into your local.yaml without needing any anchor.
    model: openai/qwen3.6_35b_a3b
    api_base: os.environ/LOCAL_S_BASE_URL
    api_key: os.environ/LOCAL_S_API_KEY
    timeout: 300
    # Tell LiteLLM to include reasoning tokens in the response.
    include_reasoning: true
    max_tokens: 262144
    max_completion_tokens: 16384
    extra_body:
      # Sampling parameters pinned for reproducibility.
      seed: 42
      temperature: 0.0
      top_p: 1.0
      top_k: 1
      presence_penalty: 0.0
      repetition_penalty: 1.0
      # Cap on chain-of-thought length. Tune for the model.
      max_thinking_tokens: 1536
      # Some local servers need this flag to handle newer chat
      # templates correctly. Remove if your server errors on it.
      forward_compatibility: true
      stream_options:
        include_usage: true
      # Qwen3.6-specific template flags.
      chat_template_kwargs:
        enable_thinking: true
        preserve_thinking: false
  model_info:
    id: "local-qwen3.6-35b-a3b"
    db_model: false
    supports_reasoning: true
    mode: chat
    context_window: 262144
    max_tokens: 262144
    max_input_tokens: 229376
    max_output_tokens: 16384
    limit:
      context: 262144
      output: 16384
    supports_system_messages: true
    supports_native_streaming: true
    supports_vision: false
    # Full list of OpenAI parameters this model accepts. Inlined
    # (rather than referencing a shared anchor) so the block is
    # self-contained and can be copy/pasted standalone.
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

- Use for: long-context tasks, large codebase analysis, fast scanning.
- **`LOCAL_S_BASE_URL` and `LOCAL_S_API_KEY`** — set these in `.env.proxy` to point at the inference server on port 8001.
- **`max_tokens: 262144`** — Larger context window than the 27B primary. Suitable for codebases that don't fit in 128K.
- **`max_completion_tokens: 16384`** — Same as 27B. Output cap is independent of context window.

See [Local provider](index.md) for the generic schema and enabling steps.
