"""Pure-logic helpers for VS Code proxy config.

Tests transform functions that take inputs and return outputs with no I/O.
"""

from __future__ import annotations

import pytest

from codefreedom.cli.vscode import (
    _STANDARD_REASONING_EFFORT_LEVELS,
    _VSCODE_APIKEY_PLACEHOLDER,
    _build_vscode_entry,
    _deduplicate_models,
    _model_to_vscode_entry,
    _resolve_model_id,
    _resolve_reasoning_effort,
)

pytestmark = pytest.mark.unit

# ── _resolve_model_id ────────────────────────────────────────────────────────


class TestResolveModelId:
    def test_uses_model_name(self):
        assert _resolve_model_id({"model_name": "gpt-4"}) == "gpt-4"

    def test_falls_back_to_model_info_id(self):
        assert _resolve_model_id({"model_info": {"id": "from-info"}}) == "from-info"

    def test_unknown_when_no_identifier(self):
        assert _resolve_model_id({}) == "unknown"

    def test_prefers_model_name_over_info_id(self):
        assert (
            _resolve_model_id(
                {
                    "model_name": "name-wins",
                    "model_info": {"id": "info-id"},
                }
            )
            == "name-wins"
        )


# ── _deduplicate_models ──────────────────────────────────────────────────────


class TestDeduplicateModels:
    def test_no_dupes_preserves_order(self):
        models = [
            {"model_name": "a"},
            {"model_name": "b"},
            {"model_name": "c"},
        ]
        out = _deduplicate_models(models)
        assert [m["model_name"] for m in out] == ["a", "b", "c"]

    def test_removes_duplicate_model_name(self):
        models = [
            {"model_name": "gpt-4", "model_info": {"supports_vision": True}},
            {"model_name": "gpt-4", "model_info": {}},
            {"model_name": "claude-3"},
        ]
        out = _deduplicate_models(models)
        assert len(out) == 2
        assert out[0]["model_name"] == "gpt-4"
        assert out[1]["model_name"] == "claude-3"

    def test_prefers_richer_model_info(self):
        models = [
            {"model_name": "m1", "model_info": {"a": 1}},
            {"model_name": "m1", "model_info": {"a": 1, "b": 2, "c": 3}},
        ]
        out = _deduplicate_models(models)
        assert len(out) == 1
        assert len(out[0]["model_info"]) == 3

    def test_preserves_first_seen_order(self):
        models = [
            {"model_name": "z"},
            {"model_name": "a"},
            {"model_name": "z"},
            {"model_name": "m"},
        ]
        out = _deduplicate_models(models)
        assert [m["model_name"] for m in out] == ["z", "a", "m"]


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
        assert out["toolCalling"] is True
        assert out["vision"] is False
        assert out["maxInputTokens"] == 128000
        assert out["maxOutputTokens"] == 16000
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
        assert out["supportsReasoningEffort"] == self.STD

    def test_tool_calling_always_true_even_when_proxy_says_no(self):
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
        assert out["toolCalling"] is True
        assert out["vision"] is False
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
        out = _model_to_vscode_entry({"model_name": "Azure/GPT-5.4"}, self.BASE_URL)
        assert out["supportsReasoningEffort"] == self.STD

    def test_model_with_any_name_emits_list(self):
        for name in (
            "Azure/GPT-5.4",
            "Azure/GPT-5.4-Nano",
            "NVIDIA/GLM-5.1",
            "NVIDIA/Kimi-K2.6",
            "DGX/Qwen3.6-27B",
            "CodeFreedom/Pro",
            "CodeFreedom/Air",
            "OpenCodeZen/Big-Pickle",
            "OpenRouter/FreeRouter",
        ):
            out = _model_to_vscode_entry({"model_name": name}, self.BASE_URL)
            assert out["supportsReasoningEffort"] == self.STD

    def test_route_image_request_enables_vision(self):
        route_models = {"MiMo-V2.5", "DeepSeek-V4-Flash"}
        out = _model_to_vscode_entry(
            {
                "model_name": "MiMo-V2.5",
                "model_info": {"supports_vision": False},
            },
            self.BASE_URL,
            route_image_models=route_models,
        )
        assert out["vision"] is True

    def test_route_image_request_not_in_set_no_override(self):
        route_models = {"MiMo-V2.5"}
        out = _model_to_vscode_entry(
            {
                "model_name": "Some-Other-Model",
                "model_info": {"supports_vision": False},
            },
            self.BASE_URL,
            route_image_models=route_models,
        )
        assert out["vision"] is False

    def test_route_image_request_none_set_no_override(self):
        out = _model_to_vscode_entry(
            {
                "model_name": "MiMo-V2.5",
                "model_info": {"supports_vision": False},
            },
            self.BASE_URL,
            route_image_models=None,
        )
        assert out["vision"] is False

    def test_vision_true_from_model_info_preserved_even_with_route_set(self):
        route_models = set()
        out = _model_to_vscode_entry(
            {
                "model_name": "Kimi-K2.6",
                "model_info": {"supports_vision": True},
            },
            self.BASE_URL,
            route_image_models=route_models,
        )
        assert out["vision"] is True


# ── _resolve_reasoning_effort ────────────────────────────────────────────────


class TestResolveReasoningEffort:
    STD = list(_STANDARD_REASONING_EFFORT_LEVELS)

    @pytest.mark.parametrize(
        "model_name",
        [
            "Azure/GPT-5.4",
            "openai/gpt-5.4",
            "Azure/GPT-5.4-Mini",
            "openai/gpt-5.4-mini",
            "Azure/GPT-5.4-Nano",
            "openai/gpt-5.4-nano",
            "DeepSeek/DeepSeek-V4-Pro",
            "NVIDIA/DeepSeek-V4-Pro",
            "DeepSeek/DeepSeek-V4-Flash",
            "NVIDIA/DeepSeek-V4-Flash",
            "OpenCodeZen/DeepSeek-V4-Flash-FREE",
            "OpenRouter/Nemotron-3-Ultra-550B-A55B",
            "OpenCodeZen/Nemotron-3-Ultra-FREE",
            "OpenCodeZen/Nemotron-3-Super-FREE",
            "OpenCodeZen/MiMo-V2.5-FREE",
            "OpenCodeZen/Minimax-M3-FREE",
            "DGX/Qwen3.6-35B-A3B",
            "DGX/Qwen3.6-27B",
            "NVIDIA/GLM-5.1",
            "NVIDIA/Kimi-K2.6",
            "OpenCodeZen/Big-Pickle",
            "OpenRouter/FreeRouter",
            "CodeFreedom/Ultra",
            "CodeFreedom/Flash",
            "CodeFreedom/Pro",
            "CodeFreedom/Air",
            "Azure/GLM-5.1",
            "some-org/Some-Random-Model",
            "totally/unknown",
            "foo",
            "",
            "unknown",
        ],
    )
    def test_every_model_gets_standard_set(self, model_name):
        assert _resolve_reasoning_effort(model_name) == self.STD

    def test_case_insensitive(self):
        assert _resolve_reasoning_effort("azure/gpt-5.4") == self.STD
        assert _resolve_reasoning_effort("AZURE/GPT-5.4-MINI") == self.STD
        assert _resolve_reasoning_effort("azure/gpt-5.4-nano") == self.STD
        assert _resolve_reasoning_effort("Azure/GPT-5.4-Nano") == self.STD
        assert _resolve_reasoning_effort("Azure/GPT-5.4-Mini") == self.STD

    def test_returned_list_is_fresh(self):
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
        assert "${input:" in out["apiKey"]
        assert out["apiKey"].endswith("}")

    def test_deduplicates_duplicate_model_names(self):
        models = [
            {"model_name": "gpt-4", "model_info": {"supports_vision": True}},
            {"model_name": "gpt-4", "model_info": {}},
            {"model_name": "claude-3-opus"},
        ]
        out = _build_vscode_entry("CF", "http://h:4000/v1", models)
        ids = [m["id"] for m in out["models"]]
        assert len(ids) == 2
        assert ids == ["gpt-4", "claude-3-opus"]

    def test_deduplication_prefers_richer_model_info(self):
        models = [
            {"model_name": "m1", "model_info": {"a": 1}},
            {"model_name": "m1", "model_info": {"a": 1, "b": 2, "c": 3}},
        ]
        out = _build_vscode_entry("CF", "http://h:4000/v1", models)
        assert len(out["models"]) == 1
        entry = out["models"][0]
        assert entry["id"] == "m1"
        assert entry["vision"] is False
