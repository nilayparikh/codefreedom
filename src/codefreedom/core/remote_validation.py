"""Remote endpoint validation helpers for proxy and MCP tools."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from codefreedom.core.agent_runtime import (
    PROXY_AUTH_REQUIRED,
    PROXY_OK,
    PROXY_UNREACHABLE,
    fetch_proxy_models_with_status,
)

__all__ = [
    "RemoteValidationError",
    "PROXY_OK",
    "PROXY_AUTH_REQUIRED",
    "PROXY_UNREACHABLE",
    "probe_remote_proxy",
    "validate_remote_proxy_url",
    "probe_remote_tool",
    "validate_remote_tool_url",
    "validate_remote_tools_or_raise",
]


class RemoteValidationError(Exception):
    """Raised when a configured remote endpoint is unreachable or invalid."""


def probe_remote_proxy(url: str, api_key: str = "") -> str:
    """Probe a remote LiteLLM proxy and report its reachability/auth state.

    Returns one of :data:`PROXY_OK` (reachable, authenticated, has models),
    :data:`PROXY_AUTH_REQUIRED` (endpoint responded 401/403), or
    :data:`PROXY_UNREACHABLE` (network error, non-JSON, other HTTP status).
    Delegates to :func:`fetch_proxy_models_with_status` so the proxy model
    fetch stays a single source of truth.
    """
    _models, status = fetch_proxy_models_with_status(url, api_key)
    return status


def validate_remote_proxy_url(url: str, api_key: str = "") -> bool:
    return probe_remote_proxy(url, api_key) == PROXY_OK


def _parse_sse_data(body: str) -> dict | None:
    """Extract and parse the JSON payload from an SSE ``text/event-stream`` body.

    SSE frames look like::

        event: message
        id: <id>
        data: {"jsonrpc":"2.0",...}

    Multiple ``data:`` lines are concatenated per the SSE spec. Returns the
    parsed JSON dict, or ``None`` if no ``data:`` line is found or JSON
    parsing fails.
    """
    data_lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("data: "):
            data_lines.append(line[len("data: "):])
        elif line.startswith("data:"):
            data_lines.append(line[len("data:"):])
    if not data_lines:
        return None
    try:
        return json.loads("".join(data_lines))
    except json.JSONDecodeError:
        return None


def _parse_mcp_response(resp_body: bytes) -> dict | None:
    """Parse an MCP response body (SSE or plain JSON)."""
    text = resp_body.decode("utf-8", errors="replace")
    parsed = _parse_sse_data(text)
    if parsed is not None:
        return parsed
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _mcp_post(
    url: str, payload: dict, session_id: str = "", timeout: int = 5
) -> tuple[dict | None, dict[str, str]]:
    """POST a JSON-RPC request to an MCP endpoint and return (parsed_body, headers).

    Uses a no-proxy opener so localhost / port-forwarded endpoints are never
    routed through a system proxy (a common Windows issue where ``urllib``
    inherits IE/Edge proxy settings from the registry).
    """
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **({"Mcp-Session-Id": session_id} if session_id else {}),
        },
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            body = _parse_mcp_response(resp.read())
            return body, headers
    except urllib.error.HTTPError as exc:
        return _parse_mcp_response(exc.read() or b""), {}
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, {}


def validate_remote_tool_url(_tool: str, url: str) -> list[str]:
    """Probe a remote MCP endpoint and return tool/method names.

    Returns a list of tool names. An empty list means the endpoint is
    unreachable, returned an error, or has no tools.
    """
    methods, _error = probe_remote_tool(url)
    return methods


def probe_remote_tool(url: str) -> tuple[list[str], str]:
    """Probe a remote MCP endpoint and return ``(methods, error)``.

    On success *error* is an empty string. On failure *methods* is empty and
    *error* describes what went wrong (useful for user-facing diagnostics).
    """
    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "codefreedom", "version": "1.0"},
        },
    }
    body, headers = _mcp_post(url, init_payload)
    if body is None:
        return [], "initialize: endpoint unreachable (connection refused or timeout)"
    if not isinstance(body, dict):
        return [], "initialize: non-JSON response"
    if "error" in body:
        err = body.get("error", {})
        return [], f"initialize: server error {err.get('code', '?')}: {err.get('message', '?')}"
    if "result" not in body:
        return [], "initialize: no result in response"

    session_id = headers.get("mcp-session-id", "")

    list_payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }
    body, _headers = _mcp_post(url, list_payload, session_id=session_id)
    if body is None:
        return [], "tools/list: endpoint unreachable"
    if not isinstance(body, dict):
        return [], "tools/list: non-JSON response"
    if "error" in body:
        err = body.get("error", {})
        return [], f"tools/list: server error {err.get('code', '?')}: {err.get('message', '?')}"
    if "result" not in body:
        return [], "tools/list: no result in response"

    tools = body.get("result", {}).get("tools", [])
    if not isinstance(tools, list):
        return [], "tools/list: tools field is not a list"
    methods = [str(t.get("name", "?")) for t in tools if isinstance(t, dict)]
    if not methods:
        return [], "tools/list: server returned 0 tools"
    return methods, ""


def validate_remote_tools_or_raise(acquired_tools: list[str]) -> None:
    from codefreedom.tools.registry import load_tool_mcp_endpoints

    endpoints = load_tool_mcp_endpoints(acquired_tools).get("mcpServers", {})
    for server in endpoints.values():
        url = server.get("url")
        if not url:
            continue
        if not validate_remote_tool_url("tool", str(url)):
            raise RemoteValidationError(f"Remote MCP endpoint is unavailable: {url}")
