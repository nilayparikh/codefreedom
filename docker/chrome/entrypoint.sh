#!/bin/bash
# ── CodeFreedom Chrome Entrypoint ─────────────────────────────────────
# Supervises three processes inside the container:
#
#   1. chrome-devtools-mcp (stdio MCP) — proxied over HTTP by mcp-proxy
#      on port $MCP_PORT (default 9223) at $MCP_PATH (default /mcp).
#   2. headless Chrome — listening on $CHROME_DEBUG_PORT (default 9222)
#      with CDP enabled.
#   3. socat TCP forwarder — bridges 0.0.0.0:$CHROME_DEBUG_PORT →
#      localhost:$CHROME_DEBUG_PORT so Docker port mapping works even
#      when Chrome only binds to localhost (Chrome 149+ ignores
#      --remote-debugging-address=0.0.0.0).
#
# Chrome starts BEFORE socat so it gets the port first (prevents port
# conflict and the IPv4-fallback-to-IPv6 issue).  dumb-init (PID 1)
# forwards signals to all children so a single `docker stop` cleanly
# terminates all three.

set -e

CHROME_DEBUG_PORT="${CHROME_DEBUG_PORT:-9222}"
MCP_PORT="${MCP_PORT:-9223}"
MCP_PATH="${MCP_PATH:-/mcp}"
CHROME_DEVTOOLS_MCP_VERSION="${CHROME_DEVTOOLS_MCP_VERSION:-1.1.1}"
# socat listens on this port for CDP connections from outside the
# container and forwards to Chrome's 127.0.0.1:$CHROME_DEBUG_PORT.
# Must differ from CHROME_DEBUG_PORT to avoid port conflict.
CDP_PROXY_PORT="${CDP_PROXY_PORT:-9220}"

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

# ── Start Chrome in background ───────────────────────────────────────
# Chrome starts BEFORE socat so it binds to its preferred address
# (typically 127.0.0.1 or ::1) without port conflicts.
echo "[chrome] Starting headless Chrome on port ${CHROME_DEBUG_PORT}..." >&2
/usr/bin/dumb-init -- /usr/local/bin/chrome-wrapper &
CHROME_PID=$!

# ── Wait for Chrome CDP to be ready ──────────────────────────────────
# Poll both IPv4 and IPv6 localhost since Chrome 149+ may bind to
# either depending on system configuration.
CDP_READY=""
for i in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:${CHROME_DEBUG_PORT}/json/version" > /dev/null 2>&1; then
        CDP_READY="127.0.0.1"
        echo "[chrome] CDP ready on 127.0.0.1:${CHROME_DEBUG_PORT}" >&2
        break
    fi
    if curl -sf "http://[::1]:${CHROME_DEBUG_PORT}/json/version" > /dev/null 2>&1; then
        CDP_READY="::1"
        echo "[chrome] CDP ready on [::1]:${CHROME_DEBUG_PORT}" >&2
        break
    fi
    sleep 1
done

if [ -z "${CDP_READY}" ]; then
    echo "[chrome] ERROR: Chrome CDP did not become ready within 30s" >&2
    kill "${CHROME_PID}" "${MCP_PROXY_PID}" 2>/dev/null || true
    exit 1
fi

# ── Start socat CDP forwarder ────────────────────────────────────────
# Forwards 0.0.0.0:$CDP_PROXY_PORT -> localhost:$CHROME_DEBUG_PORT so
# Docker port mapping (mapping external port to $CDP_PROXY_PORT) can
# reach Chrome even when Chrome binds to localhost only.
# $CDP_PROXY_PORT differs from $CHROME_DEBUG_PORT to avoid port conflict.
# Target address format: IPv4 without brackets, IPv6 with brackets.
echo "[chrome-cdp] Starting socat forwarder on 0.0.0.0:${CDP_PROXY_PORT}" >&2
if [ "${CDP_READY}" = "::1" ]; then
    SOCAT_TARGET="TCP:[::1]:${CHROME_DEBUG_PORT}"
else
    SOCAT_TARGET="TCP:127.0.0.1:${CHROME_DEBUG_PORT}"
fi
socat TCP-LISTEN:"${CDP_PROXY_PORT}",fork,reuseaddr \
      "${SOCAT_TARGET}" &
SOCAT_CDP_PID=$!

# ── Cleanup hook ─────────────────────────────────────────────────────
cleanup() {
    for pid in "${MCP_PROXY_PID}" "${CHROME_PID}" "${SOCAT_CDP_PID}"; do
        if kill -0 "${pid}" 2>/dev/null; then
            kill "${pid}" 2>/dev/null || true
        fi
    done
}
trap cleanup SIGTERM SIGINT

# ── Wait for any child to exit ───────────────────────────────────────
# Blocks until Chrome, mcp-proxy, or socat exits.  When one dies we
# clean up the others and propagate the exit code.
wait -n
EXIT_CODE=$?

# Clean up remaining children
cleanup

# Small delay so remaining children have time to terminate gracefully
sleep 0.5

exit "${EXIT_CODE}"
