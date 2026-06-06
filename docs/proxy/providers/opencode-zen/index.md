---
description: OpenCode Zen provider — free-tier models (Mimo, Nemotron, DeepSeek, Big-Pickle, MiniMax-M3).
---

# OpenCode Zen

[OpenCode Zen](https://opencode.ai/zen) offers free-tier model access through an OpenAI-compatible API. The free tier is generous; a placeholder API key works for most models.

**Provider file:** `~/.codefreedom/proxy/config/providers/opencode-zen.yaml`

## Environment Variables

| Variable                | Description                               | Required                                   |
| ----------------------- | ----------------------------------------- | ------------------------------------------ |
| `OPENCODE_ZEN_BASE_URL` | API base URL                              | No (default: `https://opencode.ai/zen/v1`) |
| `OPENCODE_ZEN_API_KEY`  | API key (placeholder works for free tier) | No                                         |

## Available Models

| Model                                          | Context   | Max Output | Vision | Reasoning |
| ---------------------------------------------- | --------- | ---------- | ------ | --------- |
| [MiMo-V2.5-FREE](mimo-v2.5.md)                 | 1,048,576 | 131,072    | Yes    | Yes       |
| [Nemotron-3-Super-FREE](nemotron-3-super.md)   | 262,144   | 65,536     | No     | Yes       |
| [Nemotron-3-Ultra-FREE](nemotron-3-ultra.md)   | 1,048,576 | 131,072    | Yes    | Yes       |
| [DeepSeek-V4-Flash-FREE](deepseek-v4-flash.md) | 1,000,000 | 384,000    | No     | Yes       |
| [Big-Pickle](big-pickle.md)                    | 262,144   | 65,536     | No     | Yes       |
| [MiniMax-M3-FREE](minimax-m3.md)               | 512,000   | 128,000    | Yes    | Yes       |

## Generic Configuration

All OpenCode Zen models share a common base configuration. Each model file inlines the full block (rather than referencing a shared anchor) so the configuration is self-contained and can be copy/pasted standalone.

```yaml
model_list:
  - model_name: OpenCodeZen/MiMo-V2.5-FREE
    litellm_params:
      # Inline block — no anchor. Each model file shows the full
      # configuration; copy/paste one entry to register a new model.
      model: openai/mimo-v2.5-free
      api_base: os.environ/OPENCODE_ZEN_BASE_URL
      api_key: os.environ/OPENCODE_ZEN_API_KEY
      timeout: 300
      drop_params: true
      stream_options:
        include_usage: true
      extra_body:
        temperature: 0.0
        top_p: 1.0
        reasoning_effort: "high"
    model_info:
      id: "opencode-mimo-v2.5-free"
      db_model: false
      supports_reasoning: true
      mode: chat
      supports_system_messages: true
      supports_native_streaming: true
      supports_vision: true
      context_window: 1048576
      max_tokens: 1048576
      max_input_tokens: 917504
      max_output_tokens: 131072
      limit:
        context: 1048576
        output: 131072
      # Full list of OpenAI parameters this model accepts. Inlined
      # (rather than referencing a shared anchor) so the block is
      # self-contained and can be copy/pasted standalone.
      supported_openai_params:
        - tools
        - tool_choice
        - parallel_tool_calls
        - max_tokens
        - max_completion_tokens
        - stream
        - stream_options
        - temperature
        - top_p
        - stop
        - thinking
        - reasoning_effort
        - response_format
```

### Common Field Notes

- **`extra_body.reasoning_effort: "high"`** — Drives chain-of-thought depth. LiteLLM passes this to the upstream OpenAI-compatible endpoint.
- **`stream_options.include_usage: true`** — Required for token accounting in streaming responses.
- **Free tier** — All models use the `-free` suffix in the upstream model path. The `OPENCODE_ZEN_API_KEY` is typically a placeholder.

## Enabling

1. Uncomment the model entries in `opencode-zen.yaml` (commented by default in the example).
2. Ensure `providers/opencode-zen.yaml` is in the `include` list in `config.yaml`.
3. Optionally set `OPENCODE_ZEN_API_KEY` (can be a placeholder like `sk-free`).

## Per-Model Details

See each model's dedicated page for full `model_info`, context window, and supported parameters:

- [MiMo-V2.5-FREE](mimo-v2.5.md) — Xiaomi, 1M context, vision + reasoning
- [Nemotron-3-Super-FREE](nemotron-3-super.md) — NVIDIA, 262K, text-only
- [Nemotron-3-Ultra-FREE](nemotron-3-ultra.md) — NVIDIA, 1M, vision
- [DeepSeek-V4-Flash-FREE](deepseek-v4-flash.md) — 1M context, 384K output
- [Big-Pickle](big-pickle.md) — general purpose, 262K
- [MiniMax-M3-FREE](minimax-m3.md) — 512K, vision + reasoning
