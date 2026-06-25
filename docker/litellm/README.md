# CodeFreedom LiteLLM Proxy Image

Self-contained Docker image combining **LiteLLM** (proxy + dashboard) with an embedded **PostgreSQL 18.4** for spend logs, virtual keys, and team/org tables. Replaces `ghcr.io/berriai/litellm` in the CodeFreedom proxy stack.

## Overview

```text
tini (PID 1)
  └── entrypoint.sh
        ├── Boot PostgreSQL (localhost:5432, TCP only)
        ├── prisma db push (create/verify schema)
        └── exec litellm on :4000
```

- **Non-root:** Runs as `codefreedom` user (uid 1000).
- **Healthcheck:** `GET /health/liveliness`.
- **No database extra:** `prisma db push` creates the schema directly — no `litellm-proxy-extras` needed.

## Build

```bash
docker build \
  -t docker.io/nilayparikh/codefreedom:litellm-latest \
  -f docker/litellm/Dockerfile.LiteLLM docker/litellm/
```

### Build Args

| Arg                | Default                                      | Description             |
| ------------------ | -------------------------------------------- | ----------------------- |
| `IMAGE_VERSION`    | `0.1.0`                                      | OCI image version label |
| `LITELLM_FORK_URL` | `https://github.com/nilayparikh/litellm.git` | LiteLLM git fork        |
| `LITELLM_TAG`      | `v1.87.1`                                    | Pinned LiteLLM git tag  |
| `PG_VERSION`       | `18.4`                                       | PostgreSQL version      |
| `PG_SOURCE_URL`    | `https://github.com/postgres/postgres.git`   | PG source repo          |
| `PG_TAG`           | `REL_18_4`                                   | PG git tag              |

Override any arg at build time with `--build-arg`.

## Multi-Stage Architecture

### Stage 1 — `pg-builder`

Builds PostgreSQL 18.4 from source (stripped: no readline, zlib, PAM, LDAP, GSSAPI, SELinux, systemd, NLS, debug). Keeps ICU + OpenSSL for collation correctness and TLS.

### Stage 2 — `litellm-builder`

Installs LiteLLM from the git fork at the pinned tag with `--no-deps` (skipping `litellm-enterprise`, `granian`, etc.), then installs the curated minimal dependency set from `requirements.txt`. Applies the WebSearch count patch and pre-generates Prisma client/engine binaries.

### Stage 3 — `runtime`

Combines PG binaries + LiteLLM site-packages + tini + entrypoint. Exposes port 4000. Declares volumes for PG data and backups.

## Files

| File                       | Purpose                                                                       |
| -------------------------- | ----------------------------------------------------------------------------- |
| `Dockerfile.LiteLLM`       | Multi-stage build definition                                                  |
| `entrypoint.sh`            | Boots PG, pushes Prisma schema, starts LiteLLM                                |
| `requirements.txt`         | Curated minimal dependency list                                               |
| `patch_websearch_count.py` | Injects `server_tool_use.web_search_requests` into LiteLLM responses          |
| `patch_responses_azure.py` | Disables Azure Responses API auto-routing (not yet reliable on Azure Foundry) |

## Patches

### WebSearch Count Display (`patch_websearch_count.py`)

LiteLLM's `try_short_circuit_search` returns `"usage": {"input_tokens": 0, "output_tokens": 0}` — omitting the `server_tool_use.web_search_requests` field that Claude Code's TUI needs to display "Did N searches." This patch injects the missing field at build time. Idempotent; fails loudly if the target line changes.

### Azure Responses API (`patch_responses_azure.py`)

LiteLLM 1.87.x auto-routes GPT-5.x chat completions through the Azure Responses API when `reasoning_effort` + `tools` or `reasoning_summary` are present. Since Azure Foundry (`services.ai.azure.com`) does not reliably serve the Responses API yet, this patch restricts auto-routing to OpenAI only.

## Usage

Deployed via `docker compose` (see `~/.codefreedom/config/proxy/docker-compose.yaml`). Managed through the CLI:

```bash
codefreedom run proxy start    # start the proxy
codefreedom run proxy stop     # stop the proxy
codefreedom run proxy status   # check status
```

## Environment Variables (Entrypoint)

| Variable                   | Default                      | Description                 |
| -------------------------- | ---------------------------- | --------------------------- |
| `POSTGRES_DATA_DIR`        | `/var/lib/postgresql/data`   | PG data directory           |
| `POSTGRES_BACKUP_DIR`      | `/var/lib/postgresql/backup` | PG log/backup directory     |
| `POSTGRES_USER`            | `litellm`                    | PG superuser                |
| `POSTGRES_DB`              | `litellm`                    | App database name           |
| `POSTGRES_SHARED_BUFFERS`  | `256MB`                      | PG shared_buffers setting   |
| `POSTGRES_MAX_CONNECTIONS` | `100`                        | PG max_connections setting  |
| `LITELLM_PORT`             | `4000`                       | LiteLLM HTTP port           |
| `LITELLM_BIND_HOST`        | `0.0.0.0`                    | LiteLLM bind address        |
| `LITELLM_CONFIG`           | _(empty)_                    | Path to LiteLLM config file |

## Volumes

| Path                         | Purpose                      |
| ---------------------------- | ---------------------------- |
| `/var/lib/postgresql/data`   | PostgreSQL data (persistent) |
| `/var/lib/postgresql/backup` | PostgreSQL logs (persistent) |

## Security

- PostgreSQL listens on `localhost:5432` only — never exposed to the host network.
- `pg_hba.conf` uses `trust` for local connections only (single-container trust boundary).
- Runs as non-root `codefreedom` user (uid 1000).
- No SSH, no TCP PG listener outside the container.
