"""Tests for the `codefreedom vscode proxy config` command."""

from __future__ import annotations

import argparse
import json
import urllib.error
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from codefreedom.cli.vscode import (
    _STANDARD_REASONING_EFFORT_LEVELS,
    _VSCODE_APIKEY_PLACEHOLDER,
    _build_vscode_entry,
    _check_proxy_live,
    cmd_vscode_proxy_config,
    _fetch_model_info,
    _model_to_vscode_entry,
    _proxy_health_url,
    _proxy_model_info_url,
    _resolve_master_key,
    _resolve_reasoning_effort,
)

# ── _resolve_master_key ──────────────────────────────────────────────────────


class TestResolveMasterKey:
    def test_from_os_environ_wins(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-from-env")
        # Even if the file has a different key, env wins.
        (tmp_path / ".env.proxy.secrets").write_text(
            "LITELLM_MASTER_KEY=sk-from-file\n"
        )
        assert _resolve_master_key() == "sk-from-env"

    def test_from_secrets_file_when_env_missing(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
        (tmp_path / ".env.proxy.secrets").write_text(
            "LITELLM_MASTER_KEY=sk-from-file\n"
        )
        assert _resolve_master_key() == "sk-from-file"

    def test_missing_in_both(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
        # No secrets file
        assert _resolve_master_key() is None

    def test_empty_string_in_env_treated_as_missing(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.setenv("LITELLM_MASTER_KEY", "   ")
        (tmp_path / ".env.proxy.secrets").write_text(
            "LITELLM_MASTER_KEY=sk-from-file\n"
        )
        # Whitespace-only env falls through to the file.
        assert _resolve_master_key() == "sk-from-file"

    def test_secrets_file_missing_key(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
        (tmp_path / ".env.proxy.secrets").write_text("OTHER_KEY=foo\n")
        assert _resolve_master_key() is None


# ── URL helpers ──────────────────────────────────────────────────────────────


class TestUrlHelpers:
    def test_health_url(self):
        assert _proxy_health_url("localhost", 4000) == (
            "http://localhost:4000/health/liveliness"
        )

    def test_model_info_url(self):
        assert _proxy_model_info_url("barsana.local", 4000) == (
            "http://barsana.local:4000/v1/model/info"
        )


# ── _check_proxy_live ────────────────────────────────────────────────────────


class TestCheckProxyLive:
    def test_returns_true_on_200(self, monkeypatch):
        ctx = MagicMock()
        ctx.__enter__.return_value.status = 200
        monkeypatch.setattr(
            "codefreedom.cli.vscode.urllib.request.urlopen",
            lambda req, timeout: ctx,
        )
        assert _check_proxy_live("h", 4000) is True

    def test_returns_false_on_500(self, monkeypatch):
        ctx = MagicMock()
        ctx.__enter__.return_value.status = 500
        monkeypatch.setattr(
            "codefreedom.cli.vscode.urllib.request.urlopen",
            lambda req, timeout: ctx,
        )
        assert _check_proxy_live("h", 4000) is False

    def test_returns_false_on_connection_refused(self, monkeypatch):
        def boom(req, timeout):
            raise urllib.error.URLError("Connection refused")

        monkeypatch.setattr("codefreedom.cli.vscode.urllib.request.urlopen", boom)
        assert _check_proxy_live("h", 4000) is False

    def test_returns_false_on_timeout(self, monkeypatch):
        def boom(req, timeout):
            raise TimeoutError("timed out")

        monkeypatch.setattr("codefreedom.cli.vscode.urllib.request.urlopen", boom)
        assert _check_proxy_live("h", 4000) is False

    def test_returns_false_on_dns_failure(self, monkeypatch):
        def boom(req, timeout):
            raise OSError("Name or service not known")

        monkeypatch.setattr("codefreedom.cli.vscode.urllib.request.urlopen", boom)
        assert _check_proxy_live("h", 4000) is False


# ── _fetch_model_info ────────────────────────────────────────────────────────


class TestFetchModelInfo:
    def _mock_urlopen(self, monkeypatch, body: Any):
        ctx = MagicMock()
        ctx.__enter__.return_value.read.return_value = json.dumps(body).encode("utf-8")
        monkeypatch.setattr(
            "codefreedom.cli.vscode.urllib.request.urlopen",
            lambda req, timeout: ctx,
        )

    def test_returns_data_list(self, monkeypatch):
        self._mock_urlopen(
            monkeypatch,
            {"data": [{"model_name": "m1"}, {"model_name": "m2"}]},
        )
        result = _fetch_model_info("h", 4000, "sk-test")
        assert result == [{"model_name": "m1"}, {"model_name": "m2"}]

    def test_missing_data_field_returns_empty(self, monkeypatch):
        self._mock_urlopen(monkeypatch, {"other": "field"})
        result = _fetch_model_info("h", 4000, "sk-test")
        assert result == []

    def test_invalid_shape_raises(self, monkeypatch):
        self._mock_urlopen(monkeypatch, ["not", "a", "dict"])
        with pytest.raises(ValueError, match="not an object"):
            _fetch_model_info("h", 4000, "sk-test")

    def test_authorization_header_sent(self, monkeypatch):
        ctx = MagicMock()
        ctx.__enter__.return_value.read.return_value = b'{"data": []}'
        captured: list = []

        def fake(req, timeout):
            captured.append(req)
            return ctx

        monkeypatch.setattr("codefreedom.cli.vscode.urllib.request.urlopen", fake)
        _fetch_model_info("h", 4000, "sk-abc")
        assert captured[0].headers["Authorization"] == "Bearer sk-abc"


# ── _model_to_vscode_entry ───────────────────────────────────────────────────


class TestModelToVscodeEntry:
    BASE_URL = "http://example:4000/v1"

    STD = list(_STANDARD_REASONING_EFFORT_LEVELS)

    def test_basic_model(self):
        out = _model_to_vscode_entry(
            {"model_name": "foo", "model_info": {}}, self.BASE_URL
        )
        assert out["id"] == "foo"
        assert out["name"] == "foo"
        assert out["url"] == self.BASE_URL
        # toolCalling is always True (see _model_to_vscode_entry docstring).
        assert out["toolCalling"] is True
        assert out["vision"] is False
        # Defaults applied
        assert out["maxInputTokens"] == 128000
        assert out["maxOutputTokens"] == 16000
        # Unknown model → standard reasoning-effort set (permissive)
        assert out["supportsReasoningEffort"] == self.STD

    def test_explicit_capabilities(self):
        out = _model_to_vscode_entry(
            {
                "model_name": "bar",
                "model_info": {
                    "supports_function_calling": True,
                    "supports_vision": True,
                    "max_input_tokens": 200000,
                    "max_output_tokens": 8000,
                },
            },
            self.BASE_URL,
        )
        assert out["toolCalling"] is True
        assert out["vision"] is True
        assert out["maxInputTokens"] == 200000
        assert out["maxOutputTokens"] == 8000
        # "bar" doesn't match any hardcoded pattern → standard set (permissive)
        assert out["supportsReasoningEffort"] == self.STD

    def test_tool_calling_always_true_even_when_proxy_says_no(self):
        # The whole point of the always-True default: even if LiteLLM
        # explicitly reports supports_function_calling=False, or lists a
        # supported_openai_params that does NOT include tools/tool_choice,
        # the entry must still advertise tool support so VS Code exposes
        # the tool UI for the model.
        out = _model_to_vscode_entry(
            {
                "model_name": "baz",
                "model_info": {
                    "supports_function_calling": False,
                    "supports_tool_choice": False,
                    "supported_openai_params": ["stream", "temperature"],
                },
            },
            self.BASE_URL,
        )
        assert out["toolCalling"] is True

    def test_max_tokens_used_when_specific_missing(self):
        out = _model_to_vscode_entry(
            {
                "model_name": "q",
                "model_info": {"max_tokens": 100000},
            },
            self.BASE_URL,
        )
        assert out["maxInputTokens"] == 100000
        assert out["maxOutputTokens"] == 100000

    def test_missing_model_info(self):
        out = _model_to_vscode_entry({"model_name": "x"}, self.BASE_URL)
        assert out["id"] == "x"
        # toolCalling is always True even with no model_info.
        assert out["toolCalling"] is True
        assert out["vision"] is False
        # Unknown model name → standard reasoning-effort set (permissive)
        assert out["supportsReasoningEffort"] == self.STD

    def test_invalid_token_values_fall_back(self):
        out = _model_to_vscode_entry(
            {
                "model_name": "bad",
                "model_info": {
                    "max_input_tokens": "not-a-number",
                    "max_output_tokens": None,
                },
            },
            self.BASE_URL,
        )
        assert out["maxInputTokens"] == 128000
        assert out["maxOutputTokens"] == 16000

    def test_model_name_fallback_to_id(self):
        out = _model_to_vscode_entry({"model_info": {"id": "from-id"}}, self.BASE_URL)
        assert out["id"] == "from-id"
        assert out["name"] == "from-id"

    def test_model_name_fallback_to_unknown(self):
        out = _model_to_vscode_entry({}, self.BASE_URL)
        assert out["id"] == "unknown"

    def test_known_model_with_gradient_emits_list(self):
        # A model that supports reasoning gets the full standard set.
        out = _model_to_vscode_entry({"model_name": "Azure/GPT-5.4"}, self.BASE_URL)
        assert out["supportsReasoningEffort"] == self.STD

    def test_known_model_only_none_omits_field(self):
        # A model that matches a rule with `None` (only supports "none")
        # gets the field OMITTED entirely — not `["none"]`, not `None`.
        out = _model_to_vscode_entry(
            {"model_name": "Azure/GPT-5.4-Nano"}, self.BASE_URL
        )
        assert "supportsReasoningEffort" not in out
        # The rest of the entry is still intact.
        assert out["id"] == "Azure/GPT-5.4-Nano"
        assert out["toolCalling"] is True

    def test_only_none_for_all_only_none_families(self):
        # Spot-check several "only none" families from the research.
        for name in (
            "NVIDIA/GLM-5.1",
            "NVIDIA/Kimi-K2.6",
            "DGX/Qwen3.6-27B",
            "CodeFreedom/Pro",
            "CodeFreedom/Air",
            "OpenCodeZen/Big-Pickle",
            "OpenRouter/FreeRouter",
        ):
            out = _model_to_vscode_entry({"model_name": name}, self.BASE_URL)
            assert (
                "supportsReasoningEffort" not in out
            ), f"{name} should omit supportsReasoningEffort but got {out.get('supportsReasoningEffort')!r}"


# ── _resolve_reasoning_effort ────────────────────────────────────────────────


class TestResolveReasoningEffort:
    """Reasoning-effort lookup — always returns the standard set for any
    model that supports reasoning.

    The helper has a two-way return contract:
      * ``list[str]`` — model supports reasoning; always the full standard
        set (``["none", "low", "medium", "high", "xhigh", "max"]``).
      * ``None`` — model has no real reasoning capability; the caller
        should OMIT the field.

    Models not in the hardcoded table are treated permissively (full standard
    set).  Order matters: more specific patterns must come first so they win
    over less-specific ones (e.g. ``gpt-5.4-nano`` before ``gpt-5.4``).
    """

    STD = list(_STANDARD_REASONING_EFFORT_LEVELS)

    @pytest.mark.parametrize(
        "model_name",
        [
            # ── Native OpenAI Tier (Azure) ──────────────────────────────
            "Azure/GPT-5.4",
            "openai/gpt-5.4",
            "Azure/GPT-5.4-Mini",
            "openai/gpt-5.4-mini",
            # ── DeepSeek V4 ─────────────────────────────────────────────
            "DeepSeek/DeepSeek-V4-Pro",
            "NVIDIA/DeepSeek-V4-Pro",
            "DeepSeek/DeepSeek-V4-Flash",
            "NVIDIA/DeepSeek-V4-Flash",
            "OpenCodeZen/DeepSeek-V4-Flash-FREE",
            # ── NVIDIA & Moonshot backends ───────────────────────────────
            "OpenRouter/Nemotron-3-Ultra-550B-A55B",
            "OpenCodeZen/Nemotron-3-Ultra-FREE",
            # ── OpenCodeZen custom models ────────────────────────────────
            "OpenCodeZen/MiMo-V2.5-FREE",
            "OpenCodeZen/Minimax-M3-FREE",
            # ── Alibaba Qwen 3.6 MoE ─────────────────────────────────────
            "DGX/Qwen3.6-35B-A3B",
            # ── CodeFreedom internal fallbacks ───────────────────────────
            "CodeFreedom/Ultra",
            "CodeFreedom/Flash",
        ],
    )
    def test_known_models_with_gradient(self, model_name):
        assert _resolve_reasoning_effort(model_name) == self.STD

    @pytest.mark.parametrize(
        "model_name",
        [
            # ── Native OpenAI Tier ─────────────────────────────────────────
            "Azure/GPT-5.4-Nano",
            "openai/gpt-5.4-nano",
            # ── Zhipu AI GLM ───────────────────────────────────────────────
            "Azure/GLM-5.1",
            "NVIDIA/GLM-5.1",
            # ── NVIDIA & Moonshot backends ─────────────────────────────────
            "NVIDIA/Kimi-K2.6",
            "OpenCodeZen/Nemotron-3-Super-FREE",
            # ── OpenCodeZen custom models ──────────────────────────────────
            "OpenCodeZen/Big-Pickle",
            "OpenRouter/FreeRouter",
            # ── Alibaba Qwen 3.6 MoE ───────────────────────────────────────
            "DGX/Qwen3.6-27B",
            # ── CodeFreedom internal fallbacks ─────────────────────────────
            "CodeFreedom/Pro",
            "CodeFreedom/Air",
        ],
    )
    def test_known_models_only_none_returns_None(self, model_name):
        # ``None`` tells the caller to OMIT the field — not the same as
        # an empty list.  See the helper's docstring.
        assert _resolve_reasoning_effort(model_name) is None

    def test_unknown_models_return_standard_set(self):
        # Unknown models are treated permissively — get the full standard set.
        for model_name in [
            "some-org/Some-Random-Model",
            "totally/unknown",
            "foo",
            "NVIDIA/Step-3.7-Flash",  # in nvidia.yaml but not in rules
            "",
            "unknown",
        ]:
            assert _resolve_reasoning_effort(model_name) == self.STD

    def test_case_insensitive_match(self):
        # The lookup is case-insensitive on the substring pattern.
        assert _resolve_reasoning_effort("azure/gpt-5.4") == self.STD
        assert _resolve_reasoning_effort("AZURE/GPT-5.4-MINI") == self.STD
        # The "only none" branch is also case-insensitive.
        assert _resolve_reasoning_effort("azure/gpt-5.4-nano") is None

    def test_specific_pattern_wins_over_general(self):
        # gpt-5.4-nano must NOT fall through to the general gpt-5.4 rule.
        assert _resolve_reasoning_effort("Azure/GPT-5.4-Nano") is None
        # gpt-5.4-mini must NOT fall through to the general gpt-5.4 rule.
        assert _resolve_reasoning_effort("Azure/GPT-5.4-Mini") == self.STD
        # nemotron-3-super must NOT be shadowed by nemotron-3-ultra
        # (different substrings — verify the order in the rules table).
        assert _resolve_reasoning_effort("OpenCodeZen/Nemotron-3-Super-FREE") is None
        assert _resolve_reasoning_effort("OpenCodeZen/Nemotron-3-Ultra-FREE") == self.STD

    def test_returned_list_is_fresh(self):
        # Calling twice returns a new list each time (not a shared mutable).
        a = _resolve_reasoning_effort("Azure/GPT-5.4")
        b = _resolve_reasoning_effort("Azure/GPT-5.4")
        assert a == b
        a.append("xhigh-extra")
        assert b == self.STD


# ── _build_vscode_entry ──────────────────────────────────────────────────────


class TestBuildVscodeEntry:
    def test_top_level_shape(self):
        out = _build_vscode_entry("MyName", "http://h:4000/v1", [{"model_name": "m1"}])
        assert out["name"] == "MyName"
        assert out["vendor"] == "customendpoint"
        assert out["apiKey"] == _VSCODE_APIKEY_PLACEHOLDER
        assert out["apiType"] == "chat-completions"
        assert isinstance(out["models"], list)
        assert out["models"][0]["id"] == "m1"

    def test_empty_models_yields_empty_list(self):
        out = _build_vscode_entry("X", "http://h:4000/v1", [])
        assert out["models"] == []

    def test_uses_placeholder_for_apikey(self):
        out = _build_vscode_entry("X", "http://h:4000/v1", [])
        # Should be a VS Code input reference, not a real key.
        assert "${input:" in out["apiKey"]
        assert out["apiKey"].endswith("}")


# ── cmd_vscode_proxy_config (integration via mocks) ─────────────────────────────


def _args(
    host: str = "localhost",
    port: int = 4000,
    name: str = "CodeFreedom",
    out: Any = None,
) -> argparse.Namespace:
    return argparse.Namespace(host=host, port=port, name=name, out=out)


class TestCmdVscodeGenerate:
    def test_proxy_down_returns_1(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
        monkeypatch.setattr(
            "codefreedom.cli.vscode._check_proxy_live", lambda h, p: False
        )
        result = cmd_vscode_proxy_config(_args())
        assert result == 1

    def test_missing_master_key_returns_1(self, monkeypatch, tmp_path: Path, capsys):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
        monkeypatch.setattr(
            "codefreedom.cli.vscode._check_proxy_live", lambda h, p: True
        )
        result = cmd_vscode_proxy_config(_args())
        assert result == 1
        # Error message names the env file.
        captured = capsys.readouterr()
        assert "LITELLM_MASTER_KEY" in captured.err

    def test_401_from_proxy_returns_1(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
        monkeypatch.setattr(
            "codefreedom.cli.vscode._check_proxy_live", lambda h, p: True
        )

        def boom(h, p, k, *, timeout=10.0):
            raise urllib.error.HTTPError(
                "http://h:4000/v1/model/info", 401, "Unauthorized", {}, None
            )

        monkeypatch.setattr("codefreedom.cli.vscode._fetch_model_info", boom)
        result = cmd_vscode_proxy_config(_args())
        assert result == 1

    def test_500_from_proxy_returns_1(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
        monkeypatch.setattr(
            "codefreedom.cli.vscode._check_proxy_live", lambda h, p: True
        )

        def boom(h, p, k, *, timeout=10.0):
            raise urllib.error.HTTPError(
                "http://h:4000/v1/model/info", 500, "Server Error", {}, None
            )

        monkeypatch.setattr("codefreedom.cli.vscode._fetch_model_info", boom)
        result = cmd_vscode_proxy_config(_args())
        assert result == 1

    def test_network_failure_returns_1(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
        monkeypatch.setattr(
            "codefreedom.cli.vscode._check_proxy_live", lambda h, p: True
        )

        def boom(h, p, k, *, timeout=10.0):
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr("codefreedom.cli.vscode._fetch_model_info", boom)
        result = cmd_vscode_proxy_config(_args())
        assert result == 1

    def test_invalid_json_returns_1(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
        monkeypatch.setattr(
            "codefreedom.cli.vscode._check_proxy_live", lambda h, p: True
        )

        def boom(h, p, k, *, timeout=10.0):
            raise ValueError("bad response")

        monkeypatch.setattr("codefreedom.cli.vscode._fetch_model_info", boom)
        result = cmd_vscode_proxy_config(_args())
        assert result == 1

    def test_happy_path_prints_to_stdout(self, monkeypatch, tmp_path: Path, capsys):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
        monkeypatch.setattr(
            "codefreedom.cli.vscode._check_proxy_live", lambda h, p: True
        )
        monkeypatch.setattr(
            "codefreedom.cli.vscode._fetch_model_info",
            lambda h, p, k, *, timeout=10.0: [
                {
                    "model_name": "model-a",
                    "model_info": {
                        "supports_vision": True,
                        "supported_openai_params": ["tools"],
                        "max_input_tokens": 32000,
                        "max_output_tokens": 4000,
                    },
                },
                {"model_name": "model-b"},
            ],
        )

        result = cmd_vscode_proxy_config(
            _args(host="example.lan", port=5000, name="MyCo")
        )
        assert result == 0

        captured = capsys.readouterr()
        # Stdout is the JSON entry
        payload = json.loads(captured.out)
        assert payload["name"] == "MyCo"
        assert payload["vendor"] == "customendpoint"
        assert payload["apiKey"] == _VSCODE_APIKEY_PLACEHOLDER
        assert payload["apiType"] == "chat-completions"
        assert len(payload["models"]) == 2
        assert payload["models"][0]["id"] == "model-a"
        assert payload["models"][0]["url"] == "http://example.lan:5000/v1"
        assert payload["models"][0]["toolCalling"] is True
        assert payload["models"][0]["vision"] is True
        assert payload["models"][0]["maxInputTokens"] == 32000
        assert payload["models"][0]["maxOutputTokens"] == 4000
        # model-b has no capabilities — vision/tokens fall back to defaults,
        # but toolCalling is always True (see _model_to_vscode_entry docstring).
        assert payload["models"][1]["toolCalling"] is True
        assert payload["models"][1]["vision"] is False
        assert payload["models"][1]["maxInputTokens"] == 128000
        assert payload["models"][1]["maxOutputTokens"] == 16000

    def test_happy_path_writes_to_out_file(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
        monkeypatch.setattr(
            "codefreedom.cli.vscode._check_proxy_live", lambda h, p: True
        )
        monkeypatch.setattr(
            "codefreedom.cli.vscode._fetch_model_info",
            lambda h, p, k, *, timeout=10.0: [{"model_name": "m1"}],
        )

        out_file = tmp_path / "out.json"
        result = cmd_vscode_proxy_config(
            _args(host="h", port=4000, name="X", out=str(out_file))
        )
        assert result == 0
        assert out_file.exists()
        payload = json.loads(out_file.read_text())
        assert payload["name"] == "X"
        assert payload["models"][0]["id"] == "m1"

    def test_empty_models_succeeds(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
        monkeypatch.setattr(
            "codefreedom.cli.vscode._check_proxy_live", lambda h, p: True
        )
        monkeypatch.setattr(
            "codefreedom.cli.vscode._fetch_model_info",
            lambda h, p, k, *, timeout=10.0: [],
        )

        result = cmd_vscode_proxy_config(_args())
        assert result == 0
