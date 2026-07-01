from __future__ import annotations

import argparse

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
