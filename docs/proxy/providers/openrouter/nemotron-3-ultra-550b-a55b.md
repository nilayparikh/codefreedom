---
description: OpenRouter/Nemotron-3-Ultra-550B-A55B — specific free-tier model via OpenRouter.
---

# OpenRouter / Nemotron-3-Ultra-550B-A55B

NVIDIA Nemotron-3-Ultra routed through OpenRouter's free tier. Pin this when you want a specific model, not dynamic selection.

**LiteLLM model:** `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free`
**Upstream:** NVIDIA Nemotron-3-Ultra (550B / A55B MoE)

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
- model_name: OpenRouter/Nemotron-3-Ultra-550B-A55B
  litellm_params:
    # Pinned free-tier model. OpenRouter will route this exact
    # request to NVIDIA's Nemotron-3-Ultra endpoint.
    model: openrouter/nvidia/nemotron-3-ultra-550b-a55b:free
    api_base: os.environ/OPENROUTER_BASE_URL
    api_key: os.environ/OPENROUTER_API_KEY
    timeout: 300
    drop_params: true
    extra_body:
      # Request usage metadata in the streaming response.
      stream_options:
        include_usage: true
  model_info:
    id: "openrouter-nemotron-3-ultra-550b-a55b"
    mode: chat
    supports_system_messages: true
    supports_native_streaming: true
    supports_vision: true
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
      - reasoning_effort
```

## Notes

- Use for: when you specifically need Nemotron-3-Ultra, vision + reasoning, free tier.
- **Pinned vs FreeRouter** — This entry pins the model. Use [FreeRouter](freerouter.md) when you want OpenRouter to choose the best available free model at request time.
- **`:free` suffix** — Requests the free-tier route. The same model is also available on paid routes through OpenRouter.
- **MoE architecture** — 550B total parameters with 55B active per token. Latency is closer to a 55B model than a 550B one.

See [OpenRouter provider](index.md) for the generic schema and enabling steps.
