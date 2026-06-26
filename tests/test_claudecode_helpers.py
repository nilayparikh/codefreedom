"""Pure-logic tests for Claude Code CLI.

Tests arg parsing logic without I/O.
"""

from __future__ import annotations

import argparse

import pytest

pytestmark = pytest.mark.unit


class TestRegisterArgs:
    def test_dangerously_skip_permissions(self):
        from codefreedom.cli.claude import register_args

        parser = argparse.ArgumentParser()
        register_args(parser)
        args = parser.parse_args(["--dangerously-skip-permissions"])
        assert args.dangerously_skip_permissions is True

    def test_native_models_flag(self):
        from codefreedom.cli.claude import register_args

        parser = argparse.ArgumentParser()
        register_args(parser)
        args = parser.parse_args(["--native-models"])
        assert args.native_models is True


class TestInitClaude:
    def test_returns_zero(self):
        from codefreedom.cli.claude import init_claude

        result = init_claude()
        assert result == 0
