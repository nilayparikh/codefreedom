# Understanding LiteLLM Proxy Configuration

> Read this alongside the provider YAML files in `providers/` and the main `config.yaml`. Each section links to official LiteLLM docs for deeper reference.

---

## What is LiteLLM Proxy?

[LiteLLM](https://github.com/BerriAI/litellm) is a lightweight Python library that provides a unified interface to 100+ LLM providers. When run in **proxy mode**, it starts a local API server (like a mini OpenAI API) that:

- **Routes** your requests to the right provider (DeepSeek, NVIDIA, Azure, local, etc.)
- **Translates** between API formats (Anthropic `/v1/messages` ↔ OpenAI `/v1/chat/completions`)
- **Manages failover and retries** when a provider is down or rate-limited
- **Handles context window fallbacks** when your prompt is too large
- **Maps model aliases** so your agent always uses the same short name

**Official docs:** [LiteLLM Proxy Overview](https://docs.litellm.ai/docs/proxy/configs)

---

## The Configuration File Structure

CodeFreedom uses a **layered** config system:

```
~/.codefreedom/proxy/config/
├── config.yaml                    # Top-level: general/ router/ litellm settings
├── providers/
│   ├── deepseek.yaml              # One file per provider
│   ├── azure-foundry.yaml
│   ├── nvidia.yaml
│   ├── opencode-zen.yaml
│   ├── openrouter.yaml
│   ├── local.yaml
│   ├── openai-compatible.yaml     # Template for any OpenAI API
│   └── anthropic-compatible.yaml  # Template for any Anthropic API
└── plugins/
    └── reasoning-efforts/
        └── reasoning-efforts-mapping.yaml  # Effort-level translation rules
```

The main `config.yaml` uses `include` to pull in provider files. Each provider file defines a `model_list`. The proxy merges them into one virtual model catalog.

---

## Config Sections (`config.yaml`)

The top-level config has three main sections:

### 1. `general_settings`

Server-level settings for the proxy itself.

| Field | Default | Purpose | Official Docs |
|-------|---------|---------|---------------|
| `store_model_in_db` | `false` | Write model metadata to PostgreSQL. Leave `false` for stateless mode. | [LiteLLM DB Docs](https://docs.litellm.ai/docs/proxy/database) |
| `store_prompts_in_spend_logs` | `false` | Log prompts for spend analysis. Requires database. | |
| `forward_client_headers_to_llm_api` | `true` | Forward headers like `User-Agent` to upstream providers. Helps with debugging. | |

### 2. `router_settings`

Controls how the proxy routes, retries, and falls back between models.

| Field | CodeFreedom Default | Purpose |
|-------|-------------------|---------|
| `num_retries` | `5` | Total retries per request across all models in a group |
| `retry_after` | `0` | Minimum delay (seconds) between retries |
| `allowed_fails` | `3` | Cool down a model after N failures per minute |
| `model_group_alias` | — | Maps friendly names to model groups (aliases) |
| `context_window_fallbacks` | — | If context is too large for one model, try another |
| `retry_policy` | — | Per-error-type retry counts |

**Official docs:** [Router Settings](https://docs.litellm.ai/docs/proxy/config_settings), [Load Balancing](https://docs.litellm.ai/docs/proxy/load_balancing), [Fallbacks](https://docs.litellm.ai/docs/proxy/reliability)

#### `model_group_alias` — The Key to Provider Agnosticism

This is the feature that makes CodeFreedom's **agent-agnostic** architecture work. Aliases allow you to switch providers without reconfiguring your code agent:

```yaml
model_group_alias:
  "CodeFreedom/Ultra": os.environ/LITELLM_MODEL_ALIAS_ULTRA
  "CodeFreedom/Pro":   os.environ/LITELLM_MODEL_ALIAS_PRO
  "CodeFreedom/Flash": os.environ/LITELLM_MODEL_ALIAS_FLASH
  "CodeFreedom/Air":   os.environ/LITELLM_MODEL_ALIAS_AIR
```

Your Claude Code profile always requests `CodeFreedom/Pro`. The env var `LITELLM_MODEL_ALIAS_PRO="DeepSeek/DeepSeek-V4-Pro"` routes it to DeepSeek. Change the env var to `"NVIDIA/DeepSeek-V4-Pro"` to route through NVIDIA — no profile changes needed.

Short aliases (`opus`, `sonnet`, `haiku`) let MCP hosts and VS Code extensions that hardcode Anthropic model IDs route through the proxy:

```yaml
"opus": os.environ/LITELLM_MODEL_ALIAS_ULTRA
"sonnet": os.environ/LITELLM_MODEL_ALIAS_PRO
"haiku": os.environ/LITELLM_MODEL_ALIAS_AIR
```

**Official docs:** [Model Group Aliases](https://docs.litellm.ai/docs/proxy/config_settings#router-settings)

#### `retry_policy` — Which Errors to Retry

```yaml
retry_policy:
  AuthenticationErrorRetries: 0            # Never retry bad credentials
  TimeoutErrorRetries: os.environ/LITELLM_TIMEOUT_ERROR_RETRIES
  RateLimitErrorRetries: os.environ/LITELLM_RATE_LIMIT_ERROR_RETRIES
  ContentPolicyViolationErrorRetries: 0    # Never retry content violations
  InternalServerErrorRetries: os.environ/LITELLM_INTERNAL_ERROR_RETRIES
```

Authentication errors and content policy violations never retry (they won't succeed on retry). Timeouts, rate limits, and server errors do retry — controlled by env vars so you can tune without editing the config file.

### 3. `litellm_settings`

Module-level settings that affect how LiteLLM processes requests.

| Field | Default | Purpose |
|-------|---------|---------|
| `always_include_stream_usage` | `true` | Always include token usage in streaming chunks |
| `drop_params` | `true` | Strip parameters the upstream provider doesn't support — prevents 400 errors |
| `modify_params` | `true` | Allow LiteLLM to modify params for provider compatibility (e.g., rename `max_tokens` to `max_completion_tokens`) |
| `use_chat_completions_url_for_anthropic_messages` | `true` | Translate Anthropic `/v1/messages` to OpenAI `/v1/chat/completions` for non-Anthropic backends |
| `callbacks` | `["prometheus"]` | Plugin callbacks for metrics, web search interception, reasoning mapping |
| `json_logs` | `false` | Output logs in JSON format for log aggregators |

**Official docs:** [LiteLLM Settings](https://docs.litellm.ai/docs/proxy/config_settings#litellm-settings)

---

## The `model_list` Entry — Anatomy of a Provider YAML

Every provider file defines a `model_list`. Each entry has three key sections.

### Complete Field Reference

Here's DeepSeek V4-Flash from `providers/deepseek.yaml`, annotated:

```yaml
model_list:
  - model_name: DeepSeek/DeepSeek-V4-Flash    # (1) External name
    litellm_params:                             # (2) API connection params
      model: deepseek/deepseek-v4-flash        # (2a)
      api_base: os.environ/DEEPSEEK_BASE_URL   # (2b)
      api_key: os.environ/DEEPSEEK_API_KEY     # (2c)
      timeout: 300                              # (2d)
      drop_params: true                         # (2e)
      modify_params: true                       # (2f)
      max_tokens: 1000000                       # (2g)
      max_completion_tokens: 384000             # (2h)
      extra_body:                               # (2i)
        stream_options:
          include_usage: true
    model_info:                                 # (3) Metadata + capabilities
      id: "deepseek-openai-deepseek-v4-flash"   # (3a)
      db_model: false                           # (3b)
      mode: chat                                # (3c)
      supports_reasoning: true                  # (3d)
      context_window: 1000000                   # (3e)
      max_tokens: 1000000                       # (3f)
      max_input_tokens: 616000                  # (3g)
      max_output_tokens: 384000                 # (3h)
      limit:                                    # (3i)
        context: 1000000
        output: 384000
      supports_system_messages: true            # (3j)
      supports_native_streaming: true           # (3k)
      supports_vision: false                    # (3l)
      input_cost_per_token: 0.00000014          # (3m)
      output_cost_per_token: 0.00000028         # (3n)
      cached_input_cost_per_token: 0.0000000028 # (3o)
      supported_openai_params:                  # (3p)
        - tools
        - tool_choice
        - max_tokens
        - stream
        - temperature
        - top_p
        - stop
        - thinking
        - reasoning_effort
    codefreedom:                                # (4) CodeFreedom extension
      plugins:
        reasoning-efforts:
          rule: deepseek-v4-flash
```

Let's go through each field:

### (1) `model_name`

**What it is:** The name that clients (Claude Code, VS Code, curl) and model aliases (`CodeFreedom/Pro`) use to reference this model.

**Convention:** `Provider/ModelName` — e.g., `DeepSeek/DeepSeek-V4-Flash`, `Azure/GPT-5.4`, `DGX/Qwen3.6-27B`. This namespace keeps names unique when multiple providers offer similar models.

**How aliases connect to it:**
```
CodeFreedom/Pro  →  LITELLM_MODEL_ALIAS_PRO="DeepSeek/DeepSeek-V4-Pro"
                   → model_name: "DeepSeek/DeepSeek-V4-Pro"
```

---

### (2) `litellm_params` — API Connection

These are the parameters LiteLLM uses to call the upstream API. They map directly to the arguments of `litellm.completion()`.

#### (2a) `model`

The LiteLLM provider-qualified model name. Format: `{provider}/{model_name}`

| Prefix | Provider | Example |
|--------|----------|---------|
| `deepseek/` | DeepSeek native API | `deepseek/deepseek-v4-flash` |
| `openai/` | OpenAI / OpenAI-compatible | `openai/gpt-5.4`, `openai/qwen3.6_27b` |
| `openrouter/` | OpenRouter | `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free` |
| `anthropic/` | Anthropic / Anthropic-compatible | `anthropic/claude-sonnet-4-20250514` |

**Full provider list:** [LiteLLM Supported Providers](https://docs.litellm.ai/docs/providers)

#### (2b) `api_base`

The URL of the API endpoint. Always loaded from an environment variable via `os.environ/VAR_NAME`.

**Why env vars?** Keep credentials out of config files. `os.environ/VAR_NAME` lets LiteLLM read from environment variables at runtime.

#### (2c) `api_key`

The API key, also via `os.environ/VAR_NAME`. If the env var is empty or unset, LiteLLM **skips** this model — nothing phones home.

#### (2d) `timeout`

Request timeout in seconds. CodeFreedom uses `300` (5 minutes) — suitable for long reasoning responses.

#### (2e) `drop_params`

**Default:** `false` in LiteLLM, `true` in CodeFreedom configs.

When `true`, LiteLLM strips parameters the upstream provider doesn't support before sending. Without this, sending `reasoning_effort` to a non-reasoning model causes a 400 error.

**Set at two levels:**
- **Globally** in `litellm_settings.drop_params` — applies to all models
- **Per-model** in `litellm_params.drop_params` — overrides global

**Official docs:** [LiteLLM drop_params](https://docs.litellm.ai/docs/completion/input#drop_params)

#### (2f) `modify_params`

When `true`, LiteLLM can rename or restructure parameters to match what the upstream provider expects. For example, converting `max_tokens` to `max_completion_tokens` for OpenAI-compatible endpoints. Used by DeepSeek models where the API expects slightly different param names.

#### (2g) `max_tokens` (in litellm_params vs model_info)

**In `litellm_params`:** A hard limit on the total tokens (input + output) that LiteLLM will send to this model. Requests exceeding this get rejected before reaching the API.

**In `model_info`:**
- `context_window` — The total context window the model supports (input + output)
- `max_input_tokens` — Maximum tokens the model accepts as input
- `max_output_tokens` — Maximum tokens the model can generate

Why both? `litellm_params.max_tokens` is a **proxy-level guard** — you can set it lower than the model's actual cap to reserve headroom. `model_info` values describe the **model's actual capabilities** for routing decisions.

#### (2h) `max_completion_tokens`

Maximum output tokens the model should generate. This is the OpenAI-style name for what Anthropic calls `max_tokens`. Some providers use one, some the other; `modify_params` handles the translation.

#### (2i) `extra_body`

Additional JSON body fields passed directly to the upstream API. Common uses:

- `stream_options.include_usage: true` — Request token usage in streaming responses
- `temperature`, `top_p`, `top_k` — Sampling parameters (set here when they're provider-specific rather than via OpenAI-compatible params)
- `max_thinking_tokens` — Budget for chain-of-thought in reasoning models
- `chat_template_kwargs` — Template arguments for local inference (llama.cpp, vLLM)
- `seed` — Deterministic output for testing
- `reasoning_effort` — Effort level for reasoning

**Official docs:** [LiteLLM Extra Body](https://docs.litellm.ai/docs/completion/input#provider_specific_params)

---

### (3) `model_info` — Capabilities and Costs

This section tells LiteLLM what the model can do, what it costs, and what parameters it accepts. Used for routing decisions, cost tracking, and parameter validation.

#### (3a) `id`

A unique identifier for this model deployment. Used internally by LiteLLM for deduplication and tracking. Should be unique across all models.

#### (3b) `db_model`

Set to `false` when not using a database. LiteLLM skips DB storage for this model.

#### (3c) `mode`

The type of model:

| Value | Meaning |
|-------|---------|
| `chat` | Chat completion model (the common case) |
| `completion` | Text completion model |
| `embedding` | Embedding model |
| `image_generation` | Image generation model |

#### (3d-3l) Capability Flags

Boolean fields that tell LiteLLM what this model supports:

| Field | Purpose | Affects |
|-------|---------|---------|
| `supports_reasoning` | Model supports chain-of-thought / reasoning | Whether to send `reasoning_effort` or `thinking` params |
| `supports_system_messages` | Model accepts system prompts | Whether to pass system messages or inject them |
| `supports_native_streaming` | Provider-native streaming support | Whether to use provider-native SSE or LiteLLM fallback |
| `supports_vision` | Model accepts image inputs | Whether to route vision requests |

#### (3e-3i) Token Limits

| Field | What it means |
|-------|---------------|
| `context_window` | Maximum total tokens (input + output) the model supports |
| `max_tokens` | Often same as `context_window` (deprecated in favor of separate input/output) |
| `max_input_tokens` | Maximum input tokens the model accepts. Used by LiteLLM for context window fallback decisions. |
| `max_output_tokens` | Maximum output tokens the model can generate |
| `limit.context` | Routing limit — used by load balancer |
| `limit.output` | Routing limit for output |

**Key insight:** `max_input_tokens` should be `context_window - max_output_tokens` plus a safety margin. For example, a model with 1M context and 384K max output typically accepts ~616K input (`1M - 384K`).

**Official docs:** [Context Window Fallbacks](https://docs.litellm.ai/docs/proxy/reliability#context-window-fallbacks)

#### (3m-3o) Cost Fields

Per-token costs for spend tracking. These are purely informational — no billing happens through the proxy.

| Field | What it means |
|-------|---------------|
| `input_cost_per_token` | Cost per input token ($) |
| `cached_input_cost_per_token` | Cost per cached input token ($) — cheaper for cache-hit prompts |
| `output_cost_per_token` | Cost per output token ($) |

**Official docs:** [Custom Model Pricing](https://docs.litellm.ai/docs/proxy/custom_pricing)

#### (3p) `supported_openai_params`

The list of OpenAI-compatible parameters this model accepts. LiteLLM uses this to validate and filter parameters before sending. When `drop_params: true`, any param NOT in this list gets stripped.

Common params and their meanings:

| Parameter | Purpose | Used By |
|-----------|---------|---------|
| `tools` | Function/tool calling | All providers |
| `tool_choice` | Force a specific tool | All providers |
| `parallel_tool_calls` | Call multiple tools at once | OpenAI, DeepSeek |
| `response_format` | JSON mode / structured output | OpenAI-compatible |
| `max_tokens` | Max total tokens | All providers |
| `max_completion_tokens` | Max output tokens | OpenAI-compatible |
| `stream` | Enable streaming | All providers |
| `stream_options` | Stream configuration | All providers |
| `temperature` | Sampling temperature | All providers |
| `top_p` | Nucleus sampling | All providers |
| `stop` | Stop sequences | All providers |
| `presence_penalty` | Penalize repeated topics | OpenAI-compatible |
| `frequency_penalty` | Penalize repeated tokens | OpenAI-compatible |
| `logit_bias` | Bias token probabilities | OpenAI |
| `logprobs` | Return token logprobs | OpenAI |
| `thinking` | Anthropic extended thinking | Anthropic, DeepSeek |
| `reasoning_effort` | Reasoning effort level | OpenAI, DeepSeek, local |

**Official docs:** [LiteLLM Input Params](https://docs.litellm.ai/docs/completion/input)

---

### (4) `codefreedom` — CodeFreedom Plugin Configuration

This section is **not** a standard LiteLLM field. It's a CodeFreedom extension that plugins read at runtime.

#### `codefreedom.plugins.reasoning-efforts.rule`

References a named rule from `plugins/reasoning-efforts/reasoning-efforts-mapping.yaml`. The rule tells the reasoning-efforts plugin how to translate effort levels (`low`, `medium`, `high`, etc.) into values the downstream model accepts.

```yaml
codefreedom:
  plugins:
    reasoning-efforts:
      rule: deepseek-v4-flash
```

Each rule defines the specific mapping for a model, accounting for its caps (e.g., DeepSeek V4-Flash caps at `high`, can't do `xhigh` or `max`).

**Dedicated docs:** [Reasoning-Efforts Mapping](../reasoning-efforts.md) (at `docs/reference/proxy/reasoning-efforts.md`)

---

## How It All Fits Together: Request Flow

Here's what happens when Claude Code sends a request:

```
Claude Code
  │  POST /v1/messages  {"model": "CodeFreedom/Pro", ...}
  ▼
LiteLLM Proxy
  │  1. Resolve alias:  CodeFreedom/Pro → LITELLM_MODEL_ALIAS_PRO
  │                     → "DeepSeek/DeepSeek-V4-Pro"
  │  2. Find model:     model_name == "DeepSeek/DeepSeek-V4-Pro"
  │  3. Load config:    litellm_params + model_info + codefreedom plugins
  │  4. Run plugins:    reasoning-efforts translates effort levels
  │  5. Transform:      Anthropic /v1/messages → OpenAI /v1/chat/completions
  │  6. Strip params:   drop_params removes unsupported fields
  │  7. Send request:   to the upstream API
  ▼
DeepSeek API (or whichever provider the alias points to)
```

If the request fails with a rate limit, the proxy retries (up to `num_retries`). If the context is too large, it tries `context_window_fallbacks`. If all retries fail, it returns the error.

---

## Key Design Decisions

### Why all provider YAMLs are commented by default

Model specs (context windows, pricing, capabilities) change frequently. A long list of every available model would be outdated within weeks. By keeping all model entries commented in the examples, we:

- Avoid maintaining stale specs
- Keep the files minimal and readable
- Let users uncomment exactly what they need
- Make it obvious what's an example vs. what's actively configured

**The pattern is the point** — each file shows 1-2 commented examples that demonstrate the structure. From these you can add any model, because the shape is always the same.

### Why `drop_params: true` is used

Different providers accept different parameters. Anthropic accepts `thinking`, DeepSeek accepts `reasoning_effort`, and local models might accept neither. Without `drop_params`, sending an unsupported parameter causes a 400 error (or silently ignored). With `drop_params: true`, unsupported params are stripped automatically.

This is set both globally (in `litellm_settings`) and per-model (in `litellm_params`) for defense in depth.

### Why `model_info` values don't always match `litellm_params`

`model_info` describes what the model **actually supports**. `litellm_params` describes what the proxy **should use**. You might set `litellm_params.max_tokens` lower than `model_info.context_window` to leave headroom for output tokens or to enforce a tighter limit than the provider's default.

---

## Further Reading

| Topic | Link |
|-------|------|
| LiteLLM Proxy Overview | [docs.litellm.ai/docs/proxy/configs](https://docs.litellm.ai/docs/proxy/configs) |
| Config Settings Reference | [docs.litellm.ai/docs/proxy/config_settings](https://docs.litellm.ai/docs/proxy/config_settings) |
| Model Management | [docs.litellm.ai/docs/proxy/model_management](https://docs.litellm.ai/docs/proxy/model_management) |
| Load Balancing & Router | [docs.litellm.ai/docs/proxy/load_balancing](https://docs.litellm.ai/docs/proxy/load_balancing) |
| Fallbacks & Reliability | [docs.litellm.ai/docs/proxy/reliability](https://docs.litellm.ai/docs/proxy/reliability) |
| Completion Input Params | [docs.litellm.ai/docs/completion/input](https://docs.litellm.ai/docs/completion/input) |
| All Supported Providers | [docs.litellm.ai/docs/providers](https://docs.litellm.ai/docs/providers) |
| Custom Model Pricing | [docs.litellm.ai/docs/proxy/custom_pricing](https://docs.litellm.ai/docs/proxy/custom_pricing) |
