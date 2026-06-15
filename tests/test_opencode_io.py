"""I/O-dependent tests for OpenCode CLI.

Tests arg parsing and binary detection.
"""

from __future__ import annotations

import argparse

import pytest

pytestmark = pytest.mark.integration


class TestRegisterArgs:
    def test_add_sandbox_flag(self):
        from codefreedom.cli.opencode import register_args

        parser = argparse.ArgumentParser()
        register_args(parser)
        args = parser.parse_args(["--sandbox"])
        assert args.sandbox is True

    def test_run_as_me_flag(self):
        from codefreedom.cli.opencode import register_args

        parser = argparse.ArgumentParser()
        register_args(parser)
        args = parser.parse_args(["--run-as-me"])
        assert args.run_as_me is True


class TestFindOpenCodeBinary:
    def test_returns_none_or_string(self):
        from codefreedom.cli.opencode import find_opencode_binary

        result = find_opencode_binary()
        assert result is None or isinstance(result, str)
