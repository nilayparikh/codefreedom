#!/bin/bash
# ── CodeFreedom Chrome Entrypoint ─────────────────────────────────────
# Supervises two long-running processes inside the container:
#
#   1. chrome-devtools-mcp (stdio MCP) — proxied over HTTP by mcp-proxy
#      on port $MCP_PORT (default 9223) at $MCP_PATH (default /mcp).
#   2. headless Chrome — listening on $CHROME_DEBUG_PORT (default 9222)
#      with CDP enabled.
#
# dumb-init (PID 1) forwards signals to all children so a single
# `docker stop` cleanly terminates both.  We also trap EXIT inside this
# script so the background mcp-proxy is killed even if chrome-wrapper
# exits unexpectedly.

set -e

CHROME_DEBUG_PORT="${CHROME_DEBUG_PORT:-9222}"
MCP_PORT="${MCP_PORT:-9223}"
MCP_PATH="${MCP_PATH:-/mcp}"
CHROME_DEVTOOLS_MCP_VERSION="${CHROME_DEVTOOLS_MCP_VERSION:-1.1.1}"

# ── Start mcp-proxy in background ─────────────────────────────────────
# mcp-proxy spawns chrome-devtools-mcp as a child stdio MCP server and
# exposes it on the configured HTTP port.  Logging goes to stderr so
# `docker logs` shows it interleaved with Chrome's stderr.

echo "[chrome-mcp] Starting mcp-proxy on port ${MCP_PORT}${MCP_PATH}" >&2
echo "[chrome-mcp]   -> chrome-devtools-mcp@${CHROME_DEVTOOLS_MCP_VERSION}" >&2
echo "[chrome-mcp]   -> Chrome CDP at http://127.0.0.1:${CHROME_DEBUG_PORT}" >&2

mcp-proxy \
    --port "${MCP_PORT}" \
    --host 0.0.0.0 \
    -- npx -y "chrome-devtools-mcp@${CHROME_DEVTOOLS_MCP_VERSION}" \
        --browser-url="http://127.0.0.1:${CHROME_DEBUG_PORT}" \
        --no-usage-statistics \
        --no-performance-crux &
MCP_PROXY_PID=$!

# ── Cleanup hook: ensure mcp-proxy dies with the container ────────────
# Only fires on real signals (SIGTERM/SIGINT), NOT on exec() replacement
# of this shell — the mcp-proxy child is reparented to the new PID 1
# (dumb-init) after exec.
cleanup() {
    if kill -0 "${MCP_PROXY_PID}" 2>/dev/null; then
        echo "[chrome-mcp] Stopping mcp-proxy (pid ${MCP_PROXY_PID})..." >&2
        kill "${MCP_PROXY_PID}" 2>/dev/null || true
    fi
}
trap cleanup SIGTERM SIGINT

# Give mcp-proxy a moment to bind the port so the first Claude Code
# connection from the host doesn't race the listener.
sleep 1

# ── Start Chrome in foreground (blocks until Chrome exits) ───────────
# dumb-init supervises Chrome for clean signal handling.  Any earlier
# crash of mcp-proxy (port-in-use, missing npx package) is fatal here
# because of `set -e` and surfaces as a non-zero container exit.
echo "[chrome] Starting headless Chrome on port ${CHROME_DEBUG_PORT}..." >&2
exec /usr/bin/dumb-init -- /usr/local/bin/chrome-wrapper
