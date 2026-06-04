---
description: Local provider — self-hosted inference servers on separate ports.
---

# Local

Route to inference servers running on your machine. Two pre-configured models on separate ports let you run a primary coding model and a fast fallback simultaneously.

**File:** `~/.codefreedom/proxy/config/providers/local.yaml`

## Environment Variables

| Variable | Description | Default |
| --- | --- | --- |
| `LOCAL_M_BASE_URL` | Primary model URL | `http://host.docker.internal:8000/v1` |
| `LOCAL_M_API_KEY` | Primary model API key | `sk-dummy` |
| `LOCAL_S_BASE_URL` | Secondary model URL | `http://host.docker.internal:8001/v1` |
| `LOCAL_S_API_KEY` | Secondary model API key | `sk-dummy` |

> **Docker mode:** URLs use `host.docker.internal` to reach host ports. This requires the `extra_hosts: host.docker.internal:host-gateway` setting in `docker-compose.yaml` (included by default).
>
> **Native mode:** Use `localhost` instead of `host.docker.internal`.

## Example Configuration

```yaml
model_list:
  - model_name: DGX/Qwen3.6-27B
    litellm_params:
      model: openai/qwen3.6_27b
      api_base: os.environ/LOCAL_M_BASE_URL
      api_key: os.environ/LOCAL_M_API_KEY
      timeout: 300
      include_reasoning: true
      max_tokens: 131072
      max_completion_tokens: 16384
      extra_body:
        seed: 42
        temperature: 0.0
        top_p: 1.0
        top_k: 1
        stream_options:
          include_usage: true
        chat_template_kwargs:
          enable_thinking: true
          preserve_thinking: false
    model_info:
      mode: chat
      context_window: 131072
      max_tokens: 131072
      supports_reasoning: true
      supports_vision: false
```

- **`include_reasoning: true`** — Tells LiteLLM to include reasoning tokens in the response.
- **`chat_template_kwargs.enable_thinking`** — Enables extended thinking mode for deeper reasoning.
- **`DGX/Qwen3.6-35B-A3B`** — The secondary model follows the same pattern on port 8001 with a larger 262K context window and vision support.

## Enabling

1. Uncomment the model entries in `local.yaml`.
2. Ensure `providers/local.yaml` is in the `include` list.
3. Set `LOCAL_M_BASE_URL` and `LOCAL_S_BASE_URL` to point at your inference servers.
4. For Docker mode, ensure `host.docker.internal` resolves (included in `docker-compose.yaml` by default).

## Cloud-Only Users

If you don't run local models, comment out `providers/local.yaml` in the `include` list and leave the `LOCAL_*` keys empty.
