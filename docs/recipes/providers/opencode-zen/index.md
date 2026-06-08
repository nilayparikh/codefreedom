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

## Models

| Model                  | Context   | Max Output | Vision | Reasoning |
| ---------------------- | --------- | ---------- | ------ | --------- |
| MiMo-V2.5-FREE         | 1,048,576 | 131,072    | Yes    | Yes       |
| Nemotron-3-Super-FREE  | 262,144   | 65,536     | No     | Yes       |
| Nemotron-3-Ultra-FREE  | 1,048,576 | 131,072    | Yes    | Yes       |
| DeepSeek-V4-Flash-FREE | 1,000,000 | 384,000    | No     | Yes       |
| Big-Pickle             | 262,144   | 65,536     | No     | Yes       |
| MiniMax-M3-FREE        | 512,000   | 128,000    | Yes    | Yes       |

## Configuration

All OpenCode Zen models share a common pattern. Example for MiMo-V2.5-FREE:

```yaml
model_list:
  - model_name: OpenCodeZen/MiMo-V2.5-FREE
    litellm_params:
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
      max_output_tokens: 131072
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

See the [source YAML](https://github.com/nilayparikh/codefreedom/tree/main/src/codefreedom/examples/proxy/config/providers/opencode-zen.yaml) for all model entries. Free-tier models use the `-free` suffix in the upstream model path.

## Enabling

1. Uncomment model entries in `opencode-zen.yaml`.
2. Ensure `providers/opencode-zen.yaml` is in the `include` list in `config.yaml`.
3. Optionally set `OPENCODE_ZEN_API_KEY` (can be a placeholder like `sk-free`).
4. Restart the proxy.
