"""
stdio-to-HTTP MCP bridge for codebase-memory-mcp.

Spawns the codebase-memory-mcp stdio MCP server as a persistent subprocess,
then runs an HTTP server on port 8330 that forwards JSON-RPC requests and
responses between the HTTP client and the stdio subprocess.

Optional: when ENABLE_UI=1, the upstream is started with --ui=true --port=9749
exposing its built-in 3D graph visualization on a second port inside the
container.

Usage (inside container):
    python3 bridge.py

Env vars:
    CBM_CACHE_DIR          — upstream SQLite cache directory (default: /cache)
    CBM_LOG_LEVEL          — log verbosity: debug|info|warn|error|none
    CBM_AUTO_INDEX         — "true" enables upstream auto-index on session start
    CBM_DIAGNOSTICS        — "1" enables upstream periodic diagnostics
    CBM_WORKERS            — override upstream worker count
    ENABLE_UI              — "1" spawns upstream with --ui=true --port=9749
    CBM_BINARY             — path to upstream binary (default:
                             /usr/local/bin/codebase-memory-mcp)
    MCP_LISTEN_HOST        — HTTP listen host (default: 0.0.0.0)
    MCP_LISTEN_PORT        — HTTP listen port (default: 8330)
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

# ── Configuration ─────────────────────────────────────────────────────────────

BINARY = os.environ.get("CBM_BINARY", "/usr/local/bin/codebase-memory-mcp")
LISTEN_HOST = os.environ.get("MCP_LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("MCP_LISTEN_PORT", "8330"))
UI_PORT = int(os.environ.get("CBM_UI_PORT", "9749"))
ENABLE_UI = os.environ.get("ENABLE_UI", "").strip().lower() in ("1", "true", "yes")

_UPSTREAM_ENV_KEYS = (
    "CBM_CACHE_DIR",
    "CBM_LOG_LEVEL",
    "CBM_AUTO_INDEX",
    "CBM_DIAGNOSTICS",
    "CBM_WORKERS",
    "CBM_DUMP_VERIFY_MIN_RATIO",
    "CBM_AUTO_INDEX_LIMIT",
)

# ── Globals ───────────────────────────────────────────────────────────────────

_proc: subprocess.Popen | None = None
_stdin_lock = threading.Lock()
_responses: dict[str, str] = {}
_response_events: dict[str, threading.Event] = {}
_reader_thread: threading.Thread | None = None
_shutdown = threading.Event()


# ── Stdout reader ─────────────────────────────────────────────────────────────


def _reader_loop() -> None:
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
                continue
            msg_id = msg.get("id")
            if msg_id is not None:
                sid = str(msg_id)
                _responses[sid] = line
                ev = _response_events.get(sid)
                if ev:
                    ev.set()


# ── HTTP Handler ──────────────────────────────────────────────────────────────

_WELL_KNOWN_PREFIX = "/.well-known/"


class MCPHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def _json_response(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_error(self, code: int, message: str) -> None:
        self._json_response(code, {"error": message})

    def _handle_well_known(self) -> bool:
        if not self.path.startswith(_WELL_KNOWN_PREFIX):
            return False
        self._json_error(404, "Not Found")
        return True

    def do_OPTIONS(self):
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

        try:
            req = json.loads(body)
        except json.JSONDecodeError:
            self._json_error(400, "Invalid JSON")
            return

        req_id = req.get("id")
        if req_id is None:
            _forward(body)
            self.send_response(202)
            self.end_headers()
            return

        sid = str(req_id)
        ev = threading.Event()
        _response_events[sid] = ev

        try:
            _forward(body)

            if not ev.wait(timeout=60):
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
        if self.path == "/healthz":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
            return

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


def _build_command() -> list[str]:
    cmd = [BINARY]
    if ENABLE_UI:
        cmd.extend(["--ui=true", f"--port={UI_PORT}"])
    return cmd


def _start_subprocess() -> subprocess.Popen:
    env = os.environ.copy()
    forwarded = {k: v for k, v in env.items() if k in _UPSTREAM_ENV_KEYS}
    for k, v in forwarded.items():
        env[k] = v
    return subprocess.Popen(
        _build_command(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )


def main() -> None:
    global _proc, _reader_thread

    print(f"[bridge] Starting codebase-memory-mcp: {' '.join(_build_command())}", flush=True)
    _proc = _start_subprocess()

    _reader_thread = threading.Thread(target=_reader_loop, daemon=True)
    _reader_thread.start()

    server = HTTPServer((LISTEN_HOST, LISTEN_PORT), MCPHandler)
    print(
        f"[bridge] HTTP MCP endpoint listening on {LISTEN_HOST}:{LISTEN_PORT}",
        flush=True,
    )
    if ENABLE_UI:
        print(f"[bridge] Graph UI enabled on port {UI_PORT}", flush=True)

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
