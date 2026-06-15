"""Tests for the reasoning-efforts mapping plugin v2.

Exercises rule-based mapping, thinking_budget, auto default, and
warn-once behaviour without requiring a running LiteLLM instance.
"""

from __future__ import annotations


import asyncio
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.integration

_project_root = Path(__file__).resolve().parent.parent
_src = str(_project_root / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

_plugin_path = str(
    _project_root / "docker" / "litellm" / "plugins" / "reasoning_efforts_mapping.py"
)
_spec = importlib.util.spec_from_file_location(
    "plugins.reasoning_efforts_mapping", _plugin_path
)
assert _spec is not None, f"Plugin not found at {_plugin_path}"
_plugin = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_plugin)

ReasoningEffortsMappingLogger = _plugin.ReasoningEffortsMappingLogger
normalise = _plugin.normalise


# ============================================================================
# Helpers
# ============================================================================


def _yaml_file(data: dict) -> str:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
    return f.name


def _provider_yaml_dir(model_entries: list) -> str:
    d = tempfile.mkdtemp()
    yp = os.path.join(d, "provider.yaml")
    with open(yp, "w") as f:
        yaml.dump({"model_list": model_entries}, f)
    return d


# ============================================================================
# normalise (v2 — pass-through, no scale collapse)
# ============================================================================


class TestNormalise:
    def test_none(self):
        assert normalise(None) is None

    def test_string(self):
        assert normalise("High") == "high"

    def test_non_string(self):
        assert normalise(42) is None


# ============================================================================
# auto default — pure field rename, no remap
# ============================================================================


class TestAuto:
    def test_rename_output_config_to_reasoning_effort(self):
        inst = ReasoningEffortsMappingLogger(config_path="/nonexistent.yaml")
        out = inst._translate(
            {"output_config": {"effort": "high"}},
            model="Azure/GPT-5.4",
            custom_provider="azure",
        )
        assert out.get("reasoning_effort") == "high"
        assert "output_config" not in out

    def test_rename_reasoning_effort_to_output_config(self):
        inst = ReasoningEffortsMappingLogger(config_path="/nonexistent.yaml")
        out = inst._translate(
            {"reasoning_effort": "medium"},
            model="claude-opus-4-8",
            custom_provider="anthropic",
        )
        assert out["output_config"]["effort"] == "medium"
        assert "reasoning_effort" not in out

    def test_no_effort_field_passthrough(self):
        inst = ReasoningEffortsMappingLogger(config_path="/nonexistent.yaml")
        out = inst._translate(
            {"messages": [{"role": "user", "content": "hi"}]},
            model="some-model",
            custom_provider=None,
        )
        assert out == {"messages": [{"role": "user", "content": "hi"}]}

    def test_same_field_no_rename(self):
        inst = ReasoningEffortsMappingLogger(config_path="/nonexistent.yaml")
        out = inst._translate(
            {"reasoning_effort": "low"},
            model="openai/some-model",
            custom_provider="openai",
        )
        assert out["reasoning_effort"] == "low"


# ============================================================================
# mapping rule
# ============================================================================


class TestMapping:
    def test_named_rule_via_model_info(self):
        yp = _yaml_file(
            {
                "rules": {
                    "my-rule": {
                        "type": "mapping",
                        "output": "reasoning_effort",
                        "values": {"high": "xhigh", "xhigh": "xhigh", "max": "xhigh"},
                    }
                }
            }
        )
        inst = ReasoningEffortsMappingLogger(config_path=yp)
        out = inst._translate(
            {
                "reasoning_effort": "high",
                "litellm_params": {
                    "model_info": {
                        "codefreedom": {
                            "plugins": {"reasoning-efforts": {"rule": "my-rule"}}
                        }
                    }
                },
            },
            model="Azure/GPT-5.4",
            custom_provider="azure",
        )
        assert out["reasoning_effort"] == "xhigh"

    def test_inline_mapping(self):
        inst = ReasoningEffortsMappingLogger(config_path="/nonexistent.yaml")
        out = inst._translate(
            {
                "reasoning_effort": "high",
                "litellm_params": {
                    "model_info": {
                        "codefreedom": {
                            "plugins": {
                                "reasoning-efforts": {
                                    "type": "mapping",
                                    "output": "reasoning_effort",
                                    "values": {
                                        "high": "xhigh",
                                        "xhigh": "xhigh",
                                        "max": "xhigh",
                                    },
                                }
                            }
                        }
                    }
                },
            },
            model="Azure/GPT-5.4",
            custom_provider="azure",
        )
        assert out["reasoning_effort"] == "xhigh"

    def test_missing_value_drops(self):
        inst = ReasoningEffortsMappingLogger(config_path="/nonexistent.yaml")
        out = inst._translate(
            {
                "reasoning_effort": "medium",
                "litellm_params": {
                    "model_info": {
                        "codefreedom": {
                            "plugins": {
                                "reasoning-efforts": {
                                    "type": "mapping",
                                    "output": "reasoning_effort",
                                    "values": {"high": "xhigh"},
                                }
                            }
                        }
                    }
                },
            },
            model="some-model",
            custom_provider="openai",
        )
        assert "reasoning_effort" not in out
        assert "output_config" not in out

    def test_from_output_config_source(self):
        inst = ReasoningEffortsMappingLogger(config_path="/nonexistent.yaml")
        out = inst._translate(
            {
                "output_config": {"effort": "xhigh"},
                "litellm_params": {
                    "model_info": {
                        "codefreedom": {
                            "plugins": {
                                "reasoning-efforts": {
                                    "type": "mapping",
                                    "output": "reasoning_effort",
                                    "values": {"xhigh": "max", "max": "max"},
                                }
                            }
                        }
                    }
                },
            },
            model="DeepSeek/DeepSeek-V4-Flash",
            custom_provider="deepseek",
        )
        assert out["reasoning_effort"] == "max"
        assert "output_config" not in out

    def test_to_output_config_target(self):
        inst = ReasoningEffortsMappingLogger(config_path="/nonexistent.yaml")
        out = inst._translate(
            {
                "reasoning_effort": "high",
                "litellm_params": {
                    "model_info": {
                        "codefreedom": {
                            "plugins": {
                                "reasoning-efforts": {
                                    "type": "mapping",
                                    "output": "output_config",
                                    "values": {
                                        "high": "xhigh",
                                        "xhigh": "xhigh",
                                        "max": "xhigh",
                                    },
                                }
                            }
                        }
                    }
                },
            },
            model="claude-opus-4-8",
            custom_provider="anthropic",
        )
        assert out["output_config"]["effort"] == "xhigh"
        assert "reasoning_effort" not in out


# ============================================================================
# thinking_budget rule
# ============================================================================


class TestThinkingBudget:
    def test_sets_nested_field(self):
        inst = ReasoningEffortsMappingLogger(config_path="/nonexistent.yaml")
        out = inst._translate(
            {
                "reasoning_effort": "high",
                "litellm_params": {
                    "model_info": {
                        "codefreedom": {
                            "plugins": {
                                "reasoning-efforts": {
                                    "type": "thinking_budget",
                                    "field": "extra_body.max_thinking_tokens",
                                    "values": {
                                        "high": 8192,
                                        "xhigh": 16384,
                                        "max": 32768,
                                    },
                                }
                            }
                        }
                    }
                },
            },
            model="DGX/Qwen3.6-27B",
            custom_provider="openai",
        )
        assert out.get("extra_body", {}).get("max_thinking_tokens") == 8192

    def test_inline_thinking_budget(self):
        inst = ReasoningEffortsMappingLogger(config_path="/nonexistent.yaml")
        out = inst._translate(
            {
                "reasoning_effort": "medium",
                "litellm_params": {
                    "model_info": {
                        "codefreedom": {
                            "plugins": {
                                "reasoning-efforts": {
                                    "type": "thinking_budget",
                                    "field": "thinking_budget",
                                    "values": {"medium": 4096, "high": 8192},
                                }
                            }
                        }
                    }
                },
            },
            model="some-model",
            custom_provider="openai",
        )
        assert out["thinking_budget"] == 4096

    def test_missing_value_drops(self):
        inst = ReasoningEffortsMappingLogger(config_path="/nonexistent.yaml")
        out = inst._translate(
            {
                "reasoning_effort": "low",
                "litellm_params": {
                    "model_info": {
                        "codefreedom": {
                            "plugins": {
                                "reasoning-efforts": {
                                    "type": "thinking_budget",
                                    "field": "extra_body.budget",
                                    "values": {"high": 8192},
                                }
                            }
                        }
                    }
                },
            },
            model="some-model",
            custom_provider="openai",
        )
        assert "extra_body" not in out

    def test_dotted_path_creates_intermediate(self):
        d = {}
        ReasoningEffortsMappingLogger._set_nested(d, "a.b.c.d", 42)
        assert d == {"a": {"b": {"c": {"d": 42}}}}

    def test_no_effort_does_nothing(self):
        inst = ReasoningEffortsMappingLogger(config_path="/nonexistent.yaml")
        out = inst._translate(
            {
                "messages": [{"role": "user", "content": "hi"}],
                "litellm_params": {
                    "model_info": {
                        "codefreedom": {
                            "plugins": {
                                "reasoning-efforts": {
                                    "type": "thinking_budget",
                                    "field": "extra_body.budget",
                                    "values": {"high": 8192},
                                }
                            }
                        }
                    }
                },
            },
            model="some-model",
            custom_provider="openai",
        )
        assert "extra_body" not in out


# ============================================================================
# named rule resolution
# ============================================================================


class TestNamedRule:
    def test_resolves_by_name(self):
        yp = _yaml_file(
            {
                "rules": {
                    "my-mapping": {
                        "type": "mapping",
                        "output": "output_config",
                        "values": {"high": "xhigh", "xhigh": "xhigh", "max": "xhigh"},
                    }
                }
            }
        )
        inst = ReasoningEffortsMappingLogger(config_path=yp)
        out = inst._translate(
            {
                "reasoning_effort": "high",
                "litellm_params": {
                    "model_info": {
                        "codefreedom": {
                            "plugins": {"reasoning-efforts": {"rule": "my-mapping"}}
                        }
                    }
                },
            },
            model="some-model",
            custom_provider="anthropic",
        )
        assert out["output_config"]["effort"] == "xhigh"

    def test_missing_rule_falls_back_to_auto(self):
        yp = _yaml_file({"rules": {}})
        inst = ReasoningEffortsMappingLogger(config_path=yp)
        out = inst._translate(
            {
                "reasoning_effort": "high",
                "litellm_params": {
                    "model_info": {
                        "codefreedom": {
                            "plugins": {"reasoning-efforts": {"rule": "nonexistent"}}
                        }
                    }
                },
            },
            model="Azure/GPT-5.4",
            custom_provider="azure",
        )
        assert out["reasoning_effort"] == "high"

    def test_no_codefreedom_block_uses_auto(self):
        inst = ReasoningEffortsMappingLogger(config_path="/nonexistent.yaml")
        out = inst._translate(
            {
                "output_config": {"effort": "low"},
                "litellm_params": {"model_info": {}},
            },
            model="Azure/GPT-5.4",
            custom_provider="azure",
        )
        assert out["reasoning_effort"] == "low"
        assert "output_config" not in out


# ============================================================================
# provider inference
# ============================================================================


class TestInferProvider:
    @pytest.mark.parametrize(
        "model, expected",
        [
            ("DeepSeek/DeepSeek-V4-Pro", "deepseek"),
            ("Azure/GPT-5.4", "azure"),
            ("claude-opus-4-8", "anthropic"),
            ("bedrock/us.anthropic.claude-sonnet-4-6", "bedrock"),
            ("openai/gpt-5.4", "openai"),
            ("NVIDIA/DeepSeek-V4-Flash", "nvidia"),
            ("OCZ/MNP/MiMo-V2.5-FREE", "opencode-zen"),
            ("unknown-model", None),
            (None, None),
            ("", None),
        ],
    )
    def test_provider_inference(self, model, expected):
        assert ReasoningEffortsMappingLogger._infer_provider(model) == expected


# ============================================================================
# model_info cache
# ============================================================================


class TestModelInfoCache:
    def test_loads_from_provider_yaml(self):
        d = _provider_yaml_dir(
            [
                {
                    "model_name": "Test/Model",
                    "model_info": {
                        "codefreedom": {
                            "plugins": {"reasoning-efforts": {"rule": "foo"}}
                        }
                    },
                }
            ]
        )
        inst = ReasoningEffortsMappingLogger(
            config_path="/nonexistent.yaml", proxy_config_dir=d
        )
        mi = inst._get_model_info("Test/Model", None)
        assert mi["codefreedom"]["plugins"]["reasoning-efforts"]["rule"] == "foo"

    def test_unknown_model_returns_empty(self):
        d = _provider_yaml_dir([])
        inst = ReasoningEffortsMappingLogger(
            config_path="/nonexistent.yaml", proxy_config_dir=d
        )
        mi = inst._get_model_info("Unknown/Model", None)
        assert mi == {}


# ============================================================================
# warn-once
# ============================================================================


class TestWarnOnce:
    def test_warns_only_once(self):
        inst = ReasoningEffortsMappingLogger(config_path="/nonexistent.yaml")
        kwargs = {
            "reasoning_effort": "medium",
            "litellm_params": {
                "model_info": {
                    "codefreedom": {
                        "plugins": {
                            "reasoning-efforts": {
                                "type": "mapping",
                                "output": "reasoning_effort",
                                "values": {"high": "xhigh"},
                            }
                        }
                    }
                }
            },
        }
        inst._translate(dict(kwargs), model="X", custom_provider="openai")
        n1 = len(inst._warned)
        inst._translate(dict(kwargs), model="X", custom_provider="openai")
        assert len(inst._warned) == n1


# ============================================================================
# hook signatures
# ============================================================================


class TestHooks:
    def test_pre_request_hook_returns_dict(self):
        inst = ReasoningEffortsMappingLogger(config_path="/nonexistent.yaml")
        result = asyncio.run(
            inst.async_pre_request_hook(
                model="DeepSeek/DeepSeek-V4-Flash",
                _messages=[],
                kwargs={
                    "output_config": {"effort": "xhigh"},
                    "litellm_params": {
                        "model_info": {
                            "codefreedom": {
                                "plugins": {
                                    "reasoning-efforts": {
                                        "type": "mapping",
                                        "output": "reasoning_effort",
                                        "values": {"xhigh": "max", "max": "max"},
                                    }
                                }
                            }
                        }
                    },
                },
            )
        )
        assert result is not None
        assert result["reasoning_effort"] == "max"

    def test_log_pre_api_call_mutates_in_place(self):
        inst = ReasoningEffortsMappingLogger(config_path="/nonexistent.yaml")
        kwargs = {
            "reasoning_effort": "low",
            "litellm_params": {
                "model_info": {
                    "codefreedom": {
                        "plugins": {
                            "reasoning-efforts": {
                                "type": "thinking_budget",
                                "field": "budget",
                                "values": {"low": 512, "medium": 2048},
                            }
                        }
                    }
                }
            },
        }
        asyncio.run(inst.async_log_pre_api_call("m", [], kwargs))
        assert kwargs.get("budget") == 512


# ============================================================================
# YAML round-trip
# ============================================================================


class TestYAMLRoundtrip:
    def test_loads_and_applies_from_file(self):
        yp = _yaml_file(
            {
                "rules": {
                    "test-rule": {
                        "type": "mapping",
                        "output": "reasoning_effort",
                        "values": {
                            "low": "low",
                            "medium": "medium",
                            "high": "xhigh",
                            "xhigh": "xhigh",
                            "max": "xhigh",
                        },
                    }
                }
            }
        )
        inst = ReasoningEffortsMappingLogger(config_path=yp)
        out = inst._translate(
            {
                "output_config": {"effort": "high"},
                "litellm_params": {
                    "model_info": {
                        "codefreedom": {
                            "plugins": {"reasoning-efforts": {"rule": "test-rule"}}
                        }
                    }
                },
            },
            model="some-model",
            custom_provider="openai",
        )
        assert out["reasoning_effort"] == "xhigh"
        assert "output_config" not in out
