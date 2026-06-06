---
description: config.yaml structure — model aliases, retry policy, and fallbacks.
---

# Proxy Configuration

The core config lives at `~/.codefreedom/proxy/config/config.yaml`. It has three sections: `general_settings`, `router_settings`, and `litellm_settings`.

## Include List

The `include` block loads provider YAML files. Comment out a line to disable that provider:

```yaml
include:
  - providers/deepseek.yaml
  - providers/azure-foundry.yaml
  # - providers/nvidia.yaml       # disabled
  - providers/local.yaml
```

Each included file defines a `model_list` with one or more model entries. Files are merged — order doesn't matter.

## General Settings

```yaml
general_settings:
  store_model_in_db: false
  store_prompts_in_spend_logs: false
  forward_client_headers_to_llm_api: true
```

| Setting | Default | Description |
| --- | --- | --- |
| `store_model_in_db` | `false` | Write model metadata to PostgreSQL. Requires `database_url`. |
| `store_prompts_in_spend_logs` | `false` | Log prompts for spend analysis. Requires `database_url`. |
| `forward_client_headers_to_llm_api` | `true` | Forward client headers (e.g., `User-Agent`) to upstream providers. |

To enable database features, see [Database](database.md).

## Router Settings

### Model Aliases

Model aliases map friendly `CodeFreedom/` names to specific provider models. Claude Code profiles reference these names — change the alias to switch providers without touching your agent config.

```yaml
router_settings:
  model_group_alias:
    "CodeFreedom/Ultra": os.environ/LITELLM_MODEL_ALIAS_ULTRA
    "CodeFreedom/Pro": os.environ/LITELLM_MODEL_ALIAS_PRO
    "CodeFreedom/Flash": os.environ/LITELLM_MODEL_ALIAS_FLASH
    "CodeFreedom/Air": os.environ/LITELLM_MODEL_ALIAS_AIR
```

Set the targets in `.env.proxy`:

```bash
LITELLM_MODEL_ALIAS_ULTRA="DeepSeek/DeepSeek-V4-Pro"
LITELLM_MODEL_ALIAS_PRO="DGX/Qwen3.6-27B"
LITELLM_MODEL_ALIAS_FLASH="DeepSeek/DeepSeek-V4-Flash"
LITELLM_MODEL_ALIAS_AIR="DGX/Qwen3.6-35B-A3B"
```

Each alias points to a `model_name` defined in your provider YAMLs. Change `ULTRA` to `NVIDIA/Kimi-K2.6` to route through NVIDIA instead — no other config changes needed.

### Retry Policy

```yaml
router_settings:
  num_retries: os.environ/LITELLM_NUM_RETRIES      # default: 5
  retry_after: os.environ/LITELLM_RETRY_AFTER       # default: 0
  allowed_fails: 3

  retry_policy:
    AuthenticationErrorRetries: 0
    TimeoutErrorRetries: os.environ/LITELLM_TIMEOUT_ERROR_RETRIES
    RateLimitErrorRetries: os.environ/LITELLM_RATE_LIMIT_ERROR_RETRIES
    ContentPolicyViolationErrorRetries: 0
    InternalServerErrorRetries: os.environ/LITELLM_INTERNAL_ERROR_RETRIES
```

- `num_retries` — total retries per request across all models in a group.
- `allowed_fails` — cooldown a model after N failures per minute.
- `retry_policy` — per-error-type retry counts. Authentication and content violations never retry.

### Context Window Fallbacks

When a request is too large for the current model, fall back to one with a bigger context:

```yaml
context_window_fallbacks:
  - "DGX/Qwen3.6-27B": [os.environ/LITELLM_MODEL_ALIAS_ULTRA]
  - "DGX/Qwen3.6-35B-a3b": [os.environ/LITELLM_MODEL_ALIAS_FLASH]
```

If `DGX/Qwen3.6-27B` can't fit the context, the proxy automatically retries with the model pointed to by `LITELLM_MODEL_ALIAS_ULTRA`.

## LiteLLM Settings

```yaml
litellm_settings:
  always_include_stream_usage: os.environ/LITELLM_STREAM_USAGE
  drop_params: os.environ/LITELLM_DROP_PARAMS
  redact_user_api_key_info: os.environ/LITELLM_REDACT_USER_API_KEY
  turn_off_message_logging: os.environ/LITELLM_TURN_OFF_MSG_LOGGING
  json_logs: os.environ/LITELLM_JSON_LOGS

  use_chat_completions_url_for_anthropic_messages: true
  callbacks:
    - prometheus
  require_auth_for_metrics_endpoint: os.environ/LITELLM_REQUIRE_AUTH_METRICS
```

| Setting | Default | Description |
| --- | --- | --- |
| `drop_params` | `true` | Strip params the upstream provider doesn't support. Prevents 400 errors. |
| `redact_user_api_key_info` | `true` | Redact API keys from logs. |
| `use_chat_completions_url_for_anthropic_messages` | `true` | Translate Anthropic `/v1/messages` to OpenAI format for non-Anthropic backends. |
| `callbacks: prometheus` | on | Expose metrics at `/metrics/`. |

For the full parameter reference, see [LiteLLM Proxy Parameters](https://docs.litellm.ai/docs/config/parameters).

## Web Search Interception

The proxy can transparently replace Claude Code's built-in `WebSearch` with calls to a local search backend. This is implemented via LiteLLM's `websearch_interception` callback. See [Web Search Interception](websearch-interception.md) for the full pipeline.

To enable, uncomment two blocks in `config.yaml`:

```yaml
litellm_settings:
  callbacks:
    - prometheus
    - websearch_interception

  websearch_interception_params:
    enabled_providers: ["openai", "anthropic", "vertex_ai", "bedrock", "azure"]
    search_tool_name: codefreedom-web

search_tools:
  - search_tool_name: codefreedom-web
    litellm_params:
      search_provider: searxng
      api_base: http://web-bridge:8500
```

The default `api_base` points at the bundled `web-bridge` service in `docker-compose.yaml`, which translates SearXNG-shaped requests into JSON-RPC calls against the Camoufox MCP `web_search` tool.
