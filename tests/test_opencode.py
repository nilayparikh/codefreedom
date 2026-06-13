"""Tests for OpenCode CLI entrypoint."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestGenerateOpenCodeConfig:
    def test_default_config_structure(self):
        from codefreedom.cli.opencode import _generate_opencode_config

        config = _generate_opencode_config("http://localhost:4000", {})
        assert config["$schema"] == "https://opencode.ai/config.json"
        assert "codefreedom" in config["provider"]
        provider = config["provider"]["codefreedom"]
        assert provider["api"] == "http://localhost:4000/v1"

    def test_custom_proxy_url(self):
        from codefreedom.cli.opencode import _generate_opencode_config

        config = _generate_opencode_config("http://my-proxy:8080", {})
        assert config["provider"]["codefreedom"]["api"] == "http://my-proxy:8080/v1"

    def test_proxy_api_key_from_env(self):
        from codefreedom.cli.opencode import _generate_opencode_config

        config = _generate_opencode_config(
            "http://localhost:4000", {"PROXY_API_KEY": "sk-test"}
        )
        assert config["provider"]["codefreedom"]["options"]["apiKey"] == "sk-test"

    def test_proxy_url_strips_trailing_slash(self):
        from codefreedom.cli.opencode import _generate_opencode_config

        config = _generate_opencode_config("http://localhost:4000/", {})
        assert config["provider"]["codefreedom"]["api"] == "http://localhost:4000/v1"


class TestBuildProviderModels:
    def test_minimal_entries(self):
        from codefreedom.cli.opencode import _build_provider_models

        proxy_models = [
            {"id": "deepseek-chat"},
            {"id": "gpt-4o"},
            {"id": "claude-sonnet-4-20250514"},
        ]
        models = _build_provider_models(proxy_models)

        for mid in ("deepseek-chat", "gpt-4o", "claude-sonnet-4-20250514"):
            assert models[mid]["tool_call"] is True
            assert "name" in models[mid]

    def test_skips_filtered_models(self):
        from codefreedom.cli.opencode import _build_provider_models

        proxy_models = [
            {"id": "azure/gpt-4"},
            {"id": "gpt-3.5-turbo"},
            {"id": "custom"},
            {"id": "valid-model"},
        ]
        models = _build_provider_models(proxy_models)
        assert "valid-model" in models
        assert "azure/gpt-4" not in models
        assert "gpt-3.5-turbo" not in models


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
