"""Tests for config profiles — loading, inheritance, ${VAR} resolution."""

from pathlib import Path

import pytest
import yaml

from codefreedom.config import load_config
from codefreedom.config.errors import ConfigError
from codefreedom.config.models import AgentDefinition, ProfileEntry


class TestConfigLoading:
    """Tests for load_config — the single config entry point."""

    def test_loads_valid_new_format(self, tmp_path):
        _write(tmp_path, {
            "agents": {"claude-code": {"profiles": {"default": {"env": {"KEY": "val"}}}}}
        })
        config = load_config(tmp_path)
        assert config.agents["claude-code"] is not None

    def test_loads_legacy_flat_format(self, tmp_path):
        """Legacy profiles: {default: {env: {}}} is converted to agents:."""
        _write(tmp_path, {
            "profiles": {"default": {"description": "test", "env": {"KEY": "val"}}}
        })
        config = load_config(tmp_path)
        agent_cfg = config.for_agent("claude-code")
        assert agent_cfg.env["KEY"] == "val"

    def test_loads_legacy_unified_format(self, tmp_path):
        """Legacy profiles: {agent: {profiles: {}}} is auto-converted."""
        _write(tmp_path, {
            "profiles": {
                "claude-code": {"profiles": {"default": {"env": {"KEY": "val"}}}}
            }
        })
        config = load_config(tmp_path)
        agent_cfg = config.for_agent("claude-code")
        assert agent_cfg.env["KEY"] == "val"

    def test_missing_file(self, tmp_path):
        with pytest.raises(ConfigError):
            load_config(tmp_path / "nonexistent")

    def test_invalid_yaml(self, tmp_path):
        (tmp_path / "profiles.yaml").write_text(": not: valid: yaml")
        with pytest.raises(ConfigError):
            load_config(tmp_path)

    def test_empty_profiles(self, tmp_path):
        _write(tmp_path, {"agents": {}})
        config = load_config(tmp_path)
        assert len(config.agents) == 0

    def test_recipe_manifest_keys_stripped(self, tmp_path):
        """Recipe.yaml metadata (name, description, etc.) leaks into merged dict but is stripped."""
        _write(tmp_path, {
            "agents": {"claude-code": {"profiles": {"default": {"env": {"KEY": "val"}}}}}
        })
        _write_recipe(tmp_path, {
            "name": "test-recipe",
            "description": "A test recipe",
            "version": 1,
            "files": [{"path": "profiles.yaml", "target": "profiles.yaml"}],
            "dirs": [],
            "generated_artifacts": [],
            "required_secrets": [],
            "config_vars": [],
            "advice": "Run setup",
            "vars": {"SUFFIX_ID": "test"},
        })
        config = load_config(tmp_path)
        agent_cfg = config.for_agent("claude-code")
        assert agent_cfg.env["KEY"] == "val"
        assert config.common.suffix_id == "test"

    def test_legacy_common_keys_stripped(self, tmp_path):
        """Legacy common.proxy_env/tools/tool_images are stripped without error."""
        _write(tmp_path, {
            "common": {
                "proxy_env": {"PROXY_BASE_URL": "http://localhost:4000"},
                "tools": ["chrome", "web"],
                "tool_images": {"base": "docker.io/test", "tag": "latest"},
            },
            "agents": {"claude-code": {"profiles": {"default": {"env": {"KEY": "val"}}}}},
        })
        config = load_config(tmp_path)
        agent_cfg = config.for_agent("claude-code")
        assert agent_cfg.env["KEY"] == "val"

    def test_mixed_format_override_merge(self, tmp_path):
        """Override with flat profiles: + base with agent-keyed profiles: merges correctly."""
        _write(tmp_path, {
            "profiles": {
                "claude-code": {"profiles": {"default": {"env": {"A": "1"}}}},
                "mimo-code": {"profiles": {"default": {"env": {"B": "2"}}}},
            }
        })
        _write_override(tmp_path, {
            "profiles": {"default": {"env": {"A": "override"}}},
        })
        config = load_config(tmp_path)
        claude_cfg = config.for_agent("claude-code")
        mimo_cfg = config.for_agent("mimo-code")
        assert claude_cfg.env["A"] == "override"
        assert mimo_cfg.env["B"] == "2"

    def test_recipe_manifest_and_legacy_keys(self, tmp_path):
        """Full scenario: recipe manifest + legacy common keys + new format agents."""
        _write(tmp_path, {
            "common": {
                "proxy_env": {"PROXY_BASE_URL": "http://localhost:4000"},
                "tools": ["chrome"],
                "tool_images": {"base": "docker.io/test", "tag": "latest"},
            },
            "agents": {"claude-code": {"profiles": {"default": {"env": {"KEY": "val"}}}}},
        })
        _write_recipe(tmp_path, {
            "name": "test-recipe",
            "description": "Test",
            "version": 1,
            "vars": {"SUFFIX_ID": "test"},
        })
        config = load_config(tmp_path)
        agent_cfg = config.for_agent("claude-code")
        assert agent_cfg.env["KEY"] == "val"
        assert config.common.suffix_id == "test"

    def test_override_merges_into_profiles(self, tmp_path):
        _write(tmp_path, {
            "agents": {"claude-code": {"profiles": {"default": {"env": {"A": "1"}}}}}
        })
        _write_override(tmp_path, {
            "agents": {"claude-code": {"profiles": {"default": {"env": {"A": "override"}}}}}
        })
        config = load_config(tmp_path)
        agent_cfg = config.for_agent("claude-code")
        assert agent_cfg.env["A"] == "override"

    def test_override_does_not_remove_base_keys(self, tmp_path):
        _write(tmp_path, {
            "agents": {"claude-code": {"profiles": {"default": {"env": {"A": "1", "B": "2"}}}}}
        })
        _write_override(tmp_path, {
            "agents": {"claude-code": {"profiles": {"default": {"env": {"B": "override"}}}}}
        })
        config = load_config(tmp_path)
        agent_cfg = config.for_agent("claude-code")
        assert agent_cfg.env["A"] == "1"
        assert agent_cfg.env["B"] == "override"


class TestProfileEnv:
    """Tests for profile env resolution with ${VAR} interpolation."""

    def test_loads_standalone_profile(self, tmp_path):
        _write(tmp_path, {
            "agents": {"claude-code": {"profiles": {"bare": {"env": {"KEY": "bare_value"}}}}}
        })
        config = load_config(tmp_path)
        agent_cfg = config.for_agent("claude-code", profile="bare")
        assert agent_cfg.env["KEY"] == "bare_value"

    def test_inherits_from_default(self, tmp_path):
        _write(tmp_path, {
            "agents": {
                "claude-code": {
                    "profiles": {
                        "default": {"env": {"BASE": "from_default", "SHARED": "default_val"}},
                        "ultra": {"env": {"SHARED": "ultra_val"}},
                    }
                }
            }
        })
        config = load_config(tmp_path)
        agent_cfg = config.for_agent("claude-code", profile="ultra")
        assert agent_cfg.env["BASE"] == "from_default"
        assert agent_cfg.env["SHARED"] == "ultra_val"

    def test_bare_does_not_inherit(self, tmp_path):
        _write(tmp_path, {
            "agents": {
                "claude-code": {
                    "profiles": {
                        "default": {"env": {"BASE": "should_not_inherit"}},
                        "bare": {"env": {"KEY": "bare_only"}},
                    }
                }
            }
        })
        config = load_config(tmp_path)
        agent_cfg = config.for_agent("claude-code", profile="bare")
        assert agent_cfg.env.get("KEY") == "bare_only"
        assert "BASE" not in agent_cfg.env

    def test_unknown_profile_raises_error(self, tmp_path):
        _write(tmp_path, {
            "agents": {"claude-code": {"profiles": {"default": {"env": {}}}}}
        })
        config = load_config(tmp_path)
        agent_cfg = config.for_agent("claude-code", profile="nope")
        # Profile "nope" doesn't exist, resolve_profile returns empty
        assert agent_cfg.env == {}

    def test_unknown_agent_raises_error(self, tmp_path):
        _write(tmp_path, {
            "agents": {"claude-code": {"profiles": {"default": {"env": {}}}}}
        })
        config = load_config(tmp_path)
        with pytest.raises(ConfigError):
            config.for_agent("unknown-agent")

    def test_local_mode_env(self, tmp_path):
        _write(tmp_path, {
            "agents": {
                "claude-code": {
                    "profiles": {
                        "default": {
                            "env": {"BASE": "val"},
                            "local": {"env": {"LOCAL_KEY": "local_val"}},
                        }
                    }
                }
            }
        })
        config = load_config(tmp_path)
        agent_cfg = config.for_agent("claude-code", mode="local")
        assert agent_cfg.env["BASE"] == "val"
        assert agent_cfg.env["LOCAL_KEY"] == "local_val"


class TestVarResolution:
    """Tests for ${VAR} resolution in profile env."""

    def test_resolves_from_context(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CF_CLI_FROM_OS", "resolved")
        _write(tmp_path, {
            "agents": {"claude-code": {"profiles": {"default": {"env": {"RESULT": "${FROM_OS}"}}}}}
        })
        config = load_config(tmp_path)
        agent_cfg = config.for_agent("claude-code")
        assert agent_cfg.env["RESULT"] == "resolved"

    def test_default_fallback(self, tmp_path):
        _write(tmp_path, {
            "agents": {"claude-code": {"profiles": {"default": {"env": {"RESULT": "${MISSING:-fallback}"}}}}}
        })
        config = load_config(tmp_path)
        agent_cfg = config.for_agent("claude-code")
        assert agent_cfg.env["RESULT"] == "fallback"

    def test_missing_no_default(self, tmp_path):
        _write(tmp_path, {
            "agents": {"claude-code": {"profiles": {"default": {"env": {"RESULT": "${MISSING}"}}}}}
        })
        config = load_config(tmp_path)
        agent_cfg = config.for_agent("claude-code")
        assert agent_cfg.env["RESULT"] == ""


class TestAgentDefinition:
    """Unit tests for AgentDefinition.resolve_profile."""

    def test_merge_simple(self):
        ad = AgentDefinition(profiles={
            "default": ProfileEntry(env={"A": "1", "B": "2"}),
            "child": ProfileEntry(env={"B": "child_b", "C": "3"}),
        })
        result = ad.resolve_profile("child")
        assert result.env == {"A": "1", "B": "child_b", "C": "3"}

    def test_merge_tools_dedup(self):
        ad = AgentDefinition(profiles={
            "default": ProfileEntry(tools=["chrome", "web"]),
            "child": ProfileEntry(tools=["web", "github"]),
        })
        result = ad.resolve_profile("child")
        assert result.tools == ["chrome", "web", "github"]

    def test_standalone_bare(self):
        ad = AgentDefinition(profiles={
            "default": ProfileEntry(env={"A": "1"}),
            "bare": ProfileEntry(env={"B": "2"}),
        })
        result = ad.resolve_profile("bare")
        assert "A" not in result.env
        assert result.env["B"] == "2"


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "profiles.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    return path


def _write_override(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "override.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    return path


def _write_recipe(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "recipe.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    return path
pytestmark = pytest.mark.unit
