---
description: Reasoning-efforts mapping plugin — translates effort signals across Anthropic, OpenAI, and DeepSeek standards.
---

# Reasoning-Efforts Mapping

The proxy ships a CustomLogger plugin that normalises reasoning-effort signals across provider standards. Claude Code emits Anthropic's `output_config.effort` (`low` / `medium` / `high` / `xhigh` / `max`) but DeepSeek and OpenAI expect `reasoning_effort` (`none` / `low` / `medium` / `high` / `xhigh`). The plugin translates between them on every request.

## Why

LiteLLM's built-in translation only handles a single direction at a time and is brittle when Claude Code's native `/v1/messages` payload carries an Anthropic `output_config.effort` value (e.g. `"xhigh"`) to a provider that only understands the OpenAI `reasoning_effort` vocabulary. The two vocabularies are not the same:

| Provider | Values |
|----------|--------|
| Anthropic | `low` / `medium` / `high` / `xhigh` / `max` |
| OpenAI | `none` / `low` / `medium` / `high` / `xhigh` |
| DeepSeek | `low` / `medium` / `high` / `xhigh` / `max` (low/medium → high, xhigh → max) |

This plugin normalises all of them to a universal 4-level scale (`none` / `low` / `medium` / `high`) and then projects the canonical level back into whatever the target provider expects.

## How It Works

The plugin runs on two LiteLLM hooks:

- `async_pre_request_hook` — for Anthropic `/v1/messages` requests
- `async_log_pre_api_call` — for OpenAI `/v1/chat/completions` requests

Translation happens in both hooks because the two API surfaces have non-overlapping code paths in LiteLLM. The translation is idempotent: if the incoming request already matches the target provider's native syntax, it is left alone.

### Normalisation

Every incoming effort value is mapped to one of four canonical levels:

| Incoming | Canonical |
|----------|-----------|
| `none`, `off`, `disabled` | `none` |
| `low`, `minimal`, `min` | `low` |
| `medium`, `med` | `medium` |
| `high`, `hi` | `high` |
| `xhigh`, `max`, `maximum` | `high` |

### Lookup Order

For each incoming request, the plugin resolves the target provider's output in this order:

1. **Exact model match** under `models.<name>`
2. **Substring model match** (longest pattern wins) under `models.<pattern>`
3. **Provider-level defaults** under `providers.<provider>`
4. **Built-in defaults** — the 4-level universal projection

### Built-in Provider Defaults

| Provider | Output Type | Notes |
|----------|-------------|-------|
| `openai` | `reasoning_effort` | Canonical levels directly |
| `azure` | `reasoning_effort` | Canonical levels directly |
| `openai-compatible` | `reasoning_effort` | Canonical levels directly |
| `openrouter` | `reasoning_effort` | Canonical levels directly |
| `nvidia` | `reasoning_effort` | Canonical levels directly |
| `opencode-zen` | `reasoning_effort` | Canonical levels directly |
| `deepseek` | `reasoning_effort` | Canonical levels directly (thinking toggle auto-derived by LiteLLM) |
| `anthropic` | `output_config` | Canonical levels directly (thinking handled natively) |
| `bedrock` | `output_config` | Canonical levels directly |
| `vertex_ai` | `output_config` | Canonical levels directly |
| `azure-anthropic` | `output_config` | Canonical levels directly |

## Configuration

### File Locations

| File | Purpose |
|------|---------|
| `src/codefreedom/examples/proxy/config/plugins/reasoning-efforts/reasoning_efforts_mapping.py` | Plugin module (CustomLogger subclass) — baked into Docker image |
| `src/codefreedom/examples/proxy/config/plugins/reasoning-efforts/reasoning-efforts-mapping.yaml` | Per-model / per-provider mapping table — copied to host on `proxy init` |
| `~/.codefreedom/proxy/config/plugins/reasoning-efforts/reasoning-efforts-mapping.yaml` | User-editable override (copy from bundled example) |

### Activation

The plugin is wired in `config.yaml`:

```yaml
litellm_settings:
  callbacks:
    - prometheus
    - plugins.reasoning-efforts.reasoning_efforts_mapping.instance
```

> **Important:** Always reference the module-level singleton instance (`reasoning_efforts_mapping.instance`), not the class. LiteLLM's callback loader does `getattr(module, name)` and stores the result directly. If you reference the class, `isinstance(Callback, CustomLogger)` returns `False` and the call fails with a missing `self` error.

### YAML Config Format

The YAML config supports two sections: `providers` (per-provider defaults) and `models` (per-model overrides).

#### Per-Provider Defaults

```yaml
providers:
  deepseek:
    type: reasoning_effort
    levels:
      none: none
      low: high    # DeepSeek collapses low/medium -> high
      medium: high
      high: high
```

#### Per-Model Overrides

```yaml
models:
  gpt-5.4:
    type: reasoning_effort
    levels:
      none: none
      low: low
      medium: medium
      high: xhigh  # gpt-5.4 supports the extra step

  gpt-5.4-nano:
    type: reasoning_effort
    levels:
      none: none
      low: none    # clamp
      medium: none # clamp
      high: none   # clamp
```

Each model entry accepts:

- `type` — `"reasoning_effort"` (default) or `"output_config"`
- `thinking` — dict to also emit (e.g. `{type: enabled}` for DeepSeek)
- `extra_body` — dict merged into the outgoing request body
- `levels` — mapping from canonical level to provider-specific value. Missing levels fall back to the canonical value unchanged.
- Flat keys — `"none"`, `"low"`, `"medium"`, `"high"` at the top level are also accepted as shorthand for `levels:`.

### Runtime Behaviour

- The YAML is cached by mtime — edits take effect on the next request without a proxy restart.
- Missing or malformed YAML is silently ignored; all models fall back to built-in defaults.
- The plugin **never emits** `thinking` — each provider's native LiteLLM config derives the correct thinking toggle from `reasoning_effort` / `output_config`.

## Model-Specific Mappings

The bundled YAML includes mappings for all supported models. Key examples:

| Model | Canonical → Provider | Notes |
|-------|---------------------|-------|
| `claude-opus-4-8` | `high` → `xhigh` | Opus 4.8 supports the extra step |
| `claude-sonnet-4-6` | `high` → `max` | Sonnet 4.6 supports max |
| `gpt-5.4` | `high` → `xhigh` | Full gradient |
| `gpt-5.4-mini` | `high` → `medium` | Clamped at medium |
| `gpt-5.4-nano` | all → `none` | Text-only, no gradient |
| `deepseek-v4-pro` | `low/medium` → `high`, `high` → `max` | DeepSeek V4 Pro |
| `deepseek-v4-flash` | `low/medium` → `high`, `high` → `high` | Flash caps at high |
| `nemotron-3-ultra` | `high` → `high` | Full gradient |
| `nemotron-3-super` | all → `none` | Text-optimised, no gradient |
| `qwen3.6-35b-a3b` | `high` → `high` | Full gradient |
| `qwen3.6-27b` | all → `none` | Text-only, no gradient |
| `codefreedom/ultra` | `high` → `high` | Internal alias |
| `codefreedom/pro` | all → `none` | Fast tier, no gradient |
| `codefreedom/air` | all → `none` | No gradient |

## Customising

To customise mappings:

1. Copy the bundled YAML to your host config directory:
   ```bash
   mkdir -p ~/.codefreedom/proxy/config/plugins/
   cp src/codefreedom/examples/proxy/config/plugins/reasoning-efforts/reasoning-efforts-mapping.yaml ~/.codefreedom/proxy/config/plugins/reasoning-efforts-mapping.yaml
   ```
2. Edit the copy — model-level entries take precedence over provider-level, which take precedence over built-in defaults.
3. The proxy picks up changes on the next request (no restart needed).

An empty file is valid (everything uses built-in defaults) and a missing file is also valid.

## See Also

- [Proxy Configuration](config.md) — how the plugin is wired into `config.yaml`
- [Web Search Interception](websearch-interception.md) — the other bundled callback
- [LiteLLM Custom Logger docs](https://docs.litellm.ai/docs/proxy/custom_logger) — the underlying mechanism
