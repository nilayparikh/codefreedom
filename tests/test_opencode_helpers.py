"""Pure-logic tests for OpenCode config generation and model building.

Tests transform functions that take inputs and return outputs with no I/O.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


class TestDetectProxyUrl:
    def test_default_url(self, monkeypatch):
        from codefreedom.cli.opencode import _detect_proxy_url

        monkeypatch.delenv("PROXY_BASE_URL", raising=False)
        monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
        assert _detect_proxy_url({}) == "http://localhost:4000"

    def test_from_base_env_proxy_url(self, monkeypatch):
        from codefreedom.cli.opencode import _detect_proxy_url

        monkeypatch.delenv("PROXY_BASE_URL", raising=False)
        monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
        url = _detect_proxy_url({"PROXY_BASE_URL": "http://my-proxy:5000"})
        assert url == "http://my-proxy:5000"

    def test_from_base_env_litellm_url(self, monkeypatch):
        from codefreedom.cli.opencode import _detect_proxy_url

        monkeypatch.delenv("PROXY_BASE_URL", raising=False)
        monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
        url = _detect_proxy_url({"LITELLM_BASE_URL": "http://my-proxy:5000"})
        assert url == "http://my-proxy:5000"


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


class TestOpenCodeEnvLoading:
    def test_run_uses_open_code_runtime_resolution(self, monkeypatch):
        import argparse
        import codefreedom.cli.opencode as opencode_mod

        calls = []

        def fake_resolve_agent_runtime(
            agent, *, workspace_dir, profile_name="default", mode="local"
        ):
            calls.append((agent, profile_name, mode))

            class Runtime:
                base_env = {}

            return Runtime()

        monkeypatch.setattr(
            opencode_mod, "resolve_agent_runtime", fake_resolve_agent_runtime
        )

        import codefreedom.cli.common as common_mod

        monkeypatch.setattr(
            common_mod,
            "load_profile_with_tools",
            lambda name, path, env, mode, **kw: ({}, [], 0),
        )
        monkeypatch.setattr(
            common_mod, "acquire_and_run", lambda sid, tools, name, fn: 0
        )

        ns = argparse.Namespace(
            list_profiles=False,
            profile="default",
            opencode_action=None,
            agent_args=[],
        )
        opencode_mod.run(ns)
        assert calls == [("open-code", "default", "local")]
