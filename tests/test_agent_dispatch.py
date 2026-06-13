"""Tests for agent dispatch in codefreedom.cli.run.agent."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest


class TestResolveAgent:
    def test_resolves_canonical_name(self):
        from codefreedom.cli.run.agent import _resolve_agent

        assert _resolve_agent("claude-code") == "claude-code"
        assert _resolve_agent("mimo-code") == "mimo-code"
        assert _resolve_agent("open-code") == "open-code"

    def test_resolves_alias(self):
        from codefreedom.cli.run.agent import _resolve_agent

        assert _resolve_agent("cc") == "claude-code"
        assert _resolve_agent("mc") == "mimo-code"
        assert _resolve_agent("oc") == "open-code"

    def test_returns_none_for_unknown(self):
        from codefreedom.cli.run.agent import _resolve_agent

        assert _resolve_agent("unknown") is None
        assert _resolve_agent("") is None


class TestListAgents:
    def test_returns_zero(self):
        from codefreedom.cli.run.agent import list_agents

        result = list_agents()
        assert result == 0


class TestRunAgent:
    @patch("importlib.import_module")
    def test_dispatches_to_agent_module(self, mock_import):
        from codefreedom.cli.run.agent import run_agent

        mock_mod = MagicMock()
        mock_mod.run.return_value = 0
        mock_import.return_value = mock_mod

        args = argparse.Namespace()
        result = run_agent("claude-code", args)
        assert result == 0
        mock_mod.run.assert_called_once_with(args)

    def test_returns_1_for_unknown_agent(self):
        from codefreedom.cli.run.agent import run_agent

        args = argparse.Namespace()
        result = run_agent("nonexistent", args)
        assert result == 1

    @patch("importlib.import_module", side_effect=ImportError("no module"))
    def test_returns_1_on_import_error(self, _mock):
        from codefreedom.cli.run.agent import run_agent

        args = argparse.Namespace()
        result = run_agent("claude-code", args)
        assert result == 1

    @patch("importlib.import_module")
    def test_returns_1_when_run_function_missing(self, mock_import):
        from codefreedom.cli.run.agent import run_agent

        mock_mod = MagicMock(spec=[])
        mock_import.return_value = mock_mod

        args = argparse.Namespace()
        result = run_agent("claude-code", args)
        assert result == 1


class TestHandleArgs:
    def test_list_action(self):
        from codefreedom.cli.run.agent import handle_args

        args = argparse.Namespace(agent_name="list")
        result = handle_args(args)
        assert result == 0

    def test_none_agent_shows_list(self):
        from codefreedom.cli.run.agent import handle_args

        args = argparse.Namespace(agent_name=None)
        result = handle_args(args)
        assert result == 0
