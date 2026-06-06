---
description: Stateless vs PostgreSQL mode, Admin UI, and spend tracking.
---

# Database

By default, the proxy runs **without a database** — pure stateless routing with zero persistence. Model routing and authentication work fine this way.

Connect a PostgreSQL database to unlock the Admin UI, spend tracking, key management, and prompt logging.

## Stateless (Default)

**What works:**
- Model routing and chat completions
- Master-key authentication
- Retry and fallback logic
- Prometheus metrics at `/metrics/`

**What doesn't work:**
- Admin UI (`/ui` shows "Not connected to DB!")
- Spend tracking and cost dashboards
- API key management via the UI
- Prompt logging

The default config has `store_model_in_db: false` and no `database_url` — nothing to set up.

## PostgreSQL Setup

**Step 1: Set `DATABASE_URL`** in `.env.proxy`:

```bash
DATABASE_URL=postgresql://user:password@localhost:5432/litellm
```

**Step 2: Enable database features** in `~/.codefreedom/proxy/config/config.yaml`:

```yaml
general_settings:
  database_url: os.environ/DATABASE_URL
  store_model_in_db: true
  store_prompts_in_spend_logs: true
```

**Step 3: Restart the proxy:**

```bash
codefreedom proxy stop
codefreedom proxy start --docker
```

LiteLLM runs the Prisma migration automatically on first start — it creates the schema in your PostgreSQL database.

## Admin UI

The LiteLLM Admin UI is available at `http://localhost:4000/ui`.

**Login credentials:**
- **Username:** `admin`
- **Password:** Your `LITELLM_MASTER_KEY` value

The Admin UI lets you manage API keys, view spend dashboards, configure teams, and inspect model usage across all providers.

> **Requires PostgreSQL.** Without a database connection, the login page fails because user credentials are stored in the database.

For more details, see [LiteLLM Admin UI](https://docs.litellm.ai/docs/advanced/admin-ui) and [LiteLLM Observability](https://docs.litellm.ai/docs/observability).
