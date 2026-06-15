"""Pure-logic tests for Claude Code CLI.

Tests arg parsing logic without I/O.
"""

from __future__ import annotations

import argparse

import pytest

pytestmark = pytest.mark.unit


class TestRegisterArgs:
    def test_add_sandbox_flag(self):
        from codefreedom.cli.claude import register_args

        parser = argparse.ArgumentParser()
        register_args(parser)
        args = parser.parse_args(["--sandbox"])
        assert args.sandbox is True

    def test_add_cuda_flag(self):
        from codefreedom.cli.claude import register_args

        parser = argparse.ArgumentParser()
        register_args(parser)
        args = parser.parse_args(["--sandbox", "--cuda"])
        assert args.gpu_cuda is True
        assert args.gpu_rocm is False

    def test_mutually_exclusive_gpu(self):
        from codefreedom.cli.claude import register_args

        parser = argparse.ArgumentParser()
        register_args(parser)
        with pytest.raises(SystemExit):
            parser.parse_args(["--cuda", "--rocm"])

    def test_dangerously_skip_permissions(self):
        from codefreedom.cli.claude import register_args

        parser = argparse.ArgumentParser()
        register_args(parser)
        args = parser.parse_args(["--dangerously-skip-permissions"])
        assert args.dangerously_skip_permissions is True

    def test_run_as_me_flag(self):
        from codefreedom.cli.claude import register_args

        parser = argparse.ArgumentParser()
        register_args(parser)
        args = parser.parse_args(["--run-as-me"])
        assert args.run_as_me is True

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
