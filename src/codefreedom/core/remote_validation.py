"""Remote endpoint validation helpers for proxy and MCP tools."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from codefreedom.core.agent_runtime import fetch_proxy_models


class RemoteValidationError(Exception):
    """Raised when a configured remote endpoint is unreachable or invalid."""


def validate_remote_proxy_url(url: str) -> bool:
    models = fetch_proxy_models(url)
    return bool(models)


def validate_remote_tool_url(_tool: str, url: str) -> bool:
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
            return isinstance(body, dict) and "result" in body
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return False


def validate_remote_tools_or_raise(acquired_tools: list[str]) -> None:
    from codefreedom.tools.registry import load_tool_mcp_endpoints

    endpoints = load_tool_mcp_endpoints(acquired_tools).get("mcpServers", {})
    for server in endpoints.values():
        url = server.get("url")
        if not url:
            continue
        if not validate_remote_tool_url("tool", str(url)):
            raise RemoteValidationError(f"Remote MCP endpoint is unavailable: {url}")
