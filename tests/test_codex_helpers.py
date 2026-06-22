"""Pure-logic tests for Codex config generation.

Tests transform functions that take inputs and return outputs with no I/O.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


class TestDetectProxyUrl:
    def test_default_url(self, monkeypatch):
        from codefreedom.cli.codex import _detect_proxy_url

        monkeypatch.delenv("PROXY_BASE_URL", raising=False)
        monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
        assert _detect_proxy_url({}) == "http://localhost:4000"

    def test_from_base_env_proxy_url(self, monkeypatch):
        from codefreedom.cli.codex import _detect_proxy_url

        monkeypatch.delenv("PROXY_BASE_URL", raising=False)
        monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
        url = _detect_proxy_url({"PROXY_BASE_URL": "http://my-proxy:5000"})
        assert url == "http://my-proxy:5000"

    def test_from_base_env_litellm_url(self, monkeypatch):
        from codefreedom.cli.codex import _detect_proxy_url

        monkeypatch.delenv("PROXY_BASE_URL", raising=False)
        monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
        url = _detect_proxy_url({"LITELLM_BASE_URL": "http://my-proxy:5000"})
        assert url == "http://my-proxy:5000"


class TestGenerateCodexConfig:
    def test_basic_config(self):
        from codefreedom.cli.codex import _generate_codex_config

        config = _generate_codex_config("http://localhost:4000", {})
        assert 'model_provider = "codefreedom"' in config
        assert "[model_providers.codefreedom]" in config
        assert 'base_url = "http://localhost:4000/v1"' in config
        assert 'name = "CodeFreedom Proxy"' in config
        assert 'wire_api = "chat"' in config

    def test_with_api_key(self):
        from codefreedom.cli.codex import _generate_codex_config

        config = _generate_codex_config(
            "http://localhost:4000", {"PROXY_API_KEY": "sk-test"}
        )
        assert 'env_key = "OPENAI_API_KEY"' in config

    def test_without_api_key(self):
        from codefreedom.cli.codex import _generate_codex_config

        config = _generate_codex_config("http://localhost:4000", {})
        assert "env_key" not in config

    def test_with_default_model(self):
        from codefreedom.cli.codex import _generate_codex_config

        config = _generate_codex_config(
            "http://localhost:4000", {"CODEX_DEFAULT_MODEL": "gpt-4o"}
        )
        assert 'model = "gpt-4o"' in config

    def test_proxy_url_trailing_slash_stripped(self):
        from codefreedom.cli.codex import _generate_codex_config

        config = _generate_codex_config("http://localhost:4000/", {})
        assert 'base_url = "http://localhost:4000/v1"' in config

    def test_custom_proxy_url(self):
        from codefreedom.cli.codex import _generate_codex_config

        config = _generate_codex_config("http://my-proxy:8080", {})
        assert 'base_url = "http://my-proxy:8080/v1"' in config


class TestFindCodexBinary:
    def test_returns_none_when_not_found(self, monkeypatch):
        from codefreedom.cli.codex import find_codex_binary

        monkeypatch.setattr("shutil.which", lambda _: None)
        assert find_codex_binary() is None

    def test_returns_path_when_found(self, monkeypatch):
        from codefreedom.cli.codex import find_codex_binary

        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/codex")
        assert find_codex_binary() == "/usr/bin/codex"
