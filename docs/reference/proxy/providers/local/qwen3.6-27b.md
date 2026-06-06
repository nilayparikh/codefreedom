---
description: DGX/Qwen3.6-27B — primary local coding model on port 8000.
---

# DGX / Qwen3.6-27B

Primary local coding model. Wired to `LOCAL_M_*` env vars (port 8000). This is the model that maps to `CodeFreedom/Pro` by default.

**LiteLLM model:** `openai/qwen3.6_27b`
**Context window:** 131,072 tokens
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
# ── CodeFreedom/Pro alias maps here ──────────────────────────────────────
# Primary coding/reasoning model on port 8000
- model_name: DGX/Qwen3.6-27B
  litellm_params:
    # Inline block — no anchor. Each model file shows the full
    # configuration; copy/paste this entry to register a new model.
    model: openai/qwen3.6_27b
    api_base: os.environ/LOCAL_M_BASE_URL
    api_key: os.environ/LOCAL_M_API_KEY
    timeout: 300
    # Tell LiteLLM to include reasoning tokens in the response.
    include_reasoning: true
    max_tokens: 131072
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
    id: "local-qwen3.6-27b"
    db_model: false
    supports_reasoning: true
    mode: chat
    context_window: 131072
    max_tokens: 131072
    max_input_tokens: 114688
    max_output_tokens: 16384
    limit:
      context: 131072
      output: 16384
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
      - thinking
      - reasoning_effort
```

## Notes

- Use for: primary coding, refactors, multi-file generation, debugging.
- **`LOCAL_M_BASE_URL` and `LOCAL_M_API_KEY`** — set these in `.env.proxy` to point at the inference server on port 8000.
- **`include_reasoning: true`** — Required for the `CodeFreedom/Pro` alias to expose reasoning tokens to Claude Code.
- **`chat_template_kwargs`** — Qwen3.6-specific. If you swap to a different model, these may need to change.
- **`max_completion_tokens: 16384`** — Conservative output cap. Increase if the model needs longer generations.

See [Local provider](index.md) for the generic schema and enabling steps.
