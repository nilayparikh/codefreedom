"""Tests for load_tool_mcp_endpoints in tool_registry.py."""

import os
from pathlib import Path

import yaml

from codefreedom.config import get_codefreedom_dir
from codefreedom.tool_registry import load_tool_mcp_endpoints


def _tool_home() -> Path:
    """Return the tool home directory (set by conftest.py or default)."""
    override = os.environ.get("CODEFREEDOM_TOOL_HOME")
    if override:
        return Path(override)
    return get_codefreedom_dir()


def _write_tool_profile(tool, data):
    """Write a tool profile YAML to the tool home test dir.

    Tool profiles live under ``CODEFREEDOM_TOOL_HOME`` (set by
    conftest.py to the same session-scoped temp directory).
    """
    profiles = _tool_home() / "profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    with open(profiles / f"{tool}.yaml", "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


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

    def test_github_with_defaults(self, monkeypatch):
        """GitHub returns HTTP endpoint (port=8082 fallback, /mcp) when profile missing and no container running."""
        monkeypatch.setattr(
            "codefreedom.tool_registry._github_mapped_port",
            lambda _: None,
        )
        endpoints = load_tool_mcp_endpoints(["github"])
        servers = endpoints["mcpServers"]
        assert servers == {
            "github": {
                "type": "http",
                "url": "http://127.0.0.1:8082/mcp",
            }
        }

    def test_github_with_custom_port(self, monkeypatch):
        """GitHub reads port from profile."""
        _write_tool_profile(
            "github",
            {
                "github": {
                    "image": "codefreedom:github",
                    "container_name": "codefreedom-github",
                    "port": 9090,
                    "data_dir": "~/sandbox/github",
                    "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "test"},
                }
            },
        )

        endpoints = load_tool_mcp_endpoints(["github"])
        assert endpoints["mcpServers"]["github"]["url"] == ("http://127.0.0.1:9090/mcp")

    def test_all_tools_merged(self, monkeypatch):
        """Chrome, Web, and GitHub MCP all produce distinct entries."""
        monkeypatch.setattr(
            "codefreedom.tool_registry._github_mapped_port",
            lambda _: None,
        )
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
        _write_tool_profile(
            "github",
            {
                "github": {
                    "image": "ghcr.io/github/github-mcp-server",
                    "container_name": "codefreedom-github",
                    "port": 8082,
                    "data_dir": "~/sandbox/github",
                    "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "test"},
                }
            },
        )

        endpoints = load_tool_mcp_endpoints(["chrome", "web", "github"])
        servers = endpoints["mcpServers"]
        assert len(servers) == 3
        assert servers["chrome-devtools"]["url"] == "http://127.0.0.1:9223/mcp"
        assert servers["web"]["url"] == "http://127.0.0.1:8420/mcp"
        assert servers["github"]["url"] == "http://127.0.0.1:8082/mcp"

    def test_empty_list_returns_no_servers(self):
        """Empty acquired list returns mcpServers: {}."""
        endpoints = load_tool_mcp_endpoints([])
        assert endpoints == {"mcpServers": {}}
