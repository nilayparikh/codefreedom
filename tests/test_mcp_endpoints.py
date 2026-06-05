"""Tests for load_tool_mcp_endpoints in tool_registry.py."""

import json

from codefreedom.config import get_codefreedom_dir
from codefreedom.tool_registry import load_tool_mcp_endpoints


def _write_tool_profile(tool, data):
    """Write a tool profile JSON to the active codefreedom test dir.

    Uses ``get_codefreedom_dir()`` which returns the session-scoped
    temp directory set by ``conftest.py``.  Never monkeypatch
    ``CODEFREEDOM_HOME`` — the module-level ``_CODEFREEDOM_DIR`` in
    chrome.py / web.py is evaluated at import time.
    """
    cf_dir = get_codefreedom_dir()
    profiles = cf_dir / "profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    (profiles / f"{tool}.json").write_text(json.dumps(data))


class TestLoadToolMcpEndpoints:
    """Tests for load_tool_mcp_endpoints() across acquired tools."""

    def test_chrome_with_defaults(self):
        """Chrome returns defaults (mcp_port=9223, mcp_path=/mcp) when profile is missing."""
        endpoints = load_tool_mcp_endpoints(["chrome"])
        servers = endpoints["mcpServers"]
        assert servers == {
            "chrome-devtools": {
                "type": "http",
                "url": "http://127.0.0.1:9223/mcp",
            }
        }

    def test_web_with_defaults(self):
        """Web returns defaults (port=8420, mcp_path=/mcp) when profile is missing."""
        endpoints = load_tool_mcp_endpoints(["web"])
        servers = endpoints["mcpServers"]
        assert servers == {
            "web": {
                "type": "http",
                "url": "http://127.0.0.1:8420/mcp",
            }
        }

    def test_chrome_with_custom_mcp_port_and_path(self):
        """Chrome reads mcp_port and mcp_path from profile."""
        _write_tool_profile(
            "chrome",
            {
                "chrome": {
                    "image": "codefreedom:chrome",
                    "container_name": "codefreedom-chrome",
                    "port": 9222,
                    "mcp_port": 9100,
                    "mcp_path": "/devtools",
                    "data_dir": "~/sandbox/chrome",
                    "env": {},
                }
            },
        )

        endpoints = load_tool_mcp_endpoints(["chrome"])
        assert endpoints["mcpServers"]["chrome-devtools"]["url"] == (
            "http://127.0.0.1:9100/devtools"
        )

    def test_web_with_custom_mcp_path(self):
        """Web reads mcp_path from profile; port comes from the standard 'port' field."""
        _write_tool_profile(
            "web",
            {
                "web": {
                    "image": "codefreedom:web",
                    "container_name": "codefreedom-web",
                    "port": 8500,
                    "mcp_path": "/search-mcp",
                    "data_dir": "~/sandbox/web",
                    "env": {},
                }
            },
        )

        endpoints = load_tool_mcp_endpoints(["web"])
        assert endpoints["mcpServers"]["web"]["url"] == (
            "http://127.0.0.1:8500/search-mcp"
        )

    def test_both_tools_merged(self):
        """Both Chrome and Web produce distinct entries."""
        _write_tool_profile(
            "chrome",
            {
                "chrome": {
                    "image": "codefreedom:chrome",
                    "container_name": "codefreedom-chrome",
                    "port": 9222,
                    "mcp_port": 9223,
                    "mcp_path": "/mcp",
                    "data_dir": "~/sandbox/chrome",
                    "env": {},
                }
            },
        )
        _write_tool_profile(
            "web",
            {
                "web": {
                    "image": "codefreedom:web",
                    "container_name": "codefreedom-web",
                    "port": 8420,
                    "mcp_path": "/mcp",
                    "data_dir": "~/sandbox/web",
                    "env": {},
                }
            },
        )

        endpoints = load_tool_mcp_endpoints(["chrome", "web"])
        servers = endpoints["mcpServers"]
        assert len(servers) == 2
        assert servers["chrome-devtools"]["url"] == "http://127.0.0.1:9223/mcp"
        assert servers["web"]["url"] == "http://127.0.0.1:8420/mcp"

    def test_unknown_tool_skipped(self):
        """Unknown tool names are silently skipped."""
        endpoints = load_tool_mcp_endpoints(["unknown-tool", "chrome"])
        servers = endpoints["mcpServers"]
        assert len(servers) == 1
        assert "chrome-devtools" in servers

    def test_empty_list_returns_no_servers(self):
        """Empty acquired list returns mcpServers: {}."""
        endpoints = load_tool_mcp_endpoints([])
        assert endpoints == {"mcpServers": {}}
