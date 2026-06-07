"""
stdio-to-HTTP MCP bridge for github-mcp-server.

Spawns github-mcp-server stdio as a persistent subprocess, then runs an
HTTP server on port 8082 that forwards JSON-RPC requests/responses between
the HTTP client and the stdio subprocess.

Usage (inside container):
    python3 bridge.py

Env vars:
    GITHUB_PERSONAL_ACCESS_TOKEN — forwarded to the subprocess
    MCP_LISTEN_HOST — HTTP listen host (default: 0.0.0.0)
    MCP_LISTEN_PORT — HTTP listen port (default: 8082)
    GITHUB_MCP_BINARY  — path to github-mcp-server (default: /app/github-mcp-server)
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── Configuration ─────────────────────────────────────────────────────────────

BINARY = os.environ.get("GITHUB_MCP_BINARY", "/app/github-mcp-server")
LISTEN_HOST = os.environ.get("MCP_LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("MCP_LISTEN_PORT", "8082"))
PAT = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")

# ── Globals ───────────────────────────────────────────────────────────────────

_proc: subprocess.Popen | None = None
_stdin_lock = threading.Lock()
_responses: dict[str, str] = {}  # id → JSON response
_response_events: dict[str, threading.Event] = (
    {}
)  # id → event signalled when response ready
_reader_thread: threading.Thread | None = None
_shutdown = threading.Event()


# ── Stdout reader ─────────────────────────────────────────────────────────────


def _reader_loop():
    """Read lines from subprocess stdout, classify as response or notification."""
    global _proc
    buf = b""
    while not _shutdown.is_set():
        if _proc is None or _proc.stdout is None:
            time.sleep(0.1)
            continue
        try:
            chunk = _proc.stdout.read(1)
        except Exception:
            time.sleep(0.1)
            continue
        if not chunk:
            time.sleep(0.05)
            if _proc.poll() is not None:
                # Process exited
                break
            continue
        buf += chunk
        if chunk == b"\n":
            line = buf.decode("utf-8", errors="replace").strip()
            buf = b""
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                sys.stderr.write(f"[bridge] non-JSON line: {line}\n")
                continue
            msg_id = msg.get("id")
            if msg_id is not None:
                sid = str(msg_id)
                _responses[sid] = line
                ev = _response_events.get(sid)
                if ev:
                    ev.set()
            # otherwise it's a notification — discard for now


# ── HTTP Handler ──────────────────────────────────────────────────────────────

_WELL_KNOWN_PREFIX = "/.well-known/"


class MCPHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        """Suppress default access logging to stdout."""
        pass

    # ── JSON helpers ────────────────────────────────────────────────────────

    def _json_response(self, code: int, payload: dict) -> None:
        """Send a JSON response (never HTML)."""
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_error(self, code: int, message: str) -> None:
        """Send a JSON error response."""
        self._json_response(code, {"error": message})

    # ── Well-known / OAuth metadata ────────────────────────────────────────
    # Claude Code's MCP HTTP client probes these endpoints during OAuth
    # discovery.  If they return HTML (the default send_error output), the
    # SDK fails to parse the body as JSON and crashes with "Invalid OAuth
    # error response".  We return proper JSON 404s so the client recognises
    # that this server does NOT require OAuth and falls back to plain
    # (unauthenticated) requests.

    def _handle_well_known(self) -> bool:
        """Handle OAuth well-known GET requests.  Returns True if consumed."""
        if not self.path.startswith(_WELL_KNOWN_PREFIX):
            return False
        # Return 404 as JSON — tells the client no OAuth server is available.
        self._json_error(404, "Not Found")
        return True

    def do_OPTIONS(self):
        """CORS preflight — allow any origin."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Mcp-Session-Id, Authorization, X-MCP-Readonly,"
            " X-MCP-Toolsets, X-MCP-Exclude-Tools, X-MCP-Features",
        )
        self.end_headers()

    def do_POST(self):
        if self.path != "/mcp":
            self._json_error(404, "Not Found")
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        # Parse the request to get its id
        try:
            req = json.loads(body)
        except json.JSONDecodeError:
            self._json_error(400, "Invalid JSON")
            return

        req_id = req.get("id")
        if req_id is None:
            # Notification — forward and return 202
            _forward(body)
            self.send_response(202)
            self.end_headers()
            return

        sid = str(req_id)
        ev = threading.Event()
        _response_events[sid] = ev

        try:
            _forward(body)

            # Wait for matching response (with timeout)
            if not ev.wait(timeout=30):
                self._json_error(504, "Upstream timeout")
                return

            resp = _responses.pop(sid, None)
            if resp is None:
                self._json_error(502, "No response from upstream")
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(resp.encode("utf-8"))
        finally:
            _response_events.pop(sid, None)
            _responses.pop(sid, None)

    def do_GET(self):
        # Health check
        if self.path == "/healthz":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
            return

        # OAuth well-known metadata — JSON 404 (not HTML)
        if self._handle_well_known():
            return

        self._json_error(404, "Not Found")


def _forward(body: bytes) -> None:
    """Write a JSON-RPC message to the subprocess stdin (thread-safe)."""
    global _proc
    with _stdin_lock:
        if _proc is None or _proc.stdin is None:
            raise RuntimeError("Subprocess not running")
        _proc.stdin.write(body)
        if not body.endswith(b"\n"):
            _proc.stdin.write(b"\n")
        _proc.stdin.flush()


# ── Start / stop ──────────────────────────────────────────────────────────────


def _start_subprocess() -> subprocess.Popen:
    env = os.environ.copy()
    env.setdefault("GITHUB_PERSONAL_ACCESS_TOKEN", PAT)
    proc = subprocess.Popen(
        [BINARY, "stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    # Read the initial server banner line(s) — the first non-JSON line
    # "GitHub MCP Server running on stdio" goes to stderr, actually.
    return proc


def main():
    global _proc, _reader_thread

    print(f"[bridge] Starting github-mcp-server: {BINARY}", flush=True)
    _proc = _start_subprocess()

    # Start stdout reader in background
    _reader_thread = threading.Thread(target=_reader_loop, daemon=True)
    _reader_thread.start()

    # Start HTTP server
    server = HTTPServer((LISTEN_HOST, LISTEN_PORT), MCPHandler)
    print(
        f"[bridge] HTTP MCP endpoint listening on {LISTEN_HOST}:{LISTEN_PORT}",
        flush=True,
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _shutdown.set()
        server.shutdown()
        if _proc:
            _proc.terminate()
            try:
                _proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _proc.kill()
        print("[bridge] Shutdown complete.", flush=True)


if __name__ == "__main__":
    main()
