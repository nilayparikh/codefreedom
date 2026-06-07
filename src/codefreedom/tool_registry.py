"""Tool registry — reference-counted lifecycle for profile-declared Docker tools.

Manages ``~/.codefreedom/proc/`` with two subdirectories:

* ``proc/sessions/<session-id>.json`` — per-session tracking
* ``proc/tools/<tool>.json`` — per-tool locks with ref_count

First session to need a tool starts its Docker container.  Last session to exit
stops it.  Stale sessions (dead PIDs from crashes/reboots) are cleaned on startup
but **containers are never stopped during cleanup** — they are adopted by the
next session that needs them.
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any, Callable

from codefreedom.config import get_codefreedom_dir
from codefreedom.env_loader import eprint

# ── Tool handler dispatch ─────────────────────────────────────────────────────
# Each tool maps to (load_settings, start, stop) — existing functions from
# the tool CLI modules that accept/return the same signatures.

from codefreedom.cli.chrome import (  # noqa: E402
    _load_profile as chrome_load_profile,
    start as chrome_start,
    stop as chrome_stop,
)
from codefreedom.cli.web import (  # noqa: E402
    _load_profile as web_load_profile,
    start as web_start,
    stop as web_stop,
)
from codefreedom.cli.github import (  # noqa: E402
    _load_profile as github_load_profile,
    start as github_start,
    stop as github_stop,
)

_KNOWN_TOOLS: dict[
    str, tuple[Callable[[], dict], Callable[[dict], int], Callable[[dict], int]]
] = {
    "chrome": (chrome_load_profile, chrome_start, chrome_stop),
    "web": (web_load_profile, web_start, web_stop),
    "github": (github_load_profile, github_start, github_stop),
}

# ── Session / lock paths ──────────────────────────────────────────────────────

_CODEFREEDOM_DIR: Path = get_codefreedom_dir()
_PROC_DIR: Path = _CODEFREEDOM_DIR / "proc"
_SESSIONS_DIR: Path = _PROC_DIR / "sessions"
_TOOLS_DIR: Path = _PROC_DIR / "tools"


def _ensure_proc_dirs() -> None:
    """Create proc directory tree if it does not exist."""
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    _TOOLS_DIR.mkdir(parents=True, exist_ok=True)


# ── Atomic file helpers ───────────────────────────────────────────────────────


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically via temp-file + rename (atomic on Linux)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    """Read a JSON file, returning None if missing or corrupt."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        eprint(f"[PROC] Warning: failed to read {path}: {exc}")
        return None


# ── Session ID generation ─────────────────────────────────────────────────────


def generate_session_id(mode: str) -> str:
    """Generate a unique session ID.

    Sandbox mode: ``codefreedom-XXXX`` (doubles as Docker container name).
    Local mode:   ``codefreedom-local-XXXX``.
    """
    suffix = secrets.token_hex(2)  # 4 hex chars
    if mode == "sandbox":
        return f"codefreedom-{suffix}"
    return f"codefreedom-local-{suffix}"


# ── Stale session cleanup ─────────────────────────────────────────────────────


def cleanup_stale_sessions() -> None:
    """Remove session files for dead PIDs and decrement tool ref_counts.

    **Never stops Docker containers.**  Stale tools are simply un-tracked;
    the next session that needs them will adopt the running container.
    """
    if not _SESSIONS_DIR.exists():
        return

    for session_file in sorted(_SESSIONS_DIR.glob("*.json")):
        data = _read_json(session_file)
        if data is None:
            # Corrupt file — remove it
            _safe_remove(session_file)
            continue

        pid = data.get("pid")
        if pid is None or not _pid_alive(pid):
            eprint(
                f"[PROC] Cleaning stale session: {data.get('session_id', session_file.stem)}"
            )
            # Release tool references (without stopping containers)
            for tool_name in data.get("tools", []):
                _decrement_tool_ref(tool_name, data.get("session_id", ""))
            _safe_remove(session_file)


def _pid_alive(pid: int) -> bool:
    """Check if a process with *pid* is still running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _safe_remove(path: Path) -> None:
    """Remove a file, silently ignoring errors."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _decrement_tool_ref(tool_name: str, session_id: str) -> None:
    """Decrement ref_count for a tool, removing lock if it reaches zero.

    Does NOT stop the container — only adjusts /proc state.
    """
    lock_path = _TOOLS_DIR / f"{tool_name}.json"
    lock = _read_json(lock_path)
    if lock is None:
        return

    sessions: dict[str, bool] = lock.get("sessions", {})
    sessions.pop(session_id, None)
    new_ref = max(0, len(sessions))

    if new_ref == 0:
        _safe_remove(lock_path)
        eprint(f"[PROC] Tool lock removed (ref_count=0): {tool_name}")
    else:
        lock["ref_count"] = new_ref
        lock["sessions"] = sessions
        _atomic_write(lock_path, lock)


# ── Acquire / Release ─────────────────────────────────────────────────────────


def acquire_tools(session_id: str, tools: list[str], profile: str) -> list[str]:
    """Ensure each requested tool's Docker container is running and track it.

    Returns the list of tools that were **successfully** acquired.  Tools that
    fail to start (uninitialized, Docker missing, etc.) are warned and skipped
    — Claude still launches without them.
    """
    _ensure_proc_dirs()
    cleanup_stale_sessions()

    acquired: list[str] = []

    for tool_name in tools:
        if tool_name not in _KNOWN_TOOLS:
            eprint(f"[PROC] Unknown tool '{tool_name}' -- skipping.")
            continue

        _load_settings, _start, _stop = _KNOWN_TOOLS[tool_name]

        try:
            settings = _load_settings()
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            eprint(f"[PROC] Failed to load settings for '{tool_name}': {exc}")
            continue

        # Try to start the tool (no-op if already running)
        result = _start(settings)
        if result != 0:
            eprint(
                f"[PROC] Tool '{tool_name}' failed to start (exit {result}) — skipping."
            )
            continue

        # Register in lock file
        lock_path = _TOOLS_DIR / f"{tool_name}.json"
        lock = _read_json(lock_path)

        if lock is None:
            lock = {
                "tool": tool_name,
                "container_name": settings.get("container_name", ""),
                "ref_count": 1,
                "sessions": {session_id: True},
            }
        else:
            lock["ref_count"] = lock.get("ref_count", 0) + 1
            lock.setdefault("sessions", {})[session_id] = True

        _atomic_write(lock_path, lock)
        acquired.append(tool_name)
        eprint(f"[PROC] Tool '{tool_name}' acquired (ref_count={lock['ref_count']}).")

    # Write session file
    session_data: dict[str, Any] = {
        "session_id": session_id,
        "profile": profile,
        "tools": acquired,
        "pid": os.getpid(),
        "started_at": _now_iso(),
    }
    _atomic_write(_SESSIONS_DIR / f"{session_id}.json", session_data)

    return acquired


def release_tools(session_id: str, tools: list[str]) -> None:
    """Release tool references for a session.

    When a tool's ref_count reaches zero, the Docker container is stopped.
    """
    for tool_name in tools:
        if tool_name not in _KNOWN_TOOLS:
            continue

        _load_settings, _start, _stop = _KNOWN_TOOLS[tool_name]

        lock_path = _TOOLS_DIR / f"{tool_name}.json"
        lock = _read_json(lock_path)
        if lock is None:
            continue

        sessions: dict[str, bool] = lock.get("sessions", {})
        sessions.pop(session_id, None)
        new_ref = len(sessions)

        if new_ref == 0:
            # Last session — stop the container
            try:
                settings = _load_settings()
            except (FileNotFoundError, json.JSONDecodeError):
                settings = {}
            _stop(settings)
            _safe_remove(lock_path)
            eprint(f"[PROC] Tool '{tool_name}' stopped (last session).")
        else:
            lock["ref_count"] = new_ref
            lock["sessions"] = sessions
            _atomic_write(lock_path, lock)
            eprint(f"[PROC] Tool '{tool_name}' released (ref_count={new_ref}).")

    # Remove session file
    session_path = _SESSIONS_DIR / f"{session_id}.json"
    _safe_remove(session_path)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


# ── MCP endpoint resolution ───────────────────────────────────────────────────

_TOOL_MCP_SERVER_NAMES: dict[str, str] = {
    "chrome": "chrome-devtools",
    "web": "web",
    "github": "github",
}


def _github_mapped_port(container_name: str) -> int | None:
    """Return host port mapped to container 8082, or None."""
    import subprocess

    result = subprocess.run(
        ["docker", "port", container_name, "8082"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        line = result.stdout.strip().split("\n")[0]
        if ":" in line:
            return int(line.rsplit(":", 1)[-1])
    return None


def load_tool_mcp_endpoints(acquired_tools: list[str]) -> dict:
    """Build MCP server entries for acquired tools.

    Reads each tool's profile to get the HTTP MCP endpoint URL and returns
    a dict suitable for writing as a project ``.mcp.json`` file.

    Returns a dict with a ``mcpServers`` key (even when empty):
    ``{"mcpServers": {"chrome-devtools": {"type": "http", "url": "..."}}}``
    """
    servers: dict[str, dict] = {}

    for tool_name in acquired_tools:
        if tool_name not in _KNOWN_TOOLS:
            continue

        load_settings, _start, _stop = _KNOWN_TOOLS[tool_name]
        try:
            settings = load_settings()
        except FileNotFoundError:
            eprint(
                f"[MCP] Tool '{tool_name}' profile not found —"
                " run 'codefreedom tools {tool_name} init' first."
            )
            continue
        except json.JSONDecodeError as exc:
            eprint(f"[MCP] Tool '{tool_name}' profile is malformed — {exc}.")
            continue

        server_name = _TOOL_MCP_SERVER_NAMES.get(tool_name, tool_name)

        if tool_name == "chrome":
            port = settings.get("mcp_port", 9223)
            path = settings.get("mcp_path", "/mcp")
        elif tool_name == "web":
            port = settings.get("port", 8420)
            path = settings.get("mcp_path", "/mcp")
        elif tool_name == "github":
            port = settings.get("port", 0)
            container = settings.get("container_name", "codefreedom-tools-github")
            if port == 0:
                # Resolve actual mapped port from running container
                port = _github_mapped_port(container) or 8082
            path = "/mcp"
        else:
            eprint(
                f"[MCP] Tool '{tool_name}' has no MCP endpoint mapping —"
                " update _TOOL_MCP_SERVER_NAMES and add a branch here."
            )
            continue

        # Normalize: ensure path starts with "/" for a valid URL.
        if not path.startswith("/"):
            path = "/" + path

        url = f"http://127.0.0.1:{port}{path}"
        servers[server_name] = {"type": "http", "url": url}

    return {"mcpServers": servers}
