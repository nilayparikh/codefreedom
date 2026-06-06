---
description: Local provider — self-hosted inference servers on separate ports.
---

# Local

Route to inference servers running on your machine. Two pre-configured models on separate ports let you run a primary coding model and a fast fallback simultaneously.

**Provider file:** `~/.codefreedom/proxy/config/providers/local.yaml`

## Environment Variables

| Variable           | Description             | Default                               |
| ------------------ | ----------------------- | ------------------------------------- |
| `LOCAL_M_BASE_URL` | Primary model URL       | `http://host.docker.internal:8000/v1` |
| `LOCAL_M_API_KEY`  | Primary model API key   | `sk-dummy`                            |
| `LOCAL_S_BASE_URL` | Secondary model URL     | `http://host.docker.internal:8001/v1` |
| `LOCAL_S_API_KEY`  | Secondary model API key | `sk-dummy`                            |

> **Docker mode:** URLs use `host.docker.internal` to reach host ports. This requires the `extra_hosts: host.docker.internal:host-gateway` setting in `docker-compose.yaml` (included by default).
>
> **Native mode:** Use `localhost` instead of `host.docker.internal`.

## Available Models

| Model                                 | Port               | Context | Max Output | Reasoning | Vision |
| ------------------------------------- | ------------------ | ------- | ---------- | --------- | ------ |
| [Qwen3.6-27B](qwen3.6-27b.md)         | 8000 (`LOCAL_M_*`) | 131,072 | 16,384     | Yes       | No     |
| [Qwen3.6-35B-A3B](qwen3.6-35b-a3b.md) | 8001 (`LOCAL_S_*`) | 262,144 | 16,384     | Yes       | No     |

## Generic Configuration

Both local models share the same `litellm_params` and `model_info` shape. Each model file inlines the full block (rather than referencing a shared anchor) so the configuration is self-contained and can be copy/pasted standalone.

```yaml
model_list:
  # ── CodeFreedom/Pro alias maps here ──────────────────────────────────────
  # Primary coding/reasoning model on port 8000
  - model_name: DGX/Qwen3.6-27B
    litellm_params:
      # Inline block — no anchor. Each model file shows the full
      # configuration; copy/paste one entry to register a new model.
      # Upstream model identifier as exposed by the local server.
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
        # Some local servers need this flag to handle newer
        # chat templates correctly. Remove if your server errors.
        forward_compatibility: true
        stream_options:
          include_usage: true
        # Qwen3.6-specific template flags:
        # - enable_thinking: surface CoT tokens to the client
        # - preserve_thinking: keep them across multi-turn context
        chat_template_kwargs:
          enabl
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

### Common Field Notes

- **`include_reasoning: true`** — LiteLLM flag to include reasoning tokens in the response. Required for any model that uses chain-of-thought.
- **`include_reasoning: true`** — LiteLLM flag to include reasoning tokens in the response. Required for any model that uses chain-of-thought.
- **`extra_body` sampling** — `seed: 42` and `temperature: 0.0` give deterministic outputs. `top_k: 1` and `top_p: 1.0` are the Qwen3.6-recommended greedy setting. Adjust for your model.
- **`max_thinking_tokens: 1536`** — Cap on CoT length. The model emits up to this many thinking tokens before the final answer. Lower for faster responses.
- **`chat_template_kwargs.enable_thinking: true`** — Required to surface chain-of-thought tokens to the client. `preserve_thinking: false` keeps the chat template from carrying them across turns.
- **`forward_compatibility: true`** — A flag some local servers need to handle newer chat templates. Remove if your server errors on this key.
- **`max_completion_tokens: 16384`** — Conservative output cap. Increase if the model needs to generate longer outputs.

## Enabling

1. Uncomment the model entries in `local.yaml` (commented by default in the example).
2. Ensure `providers/local.yaml` is in the `include` list in `config.yaml`.
3. Set `LOCAL_M_BASE_URL` and `LOCAL_S_BASE_URL` to point at your inference servers.
4. For Docker mode, ensure `host.docker.internal` resolves (included in `docker-compose.yaml` by default).

## Cloud-Only Users

If you don't run local models, comment out `providers/local.yaml` in the `include` list and leave the `LOCAL_*` keys empty.

## Per-Model Details

See each model's dedicated page for full `model_info` and any model-specific configuration:

- [Qwen3.6-27B](qwen3.6-27b.md) — primary, port 8000, 128K context
- [Qwen3.6-35B-A3B](qwen3.6-35b-a3b.md) — secondary, port 8001, 256K context
