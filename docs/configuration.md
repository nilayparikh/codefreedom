# Configuration Guide

This guide covers _all_ configuration paths for CodeFreedom. All configuration
is done manually by editing YAML and env files.

---

## Table of Contents

1. [Which setup is right for you?](#which-setup-is-right-for-you)
2. [Quick Start: copy the example files](#quick-start-copy-the-example-files)
3. [Adding a cloud provider](#adding-a-cloud-provider)
4. [Adding an OpenAI-compatible endpoint](#adding-an-openai-compatible-endpoint)
5. [Adding an Anthropic-compatible endpoint](#adding-an-anthropic-compatible-endpoint)
6. [Adding a local self-hosted backend](#adding-a-local-self-hosted-backend)
7. [Configuring model aliases](#configuring-model-aliases)
8. [Disabling providers you don't need](#disabling-providers-you-dont-need)
9. [Disabling the LiteLLM proxy entirely](#disabling-the-liteLLM-proxy-entirely)
10. [Run modes: Docker Compose vs. Native Python](#run-modes-docker-compose-vs-native-python)
11. [Verifying your setup](#verifying-your-setup)

---

## Which setup is right for you?

| Your use case                                 | Jump to                                                                             |
| --------------------------------------------- | ----------------------------------------------------------------------------------- |
| **Cloud APIs only** (DeepSeek, Azure, etc.)   | [Adding a cloud provider](#adding-a-cloud-provider)                                 |
| **Self-hosted OpenAI-compatible endpoint**    | [Adding an OpenAI-compatible endpoint](#adding-an-openai-compatible-endpoint)       |
| **Self-hosted Anthropic-compatible endpoint** | [Adding an Anthropic-compatible endpoint](#adding-an-anthropic-compatible-endpoint) |
| **Hybrid cloud + self-hosted**                | Combine the sections above                                                          |
| **Anthropic API directly** (no proxy)         | Use `codefreedom claude --native-models` or `codefreedom claude --profile bare`     |

Every provider is **opt-in**. If you don't configure it, it stays disabled.

---

## Quick Start: copy the example files

```bash
# Initialize ~/.codefreedom/ with default configs
codefreedom --init

# This creates:
#   ~/.codefreedom/profiles/claude-code.json
#   ~/.codefreedom/profiles/claude-code-profiles.schema.json
#   ~/.codefreedom/proxy/config/config.yaml
#   ~/.codefreedom/proxy/config/providers/*.yaml
#   ~/.codefreedom/proxy/docker-compose.yaml
```

Edit these files to customize your setup:

```bash
vim ~/.codefreedom/proxy/config/config.yaml          # Main proxy config
vim ~/.codefreedom/proxy/config/providers/deepseek.yaml  # Provider configs
```

For runtime env vars, create `.env` and `.env.secrets` in your workspace:

```bash
# .env — non-secret settings
ANTHROPIC_BASE_URL="http://localhost:4000"
LITELLM_MASTER_KEY="sk-your-proxy-key"

# .env.secrets — API keys (NEVER commit)
DEEPSEEK_API_KEY="sk-your-key"
```

### Env load order

At runtime, env vars are loaded with this precedence (later overrides earlier):

| Priority | Source                   | Purpose                                            |
| -------- | ------------------------ | -------------------------------------------------- |
| 1        | `workspace/.env`         | Defaults — database, URLs, model aliases           |
| 2        | `workspace/.env.secrets` | Secrets — API keys, passwords (skipped if missing) |
| 3        | System environment       | Machine-level overrides (highest priority)         |

> If `.env.secrets` is missing, secrets must come from system env vars
> (`export DEEPSEEK_API_KEY=...`). System env vars always win over both files.

Now edit these files and follow the provider-specific sections below.

---

## Adding a cloud provider

Cloud providers (DeepSeek, Azure Foundry, NVIDIA, OpenCode Zen) come
pre-configured. You only need to set the API key.

### Example: Enable DeepSeek

**1. In `.env.secrets`, set the key:**

```bash
DEEPSEEK_API_KEY=sk-your-deepseek-api-key
```

**2. Verify the provider is included** in `litellm/config/config.yaml`:

```yaml
include:
  - providers/deepseek.yaml # ← already present by default
```

**3. Start the proxy:**

```bash
docker compose up -d
```

That's it. DeepSeek V4 Flash and V4 Pro are now available through the proxy
at `http://localhost:4000`.

### Enabling other cloud providers

| Provider      | API key env var             | Config file                    |
| ------------- | --------------------------- | ------------------------------ |
| DeepSeek      | `DEEPSEEK_API_KEY`          | `providers/deepseek.yaml`      |
| Azure Foundry | `MICROSOFT_FOUNDRY_API_KEY` | `providers/azure-foundry.yaml` |
| NVIDIA        | `NVIDIA_API_KEY`            | `providers/nvidia.yaml`        |
| OpenCode Zen  | `OPENCODE_ZEN_API_KEY`      | `providers/opencode-zen.yaml`  |

---

## Adding an OpenAI-compatible endpoint

Use `litellm/templates/openai-compatible.yaml` for **any** backend that speaks
the OpenAI `/v1/chat/completions` protocol — self-hosted servers, Ollama, vLLM,
third-party proxies, etc.

### Step-by-step

**1. Copy the template** to the providers directory:

```bash
cp litellm/templates/openai-compatible.yaml litellm/config/providers/
```

**2. Uncomment the provider** in `litellm/config/config.yaml`:

```yaml
include:
  # ...
  - providers/openai-compatible.yaml # ← uncomment this line
```

**3. Set env vars in `.env`** (or `.env.secrets` for the key):

```bash
# .env
OPENAI_COMPAT_BASE_URL=http://localhost:8000/v1
OPENAI_COMPAT_MODEL=openai/qwen3.6-27b

# .env.secrets
OPENAI_COMPAT_API_KEY=sk-your-key
```

> The env vars are already defined in `litellm/docker-compose.litellm.yml`
> (commented out) — uncomment them if you prefer per-service defaults.

**4. (Optional) Add more models.** Copy the model block in the provider YAML
and adjust `model_name` and `model`:

```yaml
  - model_name: OpenAI-Compatible/Fast
    litellm_params:
      <<: *openai_compat_params
      model: openai/os.environ/OPENAI_COMPAT_MODEL_FAST
      api_base: os.environ/OPENAI_COMPAT_BASE_URL
      api_key: os.environ/OPENAI_COMPAT_API_KEY
```

Then add `OPENAI_COMPAT_MODEL_FAST=openai/another-model` to `.env`.

**5. Restart the proxy:**

```bash
cf proxy --down && cf proxy --up
```

---

## Adding an Anthropic-compatible endpoint

Use `litellm/templates/anthropic-compatible.yaml` for **any** backend that
speaks the Anthropic `/v1/messages` protocol — self-hosted servers, third-party
proxies, etc.

### Step-by-step

**1. Copy the template** to the providers directory:

```bash
cp litellm/templates/anthropic-compatible.yaml litellm/config/providers/
```

**2. Uncomment the provider** in `litellm/config/config.yaml`:

```yaml
include:
  # ...
  - providers/anthropic-compatible.yaml # ← uncomment this line
```

**3. Set env vars in `.env`** (or `.env.secrets` for the key):

```bash
# .env
ANTHROPIC_COMPAT_BASE_URL=http://localhost:8000
ANTHROPIC_COMPAT_MODEL=claude-sonnet-4-20250514

# .env.secrets
ANTHROPIC_COMPAT_API_KEY=sk-your-key
```

> The env vars are already defined in `litellm/docker-compose.litellm.yml`
> (commented out) — uncomment them if you prefer per-service defaults.

**4. (Optional) Add more models.** Copy the model block in the provider YAML:

```yaml
  - model_name: Anthropic-Compatible/Haiku
    litellm_params:
      <<: *anthropic_compat_params
      model: anthropic/os.environ/ANTHROPIC_COMPAT_MODEL_HAIKU
      api_base: os.environ/ANTHROPIC_COMPAT_BASE_URL
      api_key: os.environ/ANTHROPIC_COMPAT_API_KEY
```

**5. Restart the proxy:**

```bash
cf proxy --down && cf proxy --up
```

---

## Adding a local self-hosted backend

The `providers/local.yaml` file is pre-configured for two local backends
on ports 8000 and 8001. This works with any OpenAI-compatible self-hosted
inference server.

### Configuration

**In `.env`:**

```bash
# Backend M (port 8000) — typically a larger/capable model
LOCAL_M_BASE_URL=http://host.docker.internal:8000/v1
LOCAL_M_MODEL=openai/qwen3.6_27b

# Backend S (port 8001) — typically a faster/smaller model
LOCAL_S_BASE_URL=http://host.docker.internal:8001/v1
LOCAL_S_MODEL=openai/qwen3.6_35b_a3b
```

**In `.env.secrets`:**

```bash
LOCAL_M_API_KEY=sk-dummy
LOCAL_S_API_KEY=sk-dummy
```

> If you only have one backend, leave the other key empty to disable it.
> Or comment out the unused model block in `providers/local.yaml`.

---

## Configuring model aliases

Model aliases let you map short `CodeFreedom/` names to specific provider models.
Claude Code discovers these aliases and presents them as available models.

### How aliases work

| Alias               | Default model                | Typical use                       |
| ------------------- | ---------------------------- | --------------------------------- |
| `CodeFreedom/Ultra` | `DeepSeek/DeepSeek-V4-Pro`   | Architecture, planning, reasoning |
| `CodeFreedom/Pro`   | `DeepSeek/DeepSeek-V4-Flash` | Implementation, coding            |
| `CodeFreedom/Flash` | `DeepSeek/DeepSeek-V4-Flash` | Fast/cheap tasks                  |
| `CodeFreedom/Air`   | (not set by default)         | Lightweight scanning              |

### Changing aliases

Edit `.env`:

```bash
# Route Ultra to a local model, Pro+Flash to DeepSeek cloud
LITELLM_MODEL_ALIAS_ULTRA="OpenAI-Compatible/Default"
LITELLM_MODEL_ALIAS_PRO="DeepSeek/DeepSeek-V4-Flash"
LITELLM_MODEL_ALIAS_FLASH="DeepSeek/DeepSeek-V4-Flash"
```

The model name must match a `model_name` in one of your provider YAML files.

Then restart the proxy:

```bash
docker compose down && docker compose up -d
```

---

## Disabling providers you don't need

Every provider is opt-in. There are three levels of disabling:

### Level 1: Leave API key empty (safest)

```bash
# .env.secrets
DEEPSEEK_API_KEY=sk-abc123          # Enabled
NVIDIA_API_KEY=                     # Disabled (empty)
```

LiteLLM skips providers with empty keys at startup.

### Level 2: Comment out in config.yaml (cleaner)

```yaml
# litellm/config/config.yaml
include:
  - providers/deepseek.yaml
  # - providers/nvidia.yaml          ← disabled
```

### Level 3: Comment out in docker-compose (cleanest)

```yaml
# litellm/docker-compose.litellm.yml
environment:
  # NVIDIA_API_KEY: ${NVIDIA_API_KEY:-}     ← disabled
```

### Quick-reference: what to disable

| To disable...        | In `config.yaml` comment out          | In `.env.secrets` empty/remove       |
| -------------------- | ------------------------------------- | ------------------------------------ |
| DeepSeek             | `providers/deepseek.yaml`             | `DEEPSEEK_API_KEY`                   |
| Azure Foundry        | `providers/azure-foundry.yaml`        | `MICROSOFT_FOUNDRY_API_KEY`          |
| NVIDIA               | `providers/nvidia.yaml`               | `NVIDIA_API_KEY`                     |
| OpenCode Zen         | `providers/opencode-zen.yaml`         | `OPENCODE_ZEN_API_KEY`               |
| OpenAI-Compatible    | `providers/openai-compatible.yaml`    | `OPENAI_COMPAT_API_KEY`              |
| Anthropic-Compatible | `providers/anthropic-compatible.yaml` | `ANTHROPIC_COMPAT_API_KEY`           |
| Local backends       | `providers/local.yaml`                | `LOCAL_M_API_KEY`, `LOCAL_S_API_KEY` |

---

## Disabling the LiteLLM proxy entirely

If you only want to run Claude Code with Anthropic's native API:

```bash
codefreedom claude --profile bare
```

The `bare` profile sets no proxy endpoint — Claude Code uses its default
Anthropic OAuth/login flow. Don't start the proxy in this case.

---

## Run modes: Docker Compose vs. Native Python

### Docker Compose (default)

```bash
docker compose up -d

# Or via CLI
codefreedom proxy --up
```

**Pros:** Isolated, GPU passthrough, managed lifecycle, production-ready.

### Native Python (no Docker)

```bash
pip install codefreedom[litellm]

codefreedom proxy --up --native --port 4000

# Or run litellm directly
litellm --config litellm/config/config.yaml --port 4000
```

**Pros:** No Docker needed, lighter weight.
**Cons:** No container isolation.

> **ARM64 / Apple Silicon:** Docker Compose mode is recommended. Native mode
> may encounter prisma/SQLite driver issues on arm64.

---

## Verifying your setup

### Check the proxy

```bash
codefreedom proxy --status
codefreedom proxy --validate
```

### Test model availability

```bash
curl -s http://localhost:4000/v1/models \
  -H "Authorization: Bearer sk-codefreedom-local" | jq '.data[].id'
```

Only models from enabled providers should appear.

### Launch Claude Code

```bash
codefreedom claude                    # Flash model (default)
codefreedom claude --profile pro      # Pro model
codefreedom claude --profile ultra    # Ultra model
codefreedom claude --list-profiles    # See all profiles
```

---

## Troubleshooting

| Symptom                               | Likely cause                           | Fix                                            |
| ------------------------------------- | -------------------------------------- | ---------------------------------------------- |
| "No models available"                 | No providers enabled or all keys empty | Enable at least one provider in `.env.secrets` |
| Proxy starts but model calls fail     | API key empty or wrong                 | Check `.env.secrets` for that provider         |
| Provider appears even though disabled | `config.yaml` still includes its file  | Comment out the `include` line                 |
| `docker compose` can't find file      | Not in project root                    | `cd` to codefreedom root first                 |
| Native mode fails with prisma error   | ARM64 prisma driver missing            | Use Docker Compose mode instead                |
