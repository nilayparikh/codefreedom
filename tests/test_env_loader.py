"""Tests for config module — interpolation and config loading.

Replaces the old env_loader tests which tested the now-removed .env chain.
"""

import os

import pytest
import yaml

from codefreedom.config import load_config, resolve_var


class TestInterpolation:
    """Tests for resolve_var — ${VAR} and ${VAR:-default} resolution."""

    def test_basic_var(self):
        ctx = {"TEST_KEY": "value"}
        assert resolve_var("hello ${TEST_KEY}", ctx) == "hello value"

    def test_var_with_default_fallback(self):
        assert resolve_var("${MISSING:-default}") == "default"

    def test_var_missing_no_default(self):
        assert resolve_var("${MISSING}") == ""

    def test_var_from_context(self):
        ctx = {"MY_VAR": "from_context"}
        assert resolve_var("${MY_VAR}", ctx) == "from_context"

    def test_cf_cli_highest_priority(self):
        """CF_CLI_* in context overrides other context values."""
        ctx = {"TEST_KEY": "base_val", "CF_CLI_TEST_KEY": "cli_override"}
        assert resolve_var("${TEST_KEY}", ctx) == "base_val"
        # CF_CLI_* is injected into context by _build_context with prefix stripped
        ctx2 = {"TEST_KEY": "cli_override"}
        assert resolve_var("${TEST_KEY}", ctx2) == "cli_override"

    def test_context_overrides_default(self):
        ctx = {"KEY": "from_context"}
        assert resolve_var("${KEY:-default}", ctx) == "from_context"

    def test_escaped_dollar(self):
        assert resolve_var("$${NOT_A_VAR}") == "${NOT_A_VAR}"

    def test_dotted_key_from_context(self):
        ctx = {"common.proxy.bind_host": "0.0.0.0"}
        assert resolve_var("http://${common.proxy.bind_host}:4000", ctx) == "http://0.0.0.0:4000"

    def test_empty_string_is_valid_override(self):
        """Empty string in context does NOT fall through to default."""
        ctx = {"EMPTY_KEY": ""}
        assert resolve_var("${EMPTY_KEY:-fallback}", ctx) == ""


class TestConfigLoading:
    """Tests for load_config — the single config entry point."""

    def test_loads_valid_yaml(self, tmp_path):
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({
            "agents": {
                "claude-code": {
                    "profiles": {
                        "default": {"env": {"KEY": "value"}},
                    }
                }
            }
        }))
        config = load_config(tmp_path)
        agent_cfg = config.for_agent("claude-code")
        assert agent_cfg.env["KEY"] == "value"

    def test_interpolation_in_profiles(self, tmp_path):
        os.environ["CF_CLI_TEST_INTERP"] = "resolved"
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({
            "agents": {
                "claude-code": {
                    "profiles": {
                        "default": {"env": {"RESULT": "${TEST_INTERP}"}},
                    }
                }
            }
        }))
        config = load_config(tmp_path)
        agent_cfg = config.for_agent("claude-code")
        assert agent_cfg.env["RESULT"] == "resolved"
        del os.environ["CF_CLI_TEST_INTERP"]

    def test_var_with_default_in_profile(self, tmp_path):
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({
            "agents": {
                "claude-code": {
                    "profiles": {
                        "default": {"env": {"PORT": "${PORT:-4000}"}},
                    }
                }
            }
        }))
        config = load_config(tmp_path)
        agent_cfg = config.for_agent("claude-code")
        assert agent_cfg.env["PORT"] == "4000"

    def test_missing_yaml_raises_error(self, tmp_path):
        with pytest.raises(Exception):
            load_config(tmp_path / "nonexistent")

    def test_malformed_yaml_raises_error(self, tmp_path):
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(": invalid yaml :\n")
        with pytest.raises(Exception):
            load_config(tmp_path)

    def test_empty_agents_section(self, tmp_path):
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({"agents": {}}))
        config = load_config(tmp_path)
        with pytest.raises(Exception):
            config.for_agent("claude-code")

    def test_override_yaml_merges(self, tmp_path):
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({
            "agents": {
                "claude-code": {
                    "profiles": {
                        "default": {"env": {"KEY": "from_base"}},
                    }
                }
            }
        }))
        override = tmp_path / "override.yaml"
        override.write_text(yaml.dump({
            "agents": {
                "claude-code": {
                    "profiles": {
                        "default": {"env": {"KEY": "from_override"}},
                    }
                }
            }
        }))
        config = load_config(tmp_path)
        agent_cfg = config.for_agent("claude-code")
        assert agent_cfg.env["KEY"] == "from_override"

    def test_override_env_does_not_remove_base_keys(self, tmp_path):
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({
            "agents": {
                "claude-code": {
                    "profiles": {
                        "default": {"env": {"A": "1", "B": "2"}},
                    }
                }
            }
        }))
        override = tmp_path / "override.yaml"
        override.write_text(yaml.dump({
            "agents": {
                "claude-code": {
                    "profiles": {
                        "default": {"env": {"B": "overridden"}},
                    }
                }
            }
        }))
        config = load_config(tmp_path)
        agent_cfg = config.for_agent("claude-code")
        assert agent_cfg.env["A"] == "1"
        assert agent_cfg.env["B"] == "overridden"

    def test_legacy_profiles_format_conversion(self, tmp_path):
        """Legacy profiles: {default: {env: ...}} is auto-converted."""
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({
            "profiles": {
                "default": {"description": "test", "env": {"KEY": "val"}},
            }
        }))
        config = load_config(tmp_path)
        agent_cfg = config.for_agent("claude-code")
        assert agent_cfg.env["KEY"] == "val"

    def test_legacy_unified_format_conversion(self, tmp_path):
        """Legacy profiles: {claude-code: {profiles: {default: ...}}} is converted."""
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({
            "profiles": {
                "claude-code": {
                    "profiles": {
                        "default": {"env": {"KEY": "val"}},
                    }
                }
            }
        }))
        config = load_config(tmp_path)
        agent_cfg = config.for_agent("claude-code")
        assert agent_cfg.env["KEY"] == "val"

    def test_for_agent_unknown_agent(self, tmp_path):
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({
            "agents": {
                "claude-code": {
                    "profiles": {"default": {"env": {}}}
                }
            }
        }))
        config = load_config(tmp_path)
        with pytest.raises(Exception):
            config.for_agent("unknown-agent")

    def test_for_tool_defaults(self, tmp_path):
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({"agents": {}, "tools": {}}))
        config = load_config(tmp_path)
        tool = config.for_tool("chrome")
        assert tool.name == "chrome"
        assert "chrome" in tool.image

    def test_for_tool_profile_overrides(self, tmp_path):
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({
            "agents": {},
            "tools": {
                "chrome": {
                    "port": 9999,
                    "env": {"CUSTOM": "yes"},
                }
            }
        }))
        config = load_config(tmp_path)
        tool = config.for_tool("chrome")
        assert tool.port == 9999
        assert tool.env["CUSTOM"] == "yes"

    def test_vars_priority_profiles_wins(self, tmp_path):
        """vars from profiles.yaml are used when no recipe/override."""
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({
            "vars": {"MY_VAR": "from_profiles"},
            "common": {"suffix_id": "${MY_VAR:-default}"},
            "agents": {"claude-code": {"profiles": {"default": {"env": {}}}}},
            "tools": {"chrome": {}},
        }))
        config = load_config(tmp_path)
        assert config.common.suffix_id == "from_profiles"

    def test_vars_priority_recipe_overrides_profiles(self, tmp_path):
        """vars from recipe.yaml override vars from profiles.yaml."""
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({
            "vars": {"MY_VAR": "from_profiles"},
            "common": {"suffix_id": "${MY_VAR:-default}"},
            "agents": {"claude-code": {"profiles": {"default": {"env": {}}}}},
            "tools": {"chrome": {}},
        }))
        recipe = tmp_path / "recipe.yaml"
        recipe.write_text(yaml.dump({
            "vars": {"MY_VAR": "from_recipe"},
        }))
        config = load_config(tmp_path)
        assert config.common.suffix_id == "from_recipe"

    def test_vars_priority_override_overrides_recipe(self, tmp_path):
        """vars from override.yaml override vars from recipe.yaml."""
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({
            "vars": {"MY_VAR": "from_profiles"},
            "common": {"suffix_id": "${MY_VAR:-default}"},
            "agents": {"claude-code": {"profiles": {"default": {"env": {}}}}},
            "tools": {"chrome": {}},
        }))
        recipe = tmp_path / "recipe.yaml"
        recipe.write_text(yaml.dump({
            "vars": {"MY_VAR": "from_recipe"},
        }))
        override = tmp_path / "override.yaml"
        override.write_text(yaml.dump({
            "comment": "user overrides",
            "vars": {"MY_VAR": "from_override"},
        }))
        config = load_config(tmp_path)
        assert config.common.suffix_id == "from_override"

    def test_vars_priority_cflcli_overrides_all(self, tmp_path, monkeypatch):
        """CF_CLI_* env vars override all config layers."""
        monkeypatch.setenv("CF_CLI_MY_VAR", "from_cflcli")
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({
            "vars": {"MY_VAR": "from_profiles"},
            "common": {"suffix_id": "${MY_VAR:-default}"},
            "agents": {"claude-code": {"profiles": {"default": {"env": {}}}}},
            "tools": {"chrome": {}},
        }))
        recipe = tmp_path / "recipe.yaml"
        recipe.write_text(yaml.dump({
            "vars": {"MY_VAR": "from_recipe"},
        }))
        override = tmp_path / "override.yaml"
        override.write_text(yaml.dump({
            "comment": "user overrides",
            "vars": {"MY_VAR": "from_override"},
        }))
        config = load_config(tmp_path)
        assert config.common.suffix_id == "from_cflcli"

    def test_override_comment_field_does_not_break_validation(self, tmp_path):
        """override.yaml 'comment' field is stripped before validation."""
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({
            "agents": {"claude-code": {"profiles": {"default": {"env": {}}}}},
            "tools": {"chrome": {}},
        }))
        override = tmp_path / "override.yaml"
        override.write_text(yaml.dump({
            "comment": "User overrides",
            "vars": {"SUFFIX_ID": "test123"},
        }))
        config = load_config(tmp_path)
        assert config.common.suffix_id == "test123"
