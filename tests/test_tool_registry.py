"""Tests for tool registry MCP endpoint mapping via tool classes."""

import pytest

from tests.helpers import clean_profiles, write_tool_profile


class TestChromeToolMcpEndpoint:
    def test_defaults_when_no_profile(self):
        from codefreedom.tools.chrome import ChromeTool

        tool = ChromeTool()
        assert tool.mcp_server_name == "chrome-devtools"
        port, path = tool.mcp_endpoint
        assert port == 9223
        assert path == "/mcp"

    def test_custom_port_and_path_from_profile(self):
        from codefreedom.tools.chrome import ChromeTool

        write_tool_profile(
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
        tool = ChromeTool()
        port, path = tool.mcp_endpoint
        assert port == 9100
        assert path == "/devtools"


class TestWebToolMcpEndpoint:
    def test_defaults_when_no_profile(self):
        from codefreedom.tools.web import WebTool

        tool = WebTool()
        assert tool.mcp_server_name == "web"
        port, path = tool.mcp_endpoint
        assert port == 8420
        assert path == "/mcp"

    def test_custom_port_and_path_from_profile(self):
        from codefreedom.tools.web import WebTool

        write_tool_profile(
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
        tool = WebTool()
        port, path = tool.mcp_endpoint
        assert port == 8500
        assert path == "/search-mcp"


class TestGithubToolMcpEndpoint:

    @pytest.fixture(autouse=True)
    def _clean_profiles_fixture(self):
        clean_profiles()

    def test_defaults_when_no_profile(self, monkeypatch):
        from codefreedom.tools.github import GithubTool

        monkeypatch.setattr(
            "codefreedom.tools.github._get_mapped_port",
            lambda _: None,
        )
        tool = GithubTool()
        assert tool.mcp_server_name == "github"
        port, path = tool.mcp_endpoint
        assert port == 8082
        assert path == "/mcp"

    def test_custom_port_from_profile(self):
        from codefreedom.tools.github import GithubTool

        write_tool_profile(
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
        tool = GithubTool()
        port, path = tool.mcp_endpoint
        assert port == 9090
        assert path == "/mcp"


class TestWebBridgeToolMcpEndpoint:
    def test_defaults_when_no_profile(self):
        from codefreedom.tools.web_bridge import WebBridgeTool

        tool = WebBridgeTool()
        assert tool.mcp_server_name == "web-bridge"
        port, path = tool.mcp_endpoint
        assert port == 8500
        assert path == "/search"

    def test_custom_port_from_profile(self):
        from codefreedom.tools.web_bridge import WebBridgeTool

        write_tool_profile(
            "web-bridge",
            {
                "web-bridge": {
                    "image": "codefreedom:web-bridge",
                    "container_name": "codefreedom-web-bridge",
                    "port": 9999,
                    "data_dir": "~/sandbox/web-bridge",
                    "env": {},
                }
            },
        )
        tool = WebBridgeTool()
        port, path = tool.mcp_endpoint
        assert port == 9999
        assert path == "/search"





class TestToolRegistryMcpEndpointsDispatch:
    """Verify that load_tool_mcp_endpoints dispatches via tool classes (not if/elif)."""

    @pytest.fixture(autouse=True)
    def _clean_profiles_fixture(self):
        clean_profiles()

    def test_chrome_with_defaults(self):
        from codefreedom.tools.registry import load_tool_mcp_endpoints

        endpoints = load_tool_mcp_endpoints(["chrome"])
        servers = endpoints["mcpServers"]
        assert servers == {
            "chrome-devtools": {
                "type": "http",
                "url": "http://127.0.0.1:9223/mcp",
            },
        }

    def test_web_with_defaults(self):
        from codefreedom.tools.registry import load_tool_mcp_endpoints

        endpoints = load_tool_mcp_endpoints(["web"])
        servers = endpoints["mcpServers"]
        assert servers == {
            "web": {
                "type": "http",
                "url": "http://127.0.0.1:8420/mcp",
            },
        }

    def test_github_with_defaults(self, monkeypatch):
        from codefreedom.tools.registry import load_tool_mcp_endpoints

        monkeypatch.setattr(
            "codefreedom.tools.github._get_mapped_port",
            lambda _: None,
        )
        endpoints = load_tool_mcp_endpoints(["github"])
        servers = endpoints["mcpServers"]
        assert servers == {
            "github": {
                "type": "http",
                "url": "http://127.0.0.1:8082/mcp",
            },
        }

    def test_web_bridge_with_defaults(self):
        from codefreedom.tools.registry import load_tool_mcp_endpoints

        endpoints = load_tool_mcp_endpoints(["web-bridge"])
        servers = endpoints["mcpServers"]
        assert servers == {
            "web-bridge": {
                "type": "http",
                "url": "http://127.0.0.1:8500/search",
            },
        }

    def test_all_tools_merged(self):
        from codefreedom.tools.registry import load_tool_mcp_endpoints

        write_tool_profile(
            "github",
            {
                "github": {
                    "image": "codefreedom:github",
                    "container_name": "codefreedom-github",
                    "port": 8082,
                    "data_dir": "~/sandbox/github",
                    "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "test"},
                }
            },
        )
        endpoints = load_tool_mcp_endpoints(["chrome", "web", "github", "web-bridge"])
        servers = endpoints["mcpServers"]
        assert len(servers) == 4
        assert servers["chrome-devtools"]["url"] == "http://127.0.0.1:9223/mcp"
        assert servers["web"]["url"] == "http://127.0.0.1:8420/mcp"
        assert servers["github"]["url"] == "http://127.0.0.1:8082/mcp"
        assert servers["web-bridge"]["url"] == "http://127.0.0.1:8500/search"

    def test_unknown_tool_skipped(self):
        from codefreedom.tools.registry import load_tool_mcp_endpoints

        endpoints = load_tool_mcp_endpoints(["unknown-tool", "chrome"])
        servers = endpoints["mcpServers"]
        assert len(servers) == 1
        assert "chrome-devtools" in servers

    def test_empty_list_returns_no_servers(self):
        from codefreedom.tools.registry import load_tool_mcp_endpoints

        endpoints = load_tool_mcp_endpoints([])
        assert endpoints == {"mcpServers": {}}

pytestmark = pytest.mark.integration
