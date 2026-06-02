# LiteLLM Proxy

CodeFreedom runs a standalone LiteLLM proxy. By default, it runs **without a
database** — pure stateless model routing with zero persistence. You can
optionally connect a PostgreSQL database to unlock the Admin UI, spend
tracking, key management, and prompt logging.

> **Cloud-only user?** Skip local providers. **Local + cloud?** Enable both.
> See the [Configuration Guide](configuration.md) for a complete walkthrough
> of user profiles and how to disable providers you don't need.

Configuration files are in `~/.codefreedom/proxy/` (initialized via `codefreedom --init`).

## Quick Start

```bash
# Initialize configs
codefreedom --init

# Start via Docker Compose
codefreedom proxy --up --docker

# Or start natively
codefreedom proxy --up

# Validate config
codefreedom proxy --validate
```

The proxy is available at `http://localhost:4000`.

## Database Backends

### No Database (Default)

The proxy starts with **no database connection**. This means:

- ✅ Zero-config — no PostgreSQL, no Prisma, no migrations
- ✅ Clean startup with no errors
- ✅ All model routing works (chat completions, model listing)
- ✅ Auth via `LITELLM_MASTER_KEY` only
- ❌ No Admin UI (login requires a database)
- ❌ No spend tracking, key management, or prompt logging

To use this mode, **do not set `database_url`** in the proxy config.
The config (`~/.codefreedom/proxy/config/config.yaml`) has `store_model_in_db: false`
and no `database_url` line.

### PostgreSQL (Production)

Connect to a PostgreSQL instance to unlock full LiteLLM features:
Admin UI, API key management, spend tracking, Teams/SSO, and prompt logging.

**Step 1: Set `DATABASE_URL` as an environment variable:**

```bash
export DATABASE_URL="postgresql://litellm_interface:YOUR_PASSWORD@postgres:5432/litellm_interface"
```

**Step 2: Enable database features in `~/.codefreedom/proxy/config/config.yaml`:**

```yaml
general_settings:
  database_url: os.environ/DATABASE_URL # uncomment
  store_model_in_db: true # change from false → true
  store_prompts_in_spend_logs: true # change from false → true
```

**Step 3: Restart the proxy:**

```bash
codefreedom proxy --down
codefreedom proxy --up --docker
```

The Prisma migration runs automatically on first start — LiteLLM creates the
schema in your PostgreSQL database.

## Provider Configuration

Provider definitions live in `~/.codefreedom/proxy/config/providers/`. Each YAML file
defines one or more models from a specific provider.

### Available Providers

| Provider             | File                                  | Models                                             |
| -------------------- | ------------------------------------- | -------------------------------------------------- |
| DeepSeek             | `providers/deepseek.yaml`             | DeepSeek-V4-Flash, DeepSeek-V4-Pro                 |
| Azure Foundry        | `providers/azure-foundry.yaml`        | Kimi-K2.6, DeepSeek V4 Flash                       |
| NVIDIA               | `providers/nvidia.yaml`               | DeepSeek-V4-Flash, MiniMax-M2.7, Kimi-K2.6         |
| OpenCode Zen         | `providers/opencode-zen.yaml`         | MIMO-V2.5-FREE, NEMOTRON-3-SUPER-FREE              |
| OpenAI-Compatible    | `providers/openai-compatible.yaml`    | Any OpenAI-compatible endpoint (bring your own)    |
| Anthropic-Compatible | `providers/anthropic-compatible.yaml` | Any Anthropic-compatible endpoint (bring your own) |
| Local                | `providers/local.yaml`                | Two pre-configured local backends                  |

### Enabling a Provider

Set the corresponding API key as an environment variable. Leave the key empty to
**disable** the provider — LiteLLM will skip it automatically. You can also
**remove the provider file from `config.yaml`** to fully exclude it.

```bash
# Enable DeepSeek
export DEEPSEEK_API_KEY="sk-your-key"

# Disable Azure — leave empty or remove the line entirely
export MICROSOFT_FOUNDRY_API_KEY=""

# Disable Local — leave empty or remove the line entirely
export LOCAL_M_API_KEY=""
export LOCAL_S_API_KEY=""
```

### Disabling Providers (Cloud-Only Users)

If you're a **cloud-only user** (no local models), you must disable the local provider:

1. Leave `LOCAL_M_API_KEY` and `LOCAL_S_API_KEY` empty
2. In `~/.codefreedom/proxy/config/config.yaml` — comment out or remove the line:
   ```yaml
   include:
     - providers/deepseek.yaml
     # - providers/local.yaml        ← disabled
   ```
3. Point model aliases to cloud models in the profiles:
   ```json
   "CLAUDE_MODEL": "DeepSeek/DeepSeek-V4-Flash"
   ```

### Adding a New Provider

1. Create a new YAML file in `~/.codefreedom/proxy/config/providers/`
2. Define your `model_list` entries with `litellm_params` and `model_info`
3. Add the file to the `include` list in `~/.codefreedom/proxy/config/config.yaml`
4. Set any required environment variables

## Model Aliases

Model aliases map short names to specific provider models. They're defined
in `config.yaml` via the `model_group_alias` block and controlled by
environment variables:

```bash
# .env — point aliases to your preferred provider
LITELLM_MODEL_ALIAS_ULTRA="DeepSeek/DeepSeek-V4-Pro"   # Best reasoning
LITELLM_MODEL_ALIAS_PRO="DGX/Qwen3.6-27B"              # Local coding model
LITELLM_MODEL_ALIAS_FLASH="DeepSeek/DeepSeek-V4-Flash"  # Fast/cheap
```

Claude Code discovers these aliases via gateway model discovery and presents
them as available models.

## Proxy Management

### Via Docker Compose

```bash
# Start
docker compose up -d

# Stop
docker compose down

# View logs
docker compose logs -f litellm

# Check status
docker compose ps
```

### Via CLI

```bash
codefreedom proxy --up
codefreedom proxy --down
codefreedom proxy --status

# Native Python mode (no Docker — requires litellm[proxy] extras)
codefreedom proxy --up --native
codefreedom proxy --validate
```

> **Native mode on ARM64:** May require `pip install codefreedom[litellm]` for proxy extras. Docker Compose mode is recommended on ARM64/Apple Silicon.

## Endpoints

| Endpoint                                    | Description                     |
| ------------------------------------------- | ------------------------------- |
| `http://localhost:4000/v1/chat/completions` | OpenAI chat completions         |
| `http://localhost:4000/v1/models`           | List available models           |
| `http://localhost:4000/v1/messages`         | Anthropic messages (translated) |
| `http://localhost:4000/metrics/`            | Prometheus metrics              |

Authentication: Bearer token (`LITELLM_MASTER_KEY` from `.env.secrets`).

> **Auth errors in logs:** LiteLLM logs failed authentication attempts at
> `ERROR` level — this is normal. Unauthenticated health checks or requests
> without the `Authorization` header will appear as ERROR lines but the proxy
> is functioning correctly. To reduce noise, set `LITELLM_LOG_LEVEL=WARNING`.

## Admin UI

The LiteLLM Admin UI is available at `http://localhost:4000/ui`. Use it to
manage API keys, teams, spend tracking, and model configurations.

**The Admin UI requires a PostgreSQL database.** Without a database
connection, the login page shows "Not connected to DB!" and authentication
fails because user credentials are stored in the database.

To enable the Admin UI:

1. Set up a [PostgreSQL database](#postgresql-production)
2. Restart the proxy
3. Login at `http://localhost:4000/ui` with:
   - **Username:** `admin`
   - **Password:** your `LITELLM_MASTER_KEY` value

## Router Settings

Key settings in `config.yaml`:

| Setting                                           | Default | Description                                |
| ------------------------------------------------- | ------- | ------------------------------------------ |
| `num_retries`                                     | 5       | Retries on timeout/rate-limit errors       |
| `allowed_fails`                                   | 3       | Cooldown a model after N failures/minute   |
| `context_window_fallbacks`                        | 27B→35B | Auto-fallback for context overflow         |
| `drop_params`                                     | true    | Strip unsupported params before forwarding |
| `use_chat_completions_url_for_anthropic_messages` | true    | Translate Anthropic→OpenAI format          |

## Metrics

Prometheus metrics are exposed at `/metrics/`. Set `LITELLM_REQUIRE_AUTH_METRICS=true`
to require authentication for the metrics endpoint.

These metrics can be scraped by Prometheus or any OpenTelemetry-compatible
collector (e.g., Alloy) by pointing to `http://litellm-codefreedom:4000/metrics/`.
