---
description: LiteLLM proxy overview, CLI commands, and environment setup.
---

# Proxy

CodeFreedom runs a [LiteLLM](https://docs.litellm.ai/) proxy between your code agent and LLM providers. One endpoint (`http://localhost:4000`), multiple backends — switch providers by changing environment variables, not code.

## Why LiteLLM

LiteLLM is an open-source proxy that translates between different LLM APIs. CodeFreedom uses it for:

- **Unified routing** — Claude Code talks to one URL. The proxy decides which provider handles each request.
- **Model aliases** — `CodeFreedom/Pro`, `CodeFreedom/Ultra`, etc. map to whichever provider you choose. Change the target without touching your agent config.
- **Retry and fallback** — automatic retries on timeouts and rate limits. Context-window fallbacks route to a larger model when a request is too big.
- **Spend tracking** — with a [PostgreSQL database](database.md), track costs across all providers from one dashboard.
- **Prometheus metrics** — request counts, latency, and token usage at `/metrics/`.

For the full LiteLLM reference, see the [LiteLLM docs](https://docs.litellm.ai/docs/simple_proxy).

## Quick Start

```bash
# Initialize proxy config files
codefreedom proxy init

# Set your API keys in ~/.codefreedom/.env.proxy.secrets
# (copy from ~/.codefreedom/.env.proxy.example)

# Start the proxy (Docker Compose)
codefreedom proxy start
```

The proxy always runs via `docker compose` against the self-hosted
`codefreedom:litellm-latest` image. The image bakes in the WebSearch
count display patch — no host-side `litellm` install is required.
See [Docker Mode](docker.md) for the architecture and override knobs.

## Providers

The proxy routes to any combination of these providers. Each provider is a YAML file under `~/.codefreedom/proxy/config/providers/`. See [Providers Overview](providers/index.md) for enabling and configuration.

| Provider                                                        | Description                                      | Models                                                                                                                                                                                                                                                                                                                                            |
| --------------------------------------------------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [DeepSeek](providers/deepseek/index.md)                         | V4-Flash, V4-Pro                                 | [V4-Flash](providers/deepseek/deepseek-v4-flash.md) · [V4-Pro](providers/deepseek/deepseek-v4-pro.md)                                                                                                                                                                                                                                             |
| [Azure Foundry](providers/azure-foundry/index.md)               | GPT-5.4 family                                   | [5.4](providers/azure-foundry/gpt-5.4.md) · [5.4-Mini](providers/azure-foundry/gpt-5.4-mini.md) · [5.4-Nano](providers/azure-foundry/gpt-5.4-nano.md)                                                                                                                                                                                             |
| [NVIDIA](providers/nvidia/index.md)                             | DeepSeek, GLM, Kimi, Step                        | [V4-Flash](providers/nvidia/deepseek-v4-flash.md) · [V4-Pro](providers/nvidia/deepseek-v4-pro.md) · [GLM-5.1](providers/nvidia/glm-5.1.md) · [Kimi-K2.6](providers/nvidia/kimi-k2.6.md) · [Step-3.7-Flash](providers/nvidia/step-3.7-flash.md)                                                                                                    |
| [OpenCode Zen](providers/opencode-zen/index.md)                 | Free-tier (Mimo, Nemotron, DeepSeek, MiniMax-M3) | [MiMo](providers/opencode-zen/mimo-v2.5.md) · [Nemotron-3-Super](providers/opencode-zen/nemotron-3-super.md) · [Nemotron-3-Ultra](providers/opencode-zen/nemotron-3-ultra.md) · [V4-Flash](providers/opencode-zen/deepseek-v4-flash.md) · [Big-Pickle](providers/opencode-zen/big-pickle.md) · [MiniMax-M3](providers/opencode-zen/minimax-m3.md) |
| [OpenRouter](providers/openrouter/index.md)                     | Aggregated, free tier                            | [Nemotron-3-Ultra](providers/openrouter/nemotron-3-ultra-550b-a55b.md) · [FreeRouter](providers/openrouter/freerouter.md)                                                                                                                                                                                                                         |
| [OpenAI Compatible](providers/openai-compatible/index.md)       | Any `/v1/chat/completions` endpoint              | [Default](providers/openai-compatible/default.md)                                                                                                                                                                                                                                                                                                 |
| [Anthropic Compatible](providers/anthropic-compatible/index.md) | Any `/v1/messages` endpoint                      | [Default](providers/anthropic-compatible/default.md)                                                                                                                                                                                                                                                                                              |
| [Local](providers/local/index.md)                               | Self-hosted (Ollama, vLLM, etc.)                 | [Qwen3.6-27B](providers/local/qwen3.6-27b.md) · [Qwen3.6-35B-A3B](providers/local/qwen3.6-35b-a3b.md)                                                                                                                                                                                                                                             |

Looking for free models to start with? See [Free Models](../../getting-started/free-models.md) for setup guides and rate-limit notes.

The proxy is available at `http://localhost:4000`.

## CLI Reference

Short alias: `cf px` is equivalent to `codefreedom proxy`.

### Initialize

```bash
codefreedom proxy init              # Copy example configs to ~/.codefreedom/
```

Copies `config.yaml`, provider YAMLs, `docker-compose.yaml`, and `.env` examples into `~/.codefreedom/proxy/`. Skips if files already exist — delete existing configs first, or merge changes manually from the [bundled examples](https://github.com/nilayparikh/codefreedom/tree/main/src/codefreedom/examples/proxy/).

### Start

```bash
codefreedom proxy start                # Start via Docker Compose
codefreedom proxy start --port 4001    # Override port for this run (sets LITELLM_PORT)
codefreedom proxy start --host 127.0.0.1  # Bind to localhost only (sets LITELLM_BIND_HOST)
```

| Flag     | Default   | Description                                                         |
| -------- | --------- | ------------------------------------------------------------------- |
| `--port` | `4000`    | Port to publish on the host (sets `LITELLM_PORT` for this run only) |
| `--host` | `0.0.0.0` | Bind address (sets `LITELLM_BIND_HOST` for this run only)           |

The proxy is always run via `docker compose`; there is no native Python mode.

### Stop & Status

```bash
codefreedom proxy stop              # `docker compose down` against the stack
codefreedom proxy status            # Show Docker Compose container status
codefreedom proxy restart           # `docker compose restart` (preserves state, no image pull)
```

### Validate

```bash
codefreedom proxy validate          # Check config for missing keys, broken includes
```

Parses `config.yaml`, checks that included provider files exist, and warns about unset environment variables.

### Generate VS Code Configuration

```bash
codefreedom vscode proxy config --host localhost              # Print to stdout
codefreedom vscode proxy config --host proxy.lan --port 4000  # Custom port
codefreedom vscode proxy config --host localhost --out entry.json  # Write to file
codefreedom vscode proxy config --host localhost --name "My Lab Proxy"  # Custom provider name
```

Generate a `chatLanguageModels.json` entry for VS Code from the running
LiteLLM proxy. The command reads `/v1/model/info` over HTTP and emits a
JSON object that you can drop into your VS Code `chatLanguageModels.json`
file (a list of provider entries).

| Flag     | Default       | Description                                                              |
| -------- | ------------- | ------------------------------------------------------------------------ |
| `--host` | (required)    | Hostname or IP VS Code should use to reach the proxy (not the bind host) |
| `--port` | `4000`        | Proxy port                                                               |
| `--name` | `CodeFreedom` | Provider name in the generated entry                                     |
| `--out`  | stdout        | Write to PATH instead of stdout                                          |

**Prerequisites**

| Requirement                | How to satisfy                                                                               |
| -------------------------- | -------------------------------------------------------------------------------------------- |
| Proxy is running           | `codefreedom proxy status` (or start it with `codefreedom proxy start`)                      |
| `LITELLM_MASTER_KEY` known | Exported in the shell, **or** present in `~/.codefreedom/.env.proxy.secrets`                 |
| A routable `--host`        | The bind host (`LITELLM_BIND_HOST`) is often `0.0.0.0` and not usable as a connection target |

`--host` is **required** because the bind host (often `0.0.0.0`) is not
routable. Pass the hostname or IP that VS Code should use to reach the
proxy: `localhost`, a LAN IP, or a DNS name.

**What the generated entry looks like**

```json
{
  "name": "CodeFreedom",
  "vendor": "customendpoint",
  "apiKey": "${input:codefreedom.litellm.master_key}",
  "apiType": "chat-completions",
  "models": [
    {
      "id": "Azure/GPT-5.4",
      "name": "Azure/GPT-5.4",
      "url": "http://proxy.lan:4000/v1",
      "toolCalling": true,
      "vision": true,
      "maxInputTokens": 922000,
      "maxOutputTokens": 128000,
      "supportsReasoningEffort": ["none", "low", "medium", "high", "xhigh"]
    },
    {
      "id": "Azure/GPT-5.4-Nano",
      "name": "Azure/GPT-5.4-Nano",
      "url": "http://proxy.lan:4000/v1",
      "toolCalling": true,
      "vision": true,
      "maxInputTokens": 272000,
      "maxOutputTokens": 128000
      // `supportsReasoningEffort` OMITTED — model only supports `none`
    }
  ]
}
```

`toolCalling` is **always `true`** for every model. LiteLLM does not have
a reliable, model-agnostic capability database — most providers do not
populate `supports_function_calling` even when their models do support
it — so a permissive default is friendlier than a sparse "no" that hides
tools the user actually has access to. If a model truly does not support
tool calling, the upstream API returns an error and VS Code surfaces it.

`vision`, `maxInputTokens`, and `maxOutputTokens` are read directly from
the proxy's `/v1/model/info` payload (keys: `supports_vision`,
`max_input_tokens`, `max_output_tokens`, with `max_tokens` as a shared
fallback). Missing fields fall back to conservative defaults (`128000`
input, `16000` output).

`supportsReasoningEffort` is resolved by case-insensitive substring
match against a hardcoded table of known model families
(`_REASONING_EFFORT_RULES` in `cli/proxy.py`). The table has three
return cases:

- **List** — the model exposes a real gradient. The list is emitted
  as-is.
- **Omitted** — the model only supports `"none"` (no real gradient).
  The field is dropped from the entry entirely; emitting `["none"]`
  would be a no-op and just add noise.
- **Empty list `[]`** — the model is unknown. VS Code treats this the
  same as omitting the field.

| Model pattern       | Effort levels                            | Behavior    |
| ------------------- | ---------------------------------------- | ----------- |
| `gpt-5.4`           | `none`, `low`, `medium`, `high`, `xhigh` | list        |
| `gpt-5.4-mini`      | `none`, `low`, `medium`                  | list        |
| `gpt-5.4-nano`      | (only `none`)                            | **omitted** |
| `deepseek-v4-pro`   | `none`, `low`, `medium`, `high`, `xhigh` | list        |
| `deepseek-v4-flash` | `none`, `low`, `medium`, `high`          | list        |
| `glm-5.1`           | (only `none`)                            | **omitted** |
| `kimi-k2.6`         | (only `none`)                            | **omitted** |
| `nemotron-3-ultra`  | `none`, `low`, `medium`, `high`          | list        |
| `nemotron-3-super`  | (only `none`)                            | **omitted** |
| `mimo-v2.5-free`    | `none`, `low`, `medium`, `high`          | list        |
| `minimax-m3-free`   | `none`, `low`, `medium`, `high`          | list        |
| `big-pickle`        | (only `none`)                            | **omitted** |
| `freerouter`        | (only `none`)                            | **omitted** |
| `qwen3.6-35b-a3b`   | `none`, `low`, `medium`, `high`          | list        |
| `qwen3.6-27b`       | (only `none`)                            | **omitted** |
| `codefreedom/ultra` | `none`, `low`, `medium`, `high`          | list        |
| `codefreedom/flash` | `none`, `low`, `medium`, `high`          | list        |
| `codefreedom/pro`   | (only `none`)                            | **omitted** |
| `codefreedom/air`   | (only `none`)                            | **omitted** |

Patterns match case-insensitively as substrings of the full model id
(e.g. `deepseek-v4-flash` matches `DeepSeek/DeepSeek-V4-Flash`,
`NVIDIA/DeepSeek-V4-Flash`, and `OpenCodeZen/DeepSeek-V4-Flash-FREE`).
Order matters: more-specific patterns come first so they win over
less-specific ones (e.g. `gpt-5.4-nano` is checked before `gpt-5.4`).

Edit the generated JSON to override any value, or extend the rules
table in `cli/proxy.py` to add a new family.

**Wiring the master key in VS Code**

The generated `apiKey` is a placeholder
(`${input:codefreedom.litellm.master_key}`). To actually authenticate:

1. In VS Code, run the command **"Add Secret Input"** (or the equivalent
   for your input variable system).
2. Use the same key name: `codefreedom.litellm.master_key`.
3. Paste your `LITELLM_MASTER_KEY` value.

VS Code will substitute it at runtime — the secret never lands in the
`chatLanguageModels.json` file itself. To use VS Code's standard
reference form, swap the placeholder for
`${input:chat.lm.secret.<hash>}` (the hash is generated by VS Code when
you create the secret).

**Failure modes**

| Exit code | Meaning                                                     |
| --------- | ----------------------------------------------------------- |
| 1         | Proxy not responding at `--host:--port`                     |
| 1         | `LITELLM_MASTER_KEY` not set in env or `.env.proxy.secrets` |
| 1         | Proxy returned `401`/`403` (rejected the master key)        |
| 1         | Network failure or invalid response from `/v1/model/info`   |

For end-to-end instructions (creating the file, restarting VS Code,
verifying models appear), see [VS Code Integration → Built-in](../../guides/vscode.md#built-in-chatlanguagemodelsjson-no-extension-required).

## Endpoints

| Endpoint                                    | Description                     |
| ------------------------------------------- | ------------------------------- |
| `http://localhost:4000/v1/chat/completions` | OpenAI chat completions         |
| `http://localhost:4000/v1/models`           | List available models           |
| `http://localhost:4000/v1/messages`         | Anthropic messages (translated) |
| `http://localhost:4000/metrics/`            | Prometheus metrics              |
| `http://localhost:4000/ui`                  | Admin UI (requires database)    |

Authentication uses a bearer token (`LITELLM_MASTER_KEY` from `.env.proxy.secrets`).

> **Auth errors in logs:** LiteLLM logs unauthenticated requests at ERROR level. This is normal — health checks and requests without the `Authorization` header will appear as errors. Set `LITELLM_LOG_LEVEL=WARNING` to reduce noise.

## Environment Files

The proxy loads two component-specific env files before the shared chain:

1. `~/.codefreedom/.env.proxy` — proxy settings (ports, aliases, base URLs)
2. `~/.codefreedom/.env.proxy.secrets` — API keys, master key

See the full [environment chain](../environment.md) for how these merge with workspace and system env vars.

## File Layout

```
~/.codefreedom/
├── .env.proxy                  # Proxy settings (generated from .env.proxy.example)
├── .env.proxy.secrets          # API keys (generated from .env.proxy.secrets.example)
└── proxy/
    ├── docker-compose.yaml     # Docker Compose deployment
    └── config/
        ├── config.yaml         # Core LiteLLM config (aliases, retry, fallbacks)
        └── providers/          # One YAML per provider
            ├── deepseek.yaml
            ├── azure-foundry.yaml
            ├── nvidia.yaml
            ├── opencode-zen.yaml
            ├── openrouter.yaml
            ├── openai-compatible.yaml
            ├── anthropic-compatible.yaml
            └── local.yaml
```
