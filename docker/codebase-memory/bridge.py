"""
stdio-to-HTTP MCP bridge for codebase-memory-mcp.

Spawns the codebase-memory-mcp stdio MCP server as a persistent subprocess,
then runs an HTTP server on port 8330 that forwards JSON-RPC requests and
responses between the HTTP client and the stdio subprocess.

Optional: when ENABLE_UI=1, the upstream is started with --ui=true --port=9749
exposing its built-in 3D graph visualization on a second port inside the
container.  The upstream binds the UI server to 127.0.0.1 only, so the
bridge also runs a small reverse proxy on 0.0.0.0:9749 that forwards
traffic to it — without that proxy Docker port mapping would reject
host connections with ``connection reset by peer``.

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
    REQUEST_TIMEOUT        — per-request upstream timeout in seconds (default: 60)
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ── Configuration ─────────────────────────────────────────────────────────────

BINARY = os.environ.get("CBM_BINARY", "/usr/local/bin/codebase-memory-mcp")
LISTEN_HOST = os.environ.get("MCP_LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("MCP_LISTEN_PORT", "8330"))
UI_PORT = int(os.environ.get("CBM_UI_PORT", "9749"))
UI_UPSTREAM_PORT = int(os.environ.get("CBM_UI_UPSTREAM_PORT", "19749"))
ENABLE_UI = os.environ.get("ENABLE_UI", "").strip().lower() in ("1", "true", "yes")
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "60"))

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
_stderr_thread: threading.Thread | None = None
_stderr_buffer: list[str] = []
_stderr_lock = threading.Lock()
_shutdown = threading.Event()
_upstream_alive = threading.Event()


def _upstream_running() -> bool:
    return _proc is not None and _proc.poll() is None


# ── Stdout reader ─────────────────────────────────────────────────────────────


def _reader_loop() -> None:
    """Read lines from subprocess stdout, classify as response or notification."""
    global _proc
    _upstream_alive.set()
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
            if _proc is not None and _proc.poll() is not None:
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


# ── Stderr drain ──────────────────────────────────────────────────────────────


def _stderr_loop() -> None:
    """Drain upstream stderr to container logs and keep the last 50 lines.

    Without this, a 64 KiB pipe buffer fills in a few seconds and the
    upstream blocks on its next stderr write.
    """
    while not _shutdown.is_set():
        if _proc is None or _proc.stderr is None:
            time.sleep(0.1)
            continue
        try:
            line = _proc.stderr.readline()
        except Exception:
            time.sleep(0.1)
            continue
        if not line:
            time.sleep(0.05)
            if _proc is not None and _proc.poll() is not None:
                break
            continue
        text = line.decode("utf-8", errors="replace").rstrip()
        if text:
            print(f"[upstream] {text}", flush=True)
            with _stderr_lock:
                _stderr_buffer.append(text)
                if len(_stderr_buffer) > 50:
                    del _stderr_buffer[: len(_stderr_buffer) - 50]


def _recent_stderr() -> list[str]:
    with _stderr_lock:
        return list(_stderr_buffer)


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
        self.send_header("Access-Control-Allow-Origin", "*")
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

        if not _upstream_running():
            self._json_error(502, "Upstream MCP server is not running")
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
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            return

        sid = str(req_id)
        ev = threading.Event()
        _response_events[sid] = ev

        try:
            _forward(body)

            if not ev.wait(timeout=REQUEST_TIMEOUT):
                self._json_error(504, "Upstream timeout")
                return

            resp = _responses.pop(sid, None)
            if resp is None:
                self._json_error(502, "No response from upstream")
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(resp.encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError, OSError) as exc:
            self._json_error(502, f"Upstream pipe failure: {exc}")
        finally:
            _response_events.pop(sid, None)
            _responses.pop(sid, None)

    def do_GET(self):
        if self.path == "/healthz":
            if not _upstream_running():
                self._json_response(
                    503,
                    {
                        "status": "down",
                        "upstream_alive": False,
                        "stderr_tail": _recent_stderr()[-5:],
                    },
                )
                return
            self._json_response(
                200,
                {
                    "status": "ok",
                    "upstream_alive": True,
                    "ui_enabled": ENABLE_UI,
                    "ui_port": UI_PORT if ENABLE_UI else None,
                },
            )
            return

        if self._handle_well_known():
            return

        self._json_error(404, "Not Found")


def _forward(body: bytes) -> None:
    """Write a JSON-RPC message to the subprocess stdin (thread-safe)."""
    global _proc
    with _stdin_lock:
        if not _upstream_running() or _proc is None or _proc.stdin is None:
            raise RuntimeError("Upstream MCP server is not running")
        _proc.stdin.write(body)
        if not body.endswith(b"\n"):
            _proc.stdin.write(b"\n")
        _proc.stdin.flush()


# ── Start / stop ──────────────────────────────────────────────────────────────


def _build_command() -> list[str]:
    cmd = [BINARY]
    if ENABLE_UI:
        cmd.extend(["--ui=true", f"--port={UI_UPSTREAM_PORT}"])
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
    global _proc, _reader_thread, _stderr_thread

    print(
        f"[bridge] Starting codebase-memory-mcp: {' '.join(_build_command())}",
        flush=True,
    )
    _proc = _start_subprocess()

    _reader_thread = threading.Thread(target=_reader_loop, daemon=True)
    _reader_thread.start()

    _stderr_thread = threading.Thread(target=_stderr_loop, daemon=True)
    _stderr_thread.start()

    _wait_for_upstream_mcp(timeout=15.0)

    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), MCPHandler)
    print(
        f"[bridge] HTTP MCP endpoint listening on {LISTEN_HOST}:{LISTEN_PORT}",
        flush=True,
    )

    ui_proxy: _UiProxy | None = None
    if ENABLE_UI:
        _wait_for_upstream_ui(UI_UPSTREAM_PORT, timeout=10.0)
        ui_proxy = _UiProxy(listen_host=LISTEN_HOST, listen_port=UI_PORT).start()
        print(
            f"[bridge] Graph UI proxy listening on {LISTEN_HOST}:{UI_PORT}"
            f" -> 127.0.0.1:{UI_UPSTREAM_PORT}",
            flush=True,
        )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _shutdown.set()
        server.shutdown()
        if ui_proxy is not None:
            ui_proxy.stop()
        if _proc:
            _proc.terminate()
            try:
                _proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _proc.kill()
        print("[bridge] Shutdown complete.", flush=True)


def _wait_for_upstream_mcp(timeout: float) -> None:
    """Send a JSON-RPC ``initialize`` and wait for the first valid response.

    The upstream subprocess needs a moment to set up its JSON-RPC handler.
    Without this wait, the HTTP server accepts requests before the
    upstream is ready, causing 502 "No response from upstream" on the
    first few calls. We send a lightweight ``initialize`` request and
    block until we get a response (or timeout).
    """
    deadline = time.monotonic() + timeout
    init_req = json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "bridge", "version": "1.0"},
            },
            "id": "startup",
        }
    ).encode("utf-8")

    ev = threading.Event()
    _response_events["startup"] = ev

    try:
        while time.monotonic() < deadline:
            if not _upstream_running():
                time.sleep(0.1)
                continue
            try:
                _forward(init_req)
            except RuntimeError:
                time.sleep(0.2)
                continue
            if ev.wait(timeout=2.0):
                _responses.pop("startup", None)
                print("[bridge] Upstream MCP ready.", flush=True)
                return
            # Retry — the upstream might not have been ready on the first send.
    finally:
        _response_events.pop("startup", None)
        _responses.pop("startup", None)

    print(
        f"[bridge] WARNING: upstream MCP did not respond to initialize"
        f" within {timeout:.1f}s — requests may fail until it is ready.",
        flush=True,
    )


def _wait_for_upstream_ui(port: int, *, timeout: float) -> None:
    """Block until the upstream CBM UI server is accepting connections.

    The upstream is a separate process so its TCP listener may not be up
    the instant the bridge is. Polling ``127.0.0.1:port`` for up to
    *timeout* seconds keeps us from racing the host port mapping.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    print(
        f"[bridge] WARNING: upstream UI did not start on 127.0.0.1:{port}"
        f" within {timeout:.1f}s — the proxy will start anyway and retry"
        " on each request.",
        flush=True,
    )


class _UiProxy:
    """Trivial HTTP reverse proxy from ``0.0.0.0:port`` → ``127.0.0.1:port``.

    CBM's built-in UI server only binds 127.0.0.1; without this proxy
    Docker port mapping (``-p 9749:9749``) cannot forward host
    connections to it. We accept the request, re-issue it on the
    loopback, and copy the response back verbatim.
    """

    def __init__(self, *, listen_host: str, listen_port: int) -> None:
        self._listen_host = listen_host
        self._listen_port = listen_port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> "_UiProxy":
        self._server = ThreadingHTTPServer(
            (self._listen_host, self._listen_port), _UiProxyHandler
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()


class _UiProxyHandler(BaseHTTPRequestHandler):
    """Per-request UI proxy handler.

    Re-uses the underlying connection where possible (HTTP/1.1
    keep-alive) so the graph UI's many small asset requests don't pay
    the TCP setup cost on each one.
    """

    _UPSTREAM_HOST = "127.0.0.1"

    def log_message(self, format, *args):
        pass

    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler API
        self._proxy()

    def do_POST(self) -> None:  # noqa: N802
        self._proxy()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._proxy()

    def do_HEAD(self) -> None:  # noqa: N802
        self._proxy()

    def _proxy(self) -> None:
        upstream_port = int(os.environ.get("CBM_UI_UPSTREAM_PORT", str(UI_UPSTREAM_PORT)))
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""

        forward_headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in ("host", "connection", "content-length")
        }
        forward_headers["Host"] = f"127.0.0.1:{upstream_port}"
        forward_headers["Connection"] = "close"
        if body:
            forward_headers["Content-Length"] = str(len(body))

        try:
            with socket.create_connection(
                (self._UPSTREAM_HOST, upstream_port), timeout=10
            ) as upstream:
                upstream.sendall(
                    f"{self.command} {self.path} HTTP/1.1\r\n".encode("ascii")
                )
                for k, v in forward_headers.items():
                    upstream.sendall(f"{k}: {v}\r\n".encode("ascii"))
                upstream.sendall(b"\r\n")
                if body:
                    upstream.sendall(body)
                response = b""
                while True:
                    chunk = upstream.recv(65536)
                    if not chunk:
                        break
                    response += chunk
        except OSError as exc:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            err_body = json.dumps({"error": f"UI upstream unavailable: {exc}"}).encode("utf-8")
            self.send_header("Content-Length", str(len(err_body)))
            self.end_headers()
            self.wfile.write(err_body)
            return

        head, _, payload = response.partition(b"\r\n\r\n")
        status_line, *header_lines = head.split(b"\r\n") if head else [b"HTTP/1.1 200 OK"]
        try:
            _version, code, _reason = status_line.split(b" ", 2)
        except ValueError:
            _version, code, _reason = b"HTTP/1.1", b"200", b"OK"
        try:
            self.send_response(int(code))
        except ValueError:
            self.send_response(502)
        saw_content_length = False
        for line in header_lines:
            if b":" not in line:
                continue
            name, _, value = line.partition(b":")
            key = name.strip().lower()
            if key in (b"transfer-encoding", b"connection", b"content-length"):
                if key == b"content-length":
                    saw_content_length = True
                continue
            self.send_header(name.strip().decode("latin-1"), value.strip().decode("latin-1"))
        self.send_header("Connection", "close")
        if not saw_content_length and payload:
            self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD" and payload:
            self.wfile.write(payload)


if __name__ == "__main__":
    main()
