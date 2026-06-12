"""Tool registry — shared, persistent Docker tools.

All tools (chrome, web, github, web-bridge) and the proxy use
**deterministic container names** from their config.  Docker is the
single source of truth for state — no /proc tracking needed.
"""

from __future__ import annotations

import json
import secrets
from typing import Callable

from codefreedom.log import eprint

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
from codefreedom.cli.web_bridge import (  # noqa: E402
    _load_profile as web_bridge_load_profile,
    start as web_bridge_start,
    stop as web_bridge_stop,
)

_KNOWN_TOOLS: dict[
    str, tuple[Callable[[], dict], Callable[[dict], int], Callable[[dict], int]]
] = {
    "chrome": (chrome_load_profile, chrome_start, chrome_stop),
    "web": (web_load_profile, web_start, web_stop),
    "github": (github_load_profile, github_start, github_stop),
    "web-bridge": (web_bridge_load_profile, web_bridge_start, web_bridge_stop),
}

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


# ── Acquire / Release ─────────────────────────────────────────────────────────


def acquire_tools(_session_id: str, tools: list[str], _profile: str) -> list[str]:
    """Ensure each requested tool's Docker container is running.

    Tools use static container names from their profile and check Docker
    directly for real state — no /proc tracking.  Returns the list of
    successfully started tools.
    """
    acquired: list[str] = []

    for tool_name in tools:
        if tool_name not in _KNOWN_TOOLS:
            eprint(f"[TOOLS] Unknown tool '{tool_name}' -- skipping.")
            continue

        _load_settings, _start, _ = _KNOWN_TOOLS[tool_name]

        try:
            settings = _load_settings()
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            eprint(f"[TOOLS] Failed to load settings for '{tool_name}': {exc}")
            continue

        result = _start(settings)
        if result != 0:
            eprint(
                f"[TOOLS] Tool '{tool_name}' failed to start (exit {result}) — skipping."
            )
            continue

        acquired.append(tool_name)
        eprint(f"[TOOLS] Tool '{tool_name}' acquired.")

    return acquired


def release_tools(_session_id: str, _tools: list[str]) -> None:
    """Release tools — no-op.  Tools persist until explicitly stopped."""


# ── MCP endpoint resolution ───────────────────────────────────────────────────

_TOOL_MCP_SERVER_NAMES: dict[str, str] = {
    "chrome": "chrome-devtools",
    "web": "web",
    "github": "github",
    "web-bridge": "web-bridge",
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

    Reads each tool's profile to get the HTTP MCP endpoint URL — no /proc
    needed since tools use static container names.  Returns a dict with
    a ``mcpServers`` key (even when empty).
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
        container_name = settings.get("container_name", f"codefreedom-{tool_name}")

        if tool_name == "chrome":
            port = settings.get("mcp_port", 9223)
            path = settings.get("mcp_path", "/mcp")
        elif tool_name == "web":
            port = settings.get("port", 8420)
            path = settings.get("mcp_path", "/mcp")
        elif tool_name == "github":
            port = settings.get("port", 0)
            if port == 0:
                port = _github_mapped_port(container_name) or 8082
            path = "/mcp"
        elif tool_name == "web-bridge":
            port = settings.get("port", 8500)
            path = "/search"
        else:
            eprint(
                f"[MCP] Tool '{tool_name}' has no MCP endpoint mapping —"
                " update _TOOL_MCP_SERVER_NAMES and add a branch here."
            )
            continue

        if not path.startswith("/"):
            path = "/" + path

        url = f"http://127.0.0.1:{port}{path}"
        servers[server_name] = {"type": "http", "url": url}

    return {"mcpServers": servers}
