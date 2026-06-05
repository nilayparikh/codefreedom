#!/bin/bash
# ── CodeFreedom Camoufox Entrypoint ──────────────────────────────────────
# Starts Xvfb, Openbox, x11vnc, noVNC, and the Python HTTP/MCP server.
# Supports --script mode (pipe YAML via stdin, get JSON on stdout, exit).

set -e

# Determine target user: PUID/PGID env vars, or default codefreedom (1000)
TARGET_UID="${PUID:-1000}"
TARGET_GID="${PGID:-$TARGET_UID}"

# Fix ownership of writable dirs (runs as root)
_fix_perms() {
    for dir in /userdata; do
        [ -d "$dir" ] || continue
        if [ "$(stat -c '%u:%g' "$dir" 2>/dev/null)" = "$TARGET_UID:$TARGET_GID" ]; then
            continue
        fi
        chown -R "$TARGET_UID:$TARGET_GID" "$dir" 2>/dev/null || true
    done

    # Camoufox — only GeoIP db files, not the whole tree
    local cfox
    cfox=$(python -c "import camoufox; print(camoufox.__path__[0])" 2>/dev/null) || true
    if [ -n "$cfox" ] && [ -d "$cfox" ]; then
        find "$cfox" -name "*.mmdb" \
            -exec chown "$TARGET_UID:$TARGET_GID" {} + 2>/dev/null || true
    fi

    # Browser home dir — camoufox cache lives here
    if [ -d /home/codefreedom ]; then
        chown -R "$TARGET_UID:$TARGET_GID" /home/codefreedom 2>/dev/null || true
    fi
}

_fix_perms

# Drop privileges — re-exec as target user unless already non-root
if [ "$(id -u)" = "0" ]; then
    exec gosu "$TARGET_UID:$TARGET_GID" \
        env HOME=/home/codefreedom "$0" "$@"
fi

# Ensure HOME is set for non-root users without passwd entry
export HOME="${HOME:-/home/codefreedom}"

PIDS=()

cleanup() {
    echo "" >&2
    echo "[*] Shutting down..." >&2
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null
    done
    wait
    echo "[*] Done." >&2
    exit "${EXIT_CODE:-0}"
}

trap cleanup SIGINT SIGTERM SIGHUP EXIT

# Detect script mode early — before anything prints to stdout
SCRIPT_MODE=false
for arg in "$@"; do
    if [ "$arg" = "--script" ]; then
        SCRIPT_MODE=true
        break
    fi
done

# --script reads YAML from stdin, save to temp file before
# background processes consume stdin
if [ "$SCRIPT_MODE" = "true" ]; then
    _STDIN_FILE=$(mktemp /tmp/script-stdin-XXXXXX.yaml)
    cat > "$_STDIN_FILE"
    set -- --script "$_STDIN_FILE"
fi

# In script mode, save real stdout for main.py, redirect shell stdout to stderr
if [ "$SCRIPT_MODE" = "true" ]; then
    exec 3>&1 1>&2
fi

# ── Start Xvfb ──────────────────────────────────────────────────────────
if [ -z "$DISPLAY" ] || [ "$DISPLAY" = ":99" ]; then
    DEPTH="${XVFB_DEPTH:-24}"
    Xvfb :99 -screen 0 1920x1080x${DEPTH} -ac +extension GLX +render -noreset &
    PIDS+=($!)
    export DISPLAY=:99
    sleep 0.5

    # Resize to XVFB_RESOLUTION if set
    TARGET_RES="${XVFB_RESOLUTION:-1920x1080}"
    if [[ "$TARGET_RES" != "1920x1080" ]]; then
        TARGET_W="${TARGET_RES%%x*}"
        TARGET_H="${TARGET_RES#*x}"
        MODELINE=$(cvt "$TARGET_W" "$TARGET_H" 60 2>/dev/null | grep Modeline)
        if [ -n "$MODELINE" ]; then
            MODE_NAME=$(echo "$MODELINE" | sed 's/.*"\([^"]*\)".*/\1/')
            MODE_PARAMS=$(echo "$MODELINE" | sed 's/.*"[^"]*"  *//')
            xrandr --newmode "$MODE_NAME" $MODE_PARAMS
            xrandr --addmode screen "$MODE_NAME"
            xrandr --output screen --mode "$MODE_NAME"
        fi
    fi
fi

# ── Start Openbox (WM for popup resize handles) ─────────────────────────
if command -v openbox &>/dev/null; then
    openbox --replace &
    PIDS+=($!)
    sleep 0.3
fi

# ── x11vnc and noVNC are intentionally excluded — MCP-only mode.
# The container exposes no VNC viewer or other HTTP endpoints.
# Only the MCP server on port 8420 is available.

# ── Wait for display to be ready ────────────────────────────────────────
for i in $(seq 1 30); do
    if xdpyinfo -display "$DISPLAY" &>/dev/null; then
        break
    fi
    sleep 0.5
done

# ── Launch the Python HTTP/MCP server ───────────────────────────────────
if [ "$SCRIPT_MODE" = "true" ]; then
    python /app/main.py "$@" 1>&3
    EXIT_CODE=$?
else
    python /app/main.py "$@"
    EXIT_CODE=$?
fi
