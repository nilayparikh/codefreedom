---
description: OpenCode Zen — free-tier models (Mimo, Nemotron, DeepSeek).
---

# OpenCode Zen

[OpenCode Zen](https://opencode.ai/zen) offers free-tier model access through an OpenAI-compatible API. No API key required for free models (use a placeholder).

**File:** `~/.codefreedom/proxy/config/providers/opencode-zen.yaml`

## Environment Variables

| Variable | Description | Default |
| --- | --- | --- |
| `OPENCODE_ZEN_API_KEY` | API key (placeholder for free tier) | (optional) |
| `OPENCODE_ZEN_BASE_URL` | API base URL | `https://opencode.ai/zen/v1` |

## Example Configuration

```yaml
model_list:
  - model_name: OpenCodeZen/Mimo-V2.5-FREE
    litellm_params:
      model: openai/mimo-v2.5-free
      api_base: os.environ/OPENCODE_ZEN_BASE_URL
      api_key: os.environ/OPENCODE_ZEN_API_KEY
      timeout: 300
      max_tokens: 200000
      drop_params: true
      stream_options:
        include_usage: true
      extra_body:
        temperature: 0.0
        top_p: 1.0
        reasoning_effort: "high"
    model_info:
      mode: chat
      context_window: 200000
      max_tokens: 200000
      supports_reasoning: true
      supports_vision: false
```

- **YAML anchors** — The template uses `&opencode_zen_openai_params` / `*opencode_zen_openai_params` to share common settings across models. Each additional model only overrides `model`, `max_tokens`, and `id`.
- **Free models** — Nemotron-3-Super, DeepSeek-V4-Flash, and Big-Pickle follow the same pattern.

## Enabling

1. Uncomment the model entries in `opencode-zen.yaml`.
2. Ensure `providers/opencode-zen.yaml` is in the `include` list.
3. Set `OPENCODE_ZEN_API_KEY` (can be a placeholder for free tier).
