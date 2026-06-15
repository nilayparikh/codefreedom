"""I/O-dependent tests for MiMoCode CLI.

Tests file writing, binary detection, and sandbox directory creation.
"""

from __future__ import annotations

import argparse
import json
import stat
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


class TestWriteMimoConfig:
    def test_writes_valid_json(self, tmp_path: Path):
        from codefreedom.cli.mimo import _write_mimo_config

        config = {
            "$schema": "https://opencode.ai/config.json",
            "provider": {
                "codefreedom": {
                    "name": "Test",
                    "api": "http://localhost:4000/v1",
                    "npm": "@ai-sdk/openai-compatible",
                    "models": {"test-model": {"name": "Test", "tool_call": True}},
                    "options": {"apiKey": "test"},
                }
            },
        }
        config_path = _write_mimo_config(config, tmp_path)
        assert config_path.exists()
        assert config_path.name == "mimocode.json"

        loaded = json.loads(config_path.read_text(encoding="utf-8"))
        assert loaded["$schema"] == "https://opencode.ai/config.json"
        assert "codefreedom" in loaded["provider"]

    def test_creates_parent_dirs(self, tmp_path: Path):
        from codefreedom.cli.mimo import _write_mimo_config

        nested = tmp_path / "a" / "b" / "c"
        config = {"$schema": "https://opencode.ai/config.json", "provider": {}}
        config_path = _write_mimo_config(config, nested)
        assert config_path.exists()

    @pytest.mark.skipif(
        sys.platform == "win32", reason="Unix permissions not applicable on Windows"
    )
    def test_sets_secure_permissions(self, tmp_path: Path):
        from codefreedom.cli.mimo import _write_mimo_config

        config = {"$schema": "https://opencode.ai/config.json", "provider": {}}
        config_path = _write_mimo_config(config, tmp_path)
        mode = config_path.stat().st_mode
        assert stat.S_IMODE(mode) == 0o600


class TestFindMimoBinary:
    def test_returns_none_or_string(self):
        from codefreedom.cli.mimo import find_mimo_binary

        result = find_mimo_binary()
        assert result is None or isinstance(result, str)


class TestEnsureMimoSandboxDir:
    def test_creates_directories(self):
        from codefreedom.cli.mimo import _ensure_mimo_sandbox_dir

        mimo_home, config_dir = _ensure_mimo_sandbox_dir("test-mimo")

        assert mimo_home.exists()
        assert (mimo_home / "data").exists()
        assert (mimo_home / "config").exists()
        assert (mimo_home / "cache").exists()
        assert (mimo_home / "state").exists()
        assert config_dir.exists()


class TestRegisterArgs:
    def test_add_sandbox_flag(self):
        from codefreedom.cli.mimo import register_args

        parser = argparse.ArgumentParser()
        register_args(parser)
        args = parser.parse_args(["--sandbox"])
        assert args.sandbox is True

    def test_run_as_me_flag(self):
        from codefreedom.cli.mimo import register_args

        parser = argparse.ArgumentParser()
        register_args(parser)
        args = parser.parse_args(["--run-as-me"])
        assert args.run_as_me is True
