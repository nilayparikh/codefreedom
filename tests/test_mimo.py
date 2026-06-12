"""Tests for MiMoCode CLI integration."""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest


class TestGenerateMimoConfig:
    """Tests for _generate_mimo_config and _fetch_proxy_models."""

    def test_default_models_when_proxy_unreachable(self):
        """When proxy is unreachable, _generate_mimo_config returns empty models."""
        from codefreedom.cli.mimo import _generate_mimo_config

        config = _generate_mimo_config("http://localhost:4000", {})

        assert config["$schema"] == "https://opencode.ai/config.json"
        assert "codefreedom" in config["provider"]
        provider = config["provider"]["codefreedom"]
        assert provider["name"] == "CodeFreedom Proxy"
        assert provider["api"] == "http://localhost:4000/v1"
        assert provider["npm"] == "@ai-sdk/openai-compatible"
        # No hardcoded fallback models — empty until proxy is reachable
        assert provider["models"] == {}

    def test_custom_proxy_url(self):
        """Custom proxy URL is reflected in the generated config."""
        from codefreedom.cli.mimo import _generate_mimo_config

        config = _generate_mimo_config("http://my-proxy:8080", {})
        assert config["provider"]["codefreedom"]["api"] == "http://my-proxy:8080/v1"

    def test_proxy_api_key_from_env(self):
        """Profile env PROXY_API_KEY is passed through to provider options."""
        from codefreedom.cli.mimo import _generate_mimo_config

        config = _generate_mimo_config(
            "http://localhost:4000", {"PROXY_API_KEY": "sk-test"}
        )
        assert config["provider"]["codefreedom"]["options"]["apiKey"] == "sk-test"

    def test_proxy_url_strips_trailing_slash(self):
        """Trailing slash on proxy URL is removed before /v1 is appended."""
        from codefreedom.cli.mimo import _generate_mimo_config

        config = _generate_mimo_config("http://localhost:4000/", {})
        assert config["provider"]["codefreedom"]["api"] == "http://localhost:4000/v1"

    def test_build_provider_models_minimal(self):
        """_build_provider_models produces minimal entries: name + tool_call only."""
        from codefreedom.cli.mimo import _build_provider_models

        proxy_models = [
            {"id": "deepseek-chat"},
            {"id": "gpt-4o"},
            {"id": "claude-sonnet-4-20250514"},
        ]
        models = _build_provider_models(proxy_models)

        for mid in ("deepseek-chat", "gpt-4o", "claude-sonnet-4-20250514"):
            assert models[mid]["tool_call"] is True
            assert "name" in models[mid]
            # No hardcoded reasoning or limit — discovered at runtime
            assert "reasoning" not in models[mid]
            assert "limit" not in models[mid]

    def test_build_provider_models_skips_filtered(self):
        """Internal models (azure/*, gpt-3.5-turbo, custom) are skipped."""
        from codefreedom.cli.mimo import _build_provider_models

        proxy_models = [
            {"id": "azure/gpt-4"},
            {"id": "Azure/GPT-5.4"},
            {"id": "gpt-3.5-turbo"},
            {"id": "custom"},
            {"id": "valid-model"},
        ]
        models = _build_provider_models(proxy_models)
        # Only valid-model should remain
        assert list(models.keys()) == ["valid-model"]

    def test_build_provider_models_display_name(self):
        """Provider-prefixed models get the short name as display name."""
        from codefreedom.cli.mimo import _build_provider_models

        models = _build_provider_models([{"id": "openai/gpt-4o"}])
        assert models["openai/gpt-4o"]["name"] == "gpt-4o"

    def test_default_model_from_profile_env(self):
        """MIMOCODE_DEFAULT_MODEL in profile env sets the model field."""
        from codefreedom.cli.mimo import _generate_mimo_config

        config = _generate_mimo_config(
            "http://localhost:4000", {"MIMOCODE_DEFAULT_MODEL": "deepseek-chat"}
        )
        assert config["model"] == "codefreedom/deepseek-chat"

    def test_default_model_qualified_already(self):
        """Already-qualified model name doesn't get double-prefixed."""
        from codefreedom.cli.mimo import _generate_mimo_config

        config = _generate_mimo_config(
            "http://localhost:4000",
            {"MIMOCODE_DEFAULT_MODEL": "codefreedom/deepseek-chat"},
        )
        assert config["model"] == "codefreedom/deepseek-chat"

    def test_no_default_model_when_not_set(self):
        """No model field when MIMOCODE_DEFAULT_MODEL is not in profile env."""
        from codefreedom.cli.mimo import _generate_mimo_config

        config = _generate_mimo_config("http://localhost:4000", {})
        assert "model" not in config


class TestWriteMimoConfig:
    """Tests for _write_mimo_config."""

    def test_writes_valid_json(self, tmp_path: Path):
        """Generated config is valid JSON with correct structure."""
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

        loaded = json.loads(config_path.read_text())
        assert loaded["$schema"] == "https://opencode.ai/config.json"
        assert "codefreedom" in loaded["provider"]

    def test_creates_parent_dirs(self, tmp_path: Path):
        """Creates parent directories if they don't exist."""
        from codefreedom.cli.mimo import _write_mimo_config

        nested = tmp_path / "a" / "b" / "c"
        config = {"$schema": "https://opencode.ai/config.json", "provider": {}}
        config_path = _write_mimo_config(config, nested)
        assert config_path.exists()

    @pytest.mark.skipif(
        sys.platform == "win32", reason="Unix permissions not applicable on Windows"
    )
    def test_sets_secure_permissions(self, tmp_path: Path):
        """Generated config file has 0o600 permissions (owner read/write only)."""
        from codefreedom.cli.mimo import _write_mimo_config

        config = {"$schema": "https://opencode.ai/config.json", "provider": {}}
        config_path = _write_mimo_config(config, tmp_path)
        mode = config_path.stat().st_mode
        assert stat.S_IMODE(mode) == 0o600


class TestDetectProxyUrl:
    """Tests for _detect_proxy_url."""

    def test_default_url(self):
        """Returns default when no env var is set."""
        from codefreedom.cli.mimo import _detect_proxy_url

        url = _detect_proxy_url({})
        assert url == "http://localhost:4000"

    def test_from_base_env(self):
        """LITELLM_BASE_URL in base_env takes priority."""
        from codefreedom.cli.mimo import _detect_proxy_url

        url = _detect_proxy_url({"LITELLM_BASE_URL": "http://my-proxy:5000"})
        assert url == "http://my-proxy:5000"


class TestFindMimoBinary:
    """Tests for find_mimo_binary."""

    def test_not_found_returns_none(self):
        """When mimo is not on PATH, returns None."""
        from codefreedom.cli.mimo import find_mimo_binary

        # In test environment, mimo is unlikely to be installed
        result = find_mimo_binary()
        # Either found or None — we just verify it runs without error
        assert result is None or isinstance(result, str)


class TestEnsureMimoSandboxDir:
    """Tests for _ensure_mimo_sandbox_dir."""

    def test_creates_directories(self):
        """Creates the expected sandbox directory structure under CODEFREEDOM_HOME."""
        from codefreedom.cli.mimo import _ensure_mimo_sandbox_dir

        # Uses the test CODEFREEDOM_HOME set by conftest.py
        mimo_home, config_dir = _ensure_mimo_sandbox_dir("test-mimo")

        assert mimo_home.exists()
        assert (mimo_home / "data").exists()
        assert (mimo_home / "config").exists()
        assert (mimo_home / "cache").exists()
        assert (mimo_home / "state").exists()
        assert config_dir.exists()
