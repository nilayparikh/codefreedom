"""Tool registry — shared, persistent Docker tools.

All tools (chrome, web, github, web-bridge) and the proxy use
**deterministic container names** from their config.  Docker is the
single source of truth for state — no /proc tracking needed.
"""

from __future__ import annotations

import json
import secrets
from typing import Callable, Protocol

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


# ── MCP tool classes (for endpoint resolution) ────────────────────────────────

class _McpTool(Protocol):
    @property
    def mcp_endpoint(self) -> tuple[int, str]: ...
    @property
    def mcp_server_name(self) -> str: ...


from codefreedom.cli.chrome import ChromeTool  # noqa: E402
from codefreedom.cli.web import WebTool  # noqa: E402
from codefreedom.cli.github import GithubTool  # noqa: E402
from codefreedom.cli.web_bridge import WebBridgeTool  # noqa: E402

_MCP_TOOLS: dict[str, _McpTool] = {
    "chrome": ChromeTool(),
    "web": WebTool(),
    "github": GithubTool(),
    "web-bridge": WebBridgeTool(),
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


def load_tool_mcp_endpoints(acquired_tools: list[str]) -> dict:
    """Build MCP server entries for acquired tools.

    Dispatches to each tool's class for its MCP endpoint spec — no
    hardcoded port/path knowledge lives here.
    """
    servers: dict[str, dict] = {}

    for tool_name in acquired_tools:
        if tool_name not in _MCP_TOOLS:
            continue

        tool = _MCP_TOOLS[tool_name]
        try:
            port, path = tool.mcp_endpoint
        except FileNotFoundError:
            eprint(
                f"[MCP] Tool '{tool_name}' profile not found —"
                " run 'codefreedom tools {tool_name} init' first."
            )
            continue
        except json.JSONDecodeError as exc:
            eprint(f"[MCP] Tool '{tool_name}' profile is malformed — {exc}.")
            continue

        if not path.startswith("/"):
            path = "/" + path

        url = f"http://127.0.0.1:{port}{path}"
        servers[tool.mcp_server_name] = {"type": "http", "url": url}

    return {"mcpServers": servers}
