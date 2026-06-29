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


def validate_remote_tool_url(_tool: str, url: str) -> list[str]:
    """Probe a remote MCP endpoint via ``tools/list`` and return method names.

    Returns a list of tool/method names from the JSON-RPC ``result.tools``
    array. An empty list means the endpoint is unreachable, returned an
    error, or has no tools — callers treat empty as failure (``if not ...``).
    """
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if not isinstance(body, dict) or "result" not in body:
                return []
            tools = body.get("result", {}).get("tools", [])
            if not isinstance(tools, list):
                return []
            return [str(t.get("name", "?")) for t in tools if isinstance(t, dict)]
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return []


def validate_remote_tools_or_raise(acquired_tools: list[str]) -> None:
    from codefreedom.tools.registry import load_tool_mcp_endpoints

    endpoints = load_tool_mcp_endpoints(acquired_tools).get("mcpServers", {})
    for server in endpoints.values():
        url = server.get("url")
        if not url:
            continue
        if not validate_remote_tool_url("tool", str(url)):
            raise RemoteValidationError(f"Remote MCP endpoint is unavailable: {url}")
