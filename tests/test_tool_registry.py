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


class TestCodebaseMemoryToolMcpEndpoint:
    def test_defaults_when_no_profile(self, monkeypatch, tmp_path):
        """No git repo around: defaults to 8330."""
        from codefreedom.tools.codebase_memory import CodebaseMemoryTool

        monkeypatch.chdir(tmp_path)  # not a git repo
        tool = CodebaseMemoryTool()
        assert tool.mcp_server_name == "codebase-memory"
        port, path = tool.mcp_endpoint
        assert port == 8330
        assert path == "/mcp"

    def test_custom_port_from_manifest(self, monkeypatch, tmp_path):
        """The endpoint reads ``mcp_port`` from the per-project manifest.

        Set up a git repo in ``tmp_path``, write a manifest with port
        9753, and verify the tool reports that port.
        """
        import subprocess

        from codefreedom.tools.codebase_memory import CodebaseMemoryTool

        # Make tmp_path a git repo so ``git rev-parse --show-toplevel`` works.
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        (tmp_path / "README.md").write_text("test")
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "init"], check=True)

        monkeypatch.chdir(tmp_path)

        # Write a manifest with a non-default port.
        from codebase_memory import manifest as _manifest
        data = _manifest.init_defaults(tmp_path)
        data["mcp_port"] = 9753
        data["ui_port"] = 9753 + 1419
        data["container_name"] = "codefreedom-tools-codebase-memory-test"
        _manifest.save(tmp_path, data)

        tool = CodebaseMemoryTool()
        port, path = tool.mcp_endpoint
        assert port == 9753
        assert path == "/mcp"

    def test_remote_url_falls_back_to_default_port(self, monkeypatch, tmp_path):
        """When ``remote_url`` is set, the tool class returns the default
        port (the actual URL is opaque to the registry).
        """
        import subprocess

        from codefreedom.tools.codebase_memory import CodebaseMemoryTool

        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        (tmp_path / "README.md").write_text("test")
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "init"], check=True)

        monkeypatch.chdir(tmp_path)

        from codebase_memory import manifest as _manifest
        data = _manifest.init_defaults(tmp_path)
        data["remote_url"] = "https://remote.example/mcp"
        data["mcp_port"] = 9753
        _manifest.save(tmp_path, data)

        tool = CodebaseMemoryTool()
        port, path = tool.mcp_endpoint
        # remote_url path returns the default; the agent uses remote_url directly.
        assert port == 8330
        assert path == "/mcp"

    def test_manifest_fallback_without_git(self, monkeypatch, tmp_path):
        """When git resolution fails but a manifest exists, the tool
        reads ``mcp_port`` from the manifest via the filesystem fallback.
        """
        from codefreedom.tools.codebase_memory import CodebaseMemoryTool

        # No git init — just create a manifest directly.
        from codebase_memory import manifest as _manifest
        data = _manifest.init_defaults(tmp_path)
        data["mcp_port"] = 8441
        data["ui_port"] = 9860
        data["container_name"] = "test-cbm"
        _manifest.save(tmp_path, data)

        monkeypatch.chdir(tmp_path)

        tool = CodebaseMemoryTool()
        port, path = tool.mcp_endpoint
        assert port == 8441
        assert path == "/mcp"

    def test_bare_repo_reads_manifest_port(self, monkeypatch, tmp_path):
        """A repo with ``core.bare=true`` should still resolve and read
        the manifest's ``mcp_port``.
        """
        import subprocess

        from codefreedom.tools.codebase_memory import CodebaseMemoryTool

        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        (tmp_path / "README.md").write_text("test")
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "init"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "core.bare", "true"], check=True)

        monkeypatch.chdir(tmp_path)

        from codebase_memory import manifest as _manifest
        data = _manifest.init_defaults(tmp_path)
        data["mcp_port"] = 8442
        data["ui_port"] = 9861
        data["container_name"] = "test-cbm-bare"
        _manifest.save(tmp_path, data)

        tool = CodebaseMemoryTool()
        port, path = tool.mcp_endpoint
        assert port == 8442
        assert path == "/mcp"


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
        endpoints = load_tool_mcp_endpoints(["chrome", "web", "github", "web-bridge", "codebase-memory"])
        servers = endpoints["mcpServers"]
        assert len(servers) == 5
        assert servers["chrome-devtools"]["url"] == "http://127.0.0.1:9223/mcp"
        assert servers["web"]["url"] == "http://127.0.0.1:8420/mcp"
        assert servers["github"]["url"] == "http://127.0.0.1:8082/mcp"
        assert servers["web-bridge"]["url"] == "http://127.0.0.1:8500/search"
        assert servers["codebase-memory"]["url"] == "http://127.0.0.1:8330/mcp"

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


class TestAcquireToolsRemoteUrl:
    """When remote_url is set, acquire_tools must skip local container start."""

    def test_remote_url_skips_docker_start(self, monkeypatch):
        from codefreedom.tools import registry
        from codefreedom.tools.registry import acquire_tools

        def fake_load_profile():
            return {
                "image": "img",
                "container_name": "test-chrome",
                "port": 9222,
                "remote_url": "http://remote.local:9223/mcp",
                "env": {},
            }

        start_calls: list = []

        def fake_start(settings):
            start_calls.append(settings)
            return 0

        monkeypatch.setitem(
            registry._KNOWN_TOOLS, "chrome", (fake_load_profile, fake_start, lambda s: 0)
        )

        acquired = acquire_tools("session-1", ["chrome"], "default")
        assert acquired == ["chrome"]
        assert start_calls == [], "start() must not be called when remote_url is set"

    def test_no_remote_url_starts_docker(self, monkeypatch):
        from codefreedom.tools import registry
        from codefreedom.tools.registry import acquire_tools

        def fake_load_profile():
            return {
                "image": "img",
                "container_name": "test-chrome",
                "port": 9222,
                "remote_url": "",
                "env": {},
            }

        start_calls: list = []

        def fake_start(settings):
            start_calls.append(settings)
            return 0

        monkeypatch.setitem(
            registry._KNOWN_TOOLS, "chrome", (fake_load_profile, fake_start, lambda s: 0)
        )

        acquired = acquire_tools("session-1", ["chrome"], "default")
        assert acquired == ["chrome"]
        assert len(start_calls) == 1, "start() must be called when no remote_url"


pytestmark = pytest.mark.integration
