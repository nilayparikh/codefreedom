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

- **Non-root:** Runs as `litellm` user (uid 999).
- **Healthcheck:** TCP socket connect to `127.0.0.1:4000`.
- **No database extra:** `prisma db push` creates the schema directly -- no `litellm-proxy-extras` needed.

## Build

The image uses a three-stage build. The PG base and LiteLLM base are pre-built checkpoints pushed to the registry; the final image is a thin runtime overlay.

```bash
# Stage 1 -- PG base (rarely rebuilt, quarterly at most)
docker build \
  -t nilayparikh/codefreedom:litellm-pg-base-latest \
  -f docker/litellm/Dockerfile.PgBase docker/litellm/

# Stage 2 -- LiteLLM base (rebuild on LITELLM_TAG, patch, or plugin changes)
docker build \
  -t nilayparikh/codefreedom:litellm-base-v1.90.0 \
  -f docker/litellm/Dockerfile.LitellmBase docker/litellm/

# Stage 3 -- Final runtime image (fast, ~1-2 min)
docker build \
  -t nilayparikh/codefreedom:litellm-latest \
  -f docker/litellm/Dockerfile.LitellmFinal docker/litellm/
```

### Build Args

| Arg                | Default                                      | Stage  | Description             |
| ------------------ | -------------------------------------------- | ------ | ----------------------- |
| `PG_VERSION`       | `18.4`                                       | PgBase | PostgreSQL version      |
| `PG_SOURCE_URL`    | `https://github.com/postgres/postgres.git`   | PgBase | PG source repo          |
| `PG_TAG`           | `REL_18_4`                                   | PgBase | PG git tag              |
| `LITELLM_FORK_URL` | `https://github.com/nilayparikh/litellm.git` | Base   | LiteLLM git fork        |
| `LITELLM_TAG`      | `v1.90.0`                                    | Base   | Pinned LiteLLM git tag  |
| `IMAGE_VERSION`    | `1.0.0`                                      | Final  | OCI image version label |
| `PG_BASE_IMAGE`    | `nilayparikh/codefreedom:litellm-pg-base-latest` | Base | PG base image       |
| `LITELLM_BASE_IMAGE` | `nilayparikh/codefreedom:litellm-base-v1.90.0` | Final | LiteLLM base image  |

Override any arg at build time with `--build-arg`.

## Multi-Stage Architecture

### Stage 1 -- `Dockerfile.PgBase`

Builds PostgreSQL 18.4 from source (stripped: no readline, zlib, PAM, LDAP, GSSAPI, SELinux, systemd, NLS, debug). Keeps ICU + OpenSSL for collation correctness and TLS. Produces `/usr/local/pgsql` binaries only.

### Stage 2 -- `Dockerfile.LitellmBase`

Installs LiteLLM from the git fork at the pinned tag with `--no-deps` (skipping `litellm-enterprise`, `granian`, etc.), then installs the curated minimal dependency set from `requirements.txt`. Applies all 5 patches. Copies plugins and PG binaries. Pre-generates Prisma client/engine binaries.

**Not directly runnable** -- this is a build artifact.

### Stage 3 -- `Dockerfile.LitellmFinal`

Thin runtime overlay: adds tini, gosu, nodejs, runtime libs. Copies everything from the LiteLLM base. Sets up the `litellm` user, volumes, entrypoint, and healthcheck. Exposes port 4000.

Build time: ~1-2 minutes (no compilation, no pip install, no Prisma).

## Files

| File                       | Purpose                                                                  |
| -------------------------- | ------------------------------------------------------------------------ |
| `Dockerfile.PgBase`        | Stage 1: PostgreSQL build from source                                    |
| `Dockerfile.LitellmBase`   | Stage 2: LiteLLM + deps + patches + Prisma (build artifact)             |
| `Dockerfile.LitellmFinal`  | Stage 3: Runtime overlay with user setup, volumes, healthcheck           |
| `entrypoint.sh`            | Boots PG, pushes Prisma schema, symlinks plugins, starts LiteLLM        |
| `requirements.txt`         | Curated minimal dependency list                                          |
| `patches/`                 | Build-time patches applied to LiteLLM site-packages                      |
| `plugins/`                 | CustomLogger plugins baked into the image                                |

## Patches

All patches are applied at build time in `Dockerfile.LitellmBase`. Each modifies the installed site-packages file in place. Idempotent; builds fail loudly if target code changes.

### WebSearch Count Display (`patches/patch_websearch_count.py`)

Injects `server_tool_use.web_search_requests` into LiteLLM responses so Claude Code's TUI displays "Did N searches." Patches the short-circuit path, agentic loop typed-plan path, and legacy path.

### Retry-After Type Cast (`patches/patch_retry_after_type.py`)

Wraps `min_timeout` in `float()` inside `_calculate_retry_after` to fix `TypeError: '>' not supported between instances of 'str' and 'float'` when `retry_after` is set via `os.environ/` (always a string).

### Anthropic Fake Stream Logging (`patches/patch_anthropic_fake_stream_logging.py`)

Adds an early-return guard for `FakeAnthropicMessagesStreamIterator` in `_handle_anthropic_messages_response_logging`. Prevents `ValidationError` spam on every streaming request when `use_chat_completions_url_for_anthropic_messages = True`.

### Parse Search Tools Noise (`patches/patch_parse_search_tools_noise.py`)

Suppresses the repeated "LiteLLM: Proxy initialized with Search Tools" print that fires every 30 seconds on the `add_deployment` scheduler job. Adds a `_search_tools_printed` sentinel.

### Azure Responses API (`patches/patch_responses_azure.py`)

Removes `"azure"` from the Responses API auto-routing condition in `main.py`. Azure Foundry does not reliably serve the Responses API yet; restricts auto-routing to OpenAI only.

## Plugins

CustomLogger plugins baked into `/app/litellm-plugins/`. The entrypoint symlinks them into the config mount so LiteLLM can find them. Plugin YAML configs are user-editable on the host.

| Plugin | File | Purpose |
| --- | --- | --- |
| Reasoning Efforts | `plugins/reasoning_efforts_mapping.py` | Translates reasoning-effort signals across provider standards |
| System Message Merger | `plugins/system_message_merger.py` | Merges multiple system messages into one for models that require it |
| Image Router | `plugins/image_router.py` | Routes image payloads through VLMs for text-only target models |
| Empty-Auth Error Filter | `plugins/filter_empty_errors.py` | Drops unauthenticated / pre-routing failure rows from `LiteLLM_ErrorLogs` |

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

- PostgreSQL listens on `localhost:5432` only -- never exposed to the host network.
- `pg_hba.conf` uses `trust` for local connections only (single-container trust boundary).
- Runs as non-root `litellm` user (uid 999).
- No SSH, no TCP PG listener outside the container.
