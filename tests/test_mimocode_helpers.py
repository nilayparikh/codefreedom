"""Pure-logic tests for MiMoCode config generation and model building.

Tests transform functions that take inputs and return outputs with no I/O.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


class TestDetectProxyUrl:
    def test_default_url(self, monkeypatch):
        from codefreedom.cli.mimo import _detect_proxy_url

        monkeypatch.delenv("PROXY_BASE_URL", raising=False)
        monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
        assert _detect_proxy_url({}) == "http://localhost:4000"

    def test_from_base_env_proxy_url(self, monkeypatch):
        from codefreedom.cli.mimo import _detect_proxy_url

        monkeypatch.delenv("PROXY_BASE_URL", raising=False)
        monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
        url = _detect_proxy_url({"PROXY_BASE_URL": "http://my-proxy:5000"})
        assert url == "http://my-proxy:5000"

    def test_from_base_env_litellm_url(self, monkeypatch):
        from codefreedom.cli.mimo import _detect_proxy_url

        monkeypatch.delenv("PROXY_BASE_URL", raising=False)
        monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
        url = _detect_proxy_url({"LITELLM_BASE_URL": "http://my-proxy:5000"})
        assert url == "http://my-proxy:5000"

    def test_env_var_overrides_base_env(self, monkeypatch):
        from codefreedom.cli.mimo import _detect_proxy_url

        monkeypatch.setenv("PROXY_BASE_URL", "http://env-proxy:9000")
        monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
        url = _detect_proxy_url({"PROXY_BASE_URL": "http://base-proxy:8000"})
        assert url == "http://base-proxy:8000"

    def test_proxy_base_url_takes_priority_over_litellm(self, monkeypatch):
        from codefreedom.cli.mimo import _detect_proxy_url

        monkeypatch.delenv("PROXY_BASE_URL", raising=False)
        monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
        url = _detect_proxy_url(
            {
                "PROXY_BASE_URL": "http://proxy:4000",
                "LITELLM_BASE_URL": "http://litellm:4000",
            }
        )
        assert url == "http://proxy:4000"


class TestMimoEnvLoading:
    def test_run_uses_mimo_runtime_resolution(self, monkeypatch):
        import argparse
        import codefreedom.cli.mimo as mimo_mod

        calls = []

        def fake_resolve_agent_runtime(
            agent, *, workspace_dir, profile_name="default", mode="local"
        ):
            calls.append((agent, profile_name, mode))

            class Runtime:
                base_env = {}

            return Runtime()

        monkeypatch.setattr(
            mimo_mod, "resolve_agent_runtime", fake_resolve_agent_runtime
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
            mimo_action=None,
            agent_args=[],
        )
        mimo_mod.run(ns)
        assert calls == [("mimo-code", "default", "local")]


class TestGenerateMimoConfig:
    def test_default_models_when_proxy_unreachable(self):
        from codefreedom.cli.mimo import _generate_mimo_config

        config = _generate_mimo_config("http://localhost:4000", {})

        assert config["$schema"] == "https://opencode.ai/config.json"
        assert "codefreedom" in config["provider"]
        provider = config["provider"]["codefreedom"]
        assert provider["name"] == "CodeFreedom Proxy"
        assert provider["api"] == "http://localhost:4000/v1"
        assert provider["npm"] == "@ai-sdk/openai-compatible"
        assert provider["models"] == {}

    def test_custom_proxy_url(self):
        from codefreedom.cli.mimo import _generate_mimo_config

        config = _generate_mimo_config("http://my-proxy:8080", {})
        assert config["provider"]["codefreedom"]["api"] == "http://my-proxy:8080/v1"

    def test_proxy_api_key_from_env(self):
        from codefreedom.cli.mimo import _generate_mimo_config

        config = _generate_mimo_config(
            "http://localhost:4000", {"PROXY_API_KEY": "sk-test"}
        )
        assert config["provider"]["codefreedom"]["options"]["apiKey"] == "sk-test"

    def test_proxy_url_strips_trailing_slash(self):
        from codefreedom.cli.mimo import _generate_mimo_config

        config = _generate_mimo_config("http://localhost:4000/", {})
        assert config["provider"]["codefreedom"]["api"] == "http://localhost:4000/v1"

    def test_default_model_from_profile_env(self):
        from codefreedom.cli.mimo import _generate_mimo_config

        config = _generate_mimo_config(
            "http://localhost:4000", {"MIMOCODE_DEFAULT_MODEL": "deepseek-chat"}
        )
        assert config["model"] == "codefreedom/deepseek-chat"

    def test_default_model_qualified_already(self):
        from codefreedom.cli.mimo import _generate_mimo_config

        config = _generate_mimo_config(
            "http://localhost:4000",
            {"MIMOCODE_DEFAULT_MODEL": "codefreedom/deepseek-chat"},
        )
        assert config["model"] == "codefreedom/deepseek-chat"

    def test_no_default_model_when_not_set(self):
        from codefreedom.cli.mimo import _generate_mimo_config

        config = _generate_mimo_config("http://localhost:4000", {})
        assert "model" not in config


class TestBuildProviderModels:
    def test_minimal_entries(self):
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
            assert "reasoning" not in models[mid]
            assert "limit" not in models[mid]

    def test_skips_filtered_models(self):
        from codefreedom.cli.mimo import _build_provider_models

        proxy_models = [
            {"id": "azure/gpt-4"},
            {"id": "Azure/GPT-5.4"},
            {"id": "gpt-3.5-turbo"},
            {"id": "custom"},
            {"id": "valid-model"},
        ]
        models = _build_provider_models(proxy_models)
        assert list(models.keys()) == ["valid-model"]

    def test_display_name(self):
        from codefreedom.cli.mimo import _build_provider_models

        models = _build_provider_models([{"id": "openai/gpt-4o"}])
        assert models["openai/gpt-4o"]["name"] == "gpt-4o"
