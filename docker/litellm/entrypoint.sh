#!/bin/bash
# ── CodeFreedom LiteLLM + PostgreSQL Entrypoint ────────────────────────────
# 1. Init PG cluster on first run (locale=C, encoding=UTF8)
# 2. Start PG on localhost:5432 (TCP, container-only — never exposed)
# 3. Create the app database on first run
# 4. Push the Prisma schema
# 5. Start LiteLLM
#
# PG listens on localhost:5432 only.  No Unix socket, no host port bind.
# The DATABASE_URL uses TCP → simpler for Prisma and psql.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PG_DATA="${POSTGRES_DATA_DIR:-/var/lib/postgresql/data}"
PG_BACKUP="${POSTGRES_BACKUP_DIR:-/var/lib/postgresql/backup}"
PG_USER="${POSTGRES_USER:-litellm}"
PG_DB="${POSTGRES_DB:-litellm}"
PG_SHARED_BUFFERS="${POSTGRES_SHARED_BUFFERS:-256MB}"
PG_MAX_CONNECTIONS="${POSTGRES_MAX_CONNECTIONS:-100}"
LITELLM_PORT="${LITELLM_PORT:-4000}"
LITELLM_BIND_HOST="${LITELLM_BIND_HOST:-0.0.0.0}"
LITELLM_CONFIG="${LITELLM_CONFIG:-}"
LITELLM_UI_SOURCE_PATH="/usr/local/share/litellm-ui"
LITELLM_UI_PATH="${LITELLM_UI_PATH:-/app/litellm-ui}"

export PATH="/usr/local/pgsql/bin:/usr/local/bin:${PATH}"
mkdir -p "$PG_DATA" "$PG_BACKUP" "$LITELLM_UI_PATH"
if [ -d "$LITELLM_UI_SOURCE_PATH" ] && [ -z "$(find "$LITELLM_UI_PATH" -mindepth 1 -print -quit 2>/dev/null)" ]; then
    cp -a "$LITELLM_UI_SOURCE_PATH"/. "$LITELLM_UI_PATH"/
fi
chown litellm:litellm "$PG_DATA" "$PG_BACKUP"
chown -R litellm:litellm "$LITELLM_UI_PATH"

# ── Init PG cluster (first run only) ────────────────────────────────────────
FIRST_RUN=false
if [ ! -f "$PG_DATA/PG_VERSION" ]; then
    FIRST_RUN=true
    echo "[entrypoint] Initialising PostgreSQL cluster at $PG_DATA (locale=C, encoding=UTF8)"
    gosu litellm initdb -D "$PG_DATA" --username="$PG_USER" \
        --auth=trust --auth-host=trust --auth-local=trust \
        --locale=C --encoding=UTF8
fi

# ── postgresql.conf ─────────────────────────────────────────────────────────
cat > "$PG_DATA/postgresql.conf" <<PGCONF
listen_addresses = 'localhost'
port = 5432
max_connections = $PG_MAX_CONNECTIONS
shared_buffers = $PG_SHARED_BUFFERS
work_mem = 16MB
maintenance_work_mem = 128MB
effective_cache_size = 768MB
synchronous_commit = on
fsync = on
full_page_writes = on
wal_level = replica
logging_collector = on
log_directory = '$PG_BACKUP'
log_filename = 'postgresql-%Y-%m-%d.log'
log_rotation_age = 1d
log_rotation_size = 100MB
log_min_duration_statement = 1000ms
PGCONF

# ── pg_hba.conf ─────────────────────────────────────────────────────────────
cat > "$PG_DATA/pg_hba.conf" <<HBA
local   all   all          trust
host    all   all   127.0.0.1/32  trust
host    all   all   ::1/128       trust
HBA

chown litellm:litellm "$PG_DATA/postgresql.conf" "$PG_DATA/pg_hba.conf"

# ── Start PG ────────────────────────────────────────────────────────────────
echo "[entrypoint] Starting PostgreSQL..."
chown litellm:litellm "$PG_DATA" "$PG_BACKUP"
gosu litellm pg_ctl -D "$PG_DATA" -l "$PG_BACKUP/postgres.log" start -w -t 30

# ── Create the app database (first run only, AFTER PG is up) ────────────────
if $FIRST_RUN; then
    echo "[entrypoint] Creating database $PG_DB..."
    gosu litellm createdb -h 127.0.0.1 -U "$PG_USER" "$PG_DB" 2>&1 || \
        echo "[entrypoint] (createdb returned non-zero; will continue)"
fi

# ── DATABASE_URL ────────────────────────────────────────────────────────────
export DATABASE_URL="postgresql://${PG_USER}@127.0.0.1:5432/${PG_DB}"
echo "[entrypoint] DATABASE_URL=$DATABASE_URL"

# ── Prisma schema push ──────────────────────────────────────────────────────
SCHEMA=$(gosu litellm python3 -c "import litellm; from pathlib import Path; print(Path(litellm.__file__).parent / 'proxy' / 'schema.prisma')")
echo "[entrypoint] Pushing Prisma schema..."
cd /tmp && gosu litellm prisma db push --schema="$SCHEMA" --accept-data-loss --skip-generate

# ── Query engine binary ─────────────────────────────────────────────────────
# The Prisma Python client resolves the engine via multiple paths:
#   1. PRISMA_QUERY_ENGINE_BINARY env var (highest priority)
#   2. ./<engine-name> in CWD
#   3. ~/.npm/_npx/…/prisma/query-engine-* (npx cache from build)
#   4. ~/.cache/prisma-python/binaries/…/prisma-query-engine-* (global_path)
# We set the env var to the prisma-python cache first; if that doesn't exist,
# fall back to the npx cache path so LiteLLM's internal client also finds it.
QE=$(find /home/litellm/.cache/prisma-python/binaries -name 'prisma-query-engine-*' -type f 2>/dev/null | head -1)
if [ -z "$QE" ]; then
    QE=$(find /home/litellm/.npm/_npx -name 'prisma-query-engine-*' -type f 2>/dev/null | head -1)
fi
if [ -n "$QE" ] && [ -x "$QE" ]; then
    export PRISMA_QUERY_ENGINE_BINARY="$QE"
    echo "[entrypoint] PRISMA_QUERY_ENGINE_BINARY=$QE"
fi

# ── Warm up the Prisma engine (pre-starts the binary subprocess) ─────────────
# The Prisma Python client resolves the engine via `_ensure_file()` →
# `utils.ensure(BINARY_PATHS.query_engine)`.  The resolution chain is:
#   1. PRISMA_QUERY_ENGINE_BINARY env var
#   2. ./<engine-name> in CWD
#   3. BINARY_PATHS (hardcoded /root/.npm/_npx/… from build) — NOT at runtime
#   4. ~/.cache/prisma-python/binaries/…/prisma-query-engine-… (global_path)
# The global_path works, but the client still fails.  A pre-connect forces
# the binary subprocess to start and exit cleanly, proving the binary is
# functional and leaving no stale state.
echo "[entrypoint] Warming up Prisma engine..."
gosu litellm python3 -c "
import os, asyncio
os.environ['DATABASE_URL'] = 'postgresql://litellm@127.0.0.1:5432/litellm'
from prisma import Prisma
async def warm():
    db = Prisma()
    try:
        await db.connect()
        print('[entrypoint] Engine warm-up: connected')
        r = await db.query_raw('SELECT 1 as val')
        print(f'[entrypoint] Engine warm-up: query OK ({r})')
    except Exception as e:
        print(f'[entrypoint] Engine warm-up: {type(e).__name__}: {e}')
    finally:
        await db.disconnect()
asyncio.run(warm())
" 2>&1 || echo "[entrypoint] Engine warm-up failed (non-fatal)"

# ── Cleanup ─────────────────────────────────────────────────────────────────
cleanup() {
    echo "[entrypoint] Shutting down..."
    [ -n "${LITELLM_PID:-}" ] && kill -0 "$LITELLM_PID" 2>/dev/null && kill -TERM "$LITELLM_PID" 2>/dev/null || true
    wait "${LITELLM_PID:-}" 2>/dev/null || true
    # Only try to stop PG if it's still running — tini may have already
    # forwarded SIGTERM to it, in which case pg_ctl stop would just print
    # "PID file does not exist" noise.
    if [ -f "$PG_DATA/postmaster.pid" ] && gosu litellm pg_ctl -D "$PG_DATA" status 2>/dev/null; then
        gosu litellm pg_ctl -D "$PG_DATA" stop -m fast 2>&1 || true
    fi
}
trap cleanup EXIT TERM INT

# ── Plugin bootstrap ────────────────────────────────────────────────────────
# Each plugin's .py is baked into the image at /app/litellm-plugins/.
# LiteLLM's callback loader resolves the module path relative to the
# config file's directory (/app/litellm-config/).  The recipe's
# docker-compose.yaml uses SUBPATH mounts so the parent dirs
# /app/litellm-config/plugins/<name>/ are NOT bind-mounted.  The .yaml
# files inside are mounted individually; the .py symlinks we create
# here land in the (container-only) parent dirs and never leak onto
# the host.  Result: ~/.codefreedom/config/proxy/config/plugins/ on
# the host contains ONLY user-editable .yaml files.
#
# Failures here are non-fatal -- LiteLLM will start without the plugin
# if the symlink cannot be created.
PLUGIN_SRC="/app/litellm-plugins/reasoning_efforts_mapping.py"
PLUGIN_DST="/app/litellm-config/plugins/reasoning-efforts/reasoning_efforts_mapping.py"
if [ -f "$PLUGIN_SRC" ]; then
    mkdir -p "$(dirname "$PLUGIN_DST")" 2>/dev/null || true
    # Remove stale regular file from pre-symlink entrypoint versions
    [ -f "$PLUGIN_DST" ] && [ ! -L "$PLUGIN_DST" ] && rm -f "$PLUGIN_DST"
    if ln -sf "$PLUGIN_SRC" "$PLUGIN_DST" 2>/dev/null; then
        echo "[entrypoint] Plugin .py symlinked: $PLUGIN_DST -> $PLUGIN_SRC"
    else
        echo "[entrypoint] WARNING: Could not symlink plugin .py (read-only mount?)."
        echo "              The reasoning-efforts mapper will be unavailable."
    fi
fi

PLUGIN2_SRC="/app/litellm-plugins/system_message_merger.py"
PLUGIN2_DST="/app/litellm-config/plugins/system-message-merger/system_message_merger.py"
if [ -f "$PLUGIN2_SRC" ]; then
    mkdir -p "$(dirname "$PLUGIN2_DST")" 2>/dev/null || true
    [ -f "$PLUGIN2_DST" ] && [ ! -L "$PLUGIN2_DST" ] && rm -f "$PLUGIN2_DST"
    if ln -sf "$PLUGIN2_SRC" "$PLUGIN2_DST" 2>/dev/null; then
        echo "[entrypoint] Plugin .py symlinked: $PLUGIN2_DST -> $PLUGIN2_SRC"
    else
        echo "[entrypoint] WARNING: Could not symlink system-message-merger plugin."
    fi
fi

PLUGIN3_SRC="/app/litellm-plugins/image_router.py"
PLUGIN3_DST="/app/litellm-config/plugins/image-router/image_router.py"
if [ -f "$PLUGIN3_SRC" ]; then
    mkdir -p "$(dirname "$PLUGIN3_DST")" 2>/dev/null || true
    [ -f "$PLUGIN3_DST" ] && [ ! -L "$PLUGIN3_DST" ] && rm -f "$PLUGIN3_DST"
    if ln -sf "$PLUGIN3_SRC" "$PLUGIN3_DST" 2>/dev/null; then
        echo "[entrypoint] Plugin .py symlinked: $PLUGIN3_DST -> $PLUGIN3_SRC"
    else
        echo "[entrypoint] WARNING: Could not symlink image-router plugin."
    fi
fi

PLUGIN4_SRC="/app/litellm-plugins/filter_empty_errors.py"
PLUGIN4_DST="/app/litellm-config/plugins/filter-empty-errors/filter_empty_errors.py"
if [ -f "$PLUGIN4_SRC" ]; then
    mkdir -p "$(dirname "$PLUGIN4_DST")" 2>/dev/null || true
    [ -f "$PLUGIN4_DST" ] && [ ! -L "$PLUGIN4_DST" ] && rm -f "$PLUGIN4_DST"
    if ln -sf "$PLUGIN4_SRC" "$PLUGIN4_DST" 2>/dev/null; then
        echo "[entrypoint] Plugin .py symlinked: $PLUGIN4_DST -> $PLUGIN4_SRC"
    else
        echo "[entrypoint] WARNING: Could not symlink filter-empty-errors plugin."
    fi
fi

# ── Start LiteLLM ───────────────────────────────────────────────────────────
echo "[entrypoint] Starting LiteLLM on $LITELLM_BIND_HOST:$LITELLM_PORT..."
# --use_prisma_db_push: we already ran `prisma db push` above; tells LiteLLM
# to skip `prisma migrate deploy` entirely (avoids importing litellm_proxy_extras
# which we don't install).
# --use_v2_migration_resolver: silences the "Using default (v1) migration
# resolver" warning.  Harmless — the v2 resolver code is never reached because
# use_prisma_db_push=True makes use_migrate=False.
LITELLM_ARGS=(--host "$LITELLM_BIND_HOST" --port "$LITELLM_PORT" --use_prisma_db_push --use_v2_migration_resolver)
[ -n "${LITELLM_CONFIG:-}" ] && [ -f "$LITELLM_CONFIG" ] && LITELLM_ARGS+=(--config "$LITELLM_CONFIG")
# Forward docker-compose command: args (e.g. --config /app/litellm-config/config.yaml).
# Entrypoint defaults (--host, --port) come first so docker-compose overrides win.
LITELLM_ARGS+=("$@")
gosu litellm litellm "${LITELLM_ARGS[@]}" &
LITELLM_PID=$!
wait "$LITELLM_PID" || true
