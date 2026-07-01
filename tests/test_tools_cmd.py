from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from codefreedom.cli.main import _add_subparser, _build_tools_args
from codefreedom.cli.run import tools

pytestmark = pytest.mark.unit


class TestToolsParser:
    def _build_parser(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="run_command")
        tools_parser = _add_subparser(subparsers, "tools", aliases=["tl"], help="Manage tools")
        _build_tools_args(tools_parser)
        return parser

    def test_accepts_tool_first_start(self):
        parser = self._build_parser()
        args = parser.parse_args(["tools", "chrome", "start"])
        assert args.run_command == "tools"
        assert args.action == "chrome"
        assert args.tool_name == "chrome"
        assert args.tool_action == "start"

    def test_accepts_tool_first_default_status(self):
        parser = self._build_parser()
        args = parser.parse_args(["tools", "web"])
        assert args.tool_name == "web"
        assert args.tool_action == "status"

    def test_keeps_group_action_shape(self):
        parser = self._build_parser()
        args = parser.parse_args(["tools", "start", "--chrome"])
        assert args.action == "start"
        assert args.chrome is True

    def test_help_lists_tool_subcommands(self, capsys):
        parser = self._build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["tools", "-h"])
        captured = capsys.readouterr()
        assert "chrome" in captured.out
        assert "web-bridge" in captured.out


class TestToolsRun:
    def test_run_dispatches_tool_first_start(self, monkeypatch):
        called: dict[str, set[str] | None] = {}

        def fake_start(selected=None):
            called["selected"] = selected
            return 0

        monkeypatch.setattr(tools, "start_all", fake_start)
        args = argparse.Namespace(action="chrome", tool_name="chrome", tool_action="start")
        assert tools.run(args) == 0
        assert called["selected"] == {"chrome"}

    def test_run_dispatches_tool_first_status(self, monkeypatch):
        called: dict[str, set[str] | None] = {}

        def fake_status(selected=None):
            called["selected"] = selected
            return 0

        monkeypatch.setattr(tools, "status_all", fake_status)
        args = argparse.Namespace(action="web", tool_name="web", tool_action="status")
        assert tools.run(args) == 0
        assert called["selected"] == {"web"}

    def test_run_keeps_group_status_default(self, monkeypatch):
        called: dict[str, set[str] | None] = {}

        def fake_status(selected=None):
            called["selected"] = selected
            return 0

        monkeypatch.setattr(tools, "status_all", fake_status)
        args = argparse.Namespace(action="status")
        assert tools.run(args) == 0
        assert called["selected"] is None


class TestNativeMcpRemoteUrl:
    """Native MCP writers must use get_tool_remote_url for remote tools."""

    def _make_fake_tool(self, server_name: str, port: int = 9222, path: str = "/mcp"):
        """Create a fake MCP tool class for testing."""
        return type("FakeTool", (), {
            "mcp_server_name": server_name,
            "mcp_endpoint": (property(lambda self: (port, path))),
        })()

    def test_update_opencode_mcp_uses_remote_url(self, monkeypatch, tmp_path):
        from codefreedom.cli import opencode
        from codefreedom.tools.registry import _MCP_TOOLS

        config_path = tmp_path / ".config" / "opencode" / "opencode.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text('{"mcp": {}}', encoding="utf-8")
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        fake_tool = self._make_fake_tool("chrome-devtools")
        monkeypatch.setitem(_MCP_TOOLS, "chrome", fake_tool)

        def fake_get_remote_url(name):
            if name == "chrome":
                return "http://remote.local:9223/mcp"
            return None

        monkeypatch.setattr(
            "codefreedom.tools.registry.get_tool_remote_url", fake_get_remote_url
        )

        opencode._update_opencode_mcp(["chrome"])
        result = json.loads(config_path.read_text())
        assert result["mcp"]["chrome-devtools"]["url"] == "http://remote.local:9223/mcp"
        assert result["mcp"]["chrome-devtools"]["type"] == "remote"

    def test_update_opencode_mcp_uses_local_url_when_no_remote(self, monkeypatch, tmp_path):
        from codefreedom.cli import opencode
        from codefreedom.tools.registry import _MCP_TOOLS

        config_path = tmp_path / ".config" / "opencode" / "opencode.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text('{"mcp": {}}', encoding="utf-8")
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        fake_tool = self._make_fake_tool("chrome-devtools", port=9223, path="/mcp")
        monkeypatch.setitem(_MCP_TOOLS, "chrome", fake_tool)

        def fake_get_remote_url(name):
            return None

        monkeypatch.setattr(
            "codefreedom.tools.registry.get_tool_remote_url", fake_get_remote_url
        )

        opencode._update_opencode_mcp(["chrome"])
        result = json.loads(config_path.read_text())
        assert "127.0.0.1:9223" in result["mcp"]["chrome-devtools"]["url"]

    def test_update_mimocode_mcp_uses_remote_url(self, monkeypatch, tmp_path):
        from codefreedom.cli import mimo
        from codefreedom.tools.registry import _MCP_TOOLS

        config_path = tmp_path / ".config" / "mimocode" / "mimocode.jsonc"
        config_path.parent.mkdir(parents=True)
        config_path.write_text('{"mcp": {}}', encoding="utf-8")
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        fake_tool = self._make_fake_tool("chrome-devtools")
        monkeypatch.setitem(_MCP_TOOLS, "chrome", fake_tool)

        def fake_get_remote_url(name):
            if name == "chrome":
                return "http://remote.local:9223/mcp"
            return None

        monkeypatch.setattr(
            "codefreedom.tools.registry.get_tool_remote_url", fake_get_remote_url
        )

        mimo._update_mimocode_mcp(["chrome"])
        result = json.loads(config_path.read_text())
        assert result["mcp"]["chrome-devtools"]["url"] == "http://remote.local:9223/mcp"
        assert result["mcp"]["chrome-devtools"]["type"] == "remote"

    def test_update_mimocode_mcp_uses_local_url_when_no_remote(self, monkeypatch, tmp_path):
        from codefreedom.cli import mimo
        from codefreedom.tools.registry import _MCP_TOOLS

        config_path = tmp_path / ".config" / "mimocode" / "mimocode.jsonc"
        config_path.parent.mkdir(parents=True)
        config_path.write_text('{"mcp": {}}', encoding="utf-8")
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        fake_tool = self._make_fake_tool("chrome-devtools", port=9223, path="/mcp")
        monkeypatch.setitem(_MCP_TOOLS, "chrome", fake_tool)

        def fake_get_remote_url(name):
            return None

        monkeypatch.setattr(
            "codefreedom.tools.registry.get_tool_remote_url", fake_get_remote_url
        )

        mimo._update_mimocode_mcp(["chrome"])
        result = json.loads(config_path.read_text())
        assert "127.0.0.1:9223" in result["mcp"]["chrome-devtools"]["url"]

    def test_update_codex_mcp_uses_remote_url(self, monkeypatch, tmp_path):
        import tomlkit

        from codefreedom.cli import codex
        from codefreedom.tools.registry import _MCP_TOOLS

        codex_home = tmp_path / ".codefreedom" / "codex-code" / "home"
        codex_home.mkdir(parents=True)
        config_path = codex_home / codex.CODEX_CONFIG_NAME
        config_path.write_text('[mcp_servers]\n', encoding="utf-8")

        fake_tool = self._make_fake_tool("chrome-devtools")
        monkeypatch.setitem(_MCP_TOOLS, "chrome", fake_tool)

        def fake_get_remote_url(name):
            if name == "chrome":
                return "http://remote.local:9223/mcp"
            return None

        monkeypatch.setattr(
            "codefreedom.tools.registry.get_tool_remote_url", fake_get_remote_url
        )

        codex._update_codex_mcp(["chrome"], codex_home)
        result = tomlkit.loads(config_path.read_text())
        assert str(result["mcp_servers"]["chrome-devtools"]["url"]) == "http://remote.local:9223/mcp"

    def test_update_codex_mcp_uses_local_url_when_no_remote(self, monkeypatch, tmp_path):
        import tomlkit

        from codefreedom.cli import codex
        from codefreedom.tools.registry import _MCP_TOOLS

        codex_home = tmp_path / ".codefreedom" / "codex-code" / "home"
        codex_home.mkdir(parents=True)
        config_path = codex_home / codex.CODEX_CONFIG_NAME
        config_path.write_text('[mcp_servers]\n', encoding="utf-8")

        fake_tool = self._make_fake_tool("chrome-devtools", port=9223, path="/mcp")
        monkeypatch.setitem(_MCP_TOOLS, "chrome", fake_tool)

        def fake_get_remote_url(name):
            return None

        monkeypatch.setattr(
            "codefreedom.tools.registry.get_tool_remote_url", fake_get_remote_url
        )

        codex._update_codex_mcp(["chrome"], codex_home)
        result = tomlkit.loads(config_path.read_text())
        assert "127.0.0.1:9223" in str(result["mcp_servers"]["chrome-devtools"]["url"])

    def test_load_tool_mcp_endpoints_uses_remote_url(self, monkeypatch):
        from codefreedom.tools.registry import load_tool_mcp_endpoints, _MCP_TOOLS

        fake_tool = self._make_fake_tool("chrome-devtools")
        monkeypatch.setitem(_MCP_TOOLS, "chrome", fake_tool)

        def fake_get_remote_url(name):
            if name == "chrome":
                return "http://remote.local:9223/mcp"
            return None

        monkeypatch.setattr(
            "codefreedom.tools.registry.get_tool_remote_url", fake_get_remote_url
        )

        endpoints = load_tool_mcp_endpoints(["chrome"])
        assert endpoints["mcpServers"]["chrome-devtools"]["url"] == "http://remote.local:9223/mcp"
