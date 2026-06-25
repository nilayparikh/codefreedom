"""Pure-logic merge operations for recipe system.

Tests structural merge (DeepDiff), env merge, recursive merge, and
installation orchestration using only tmp_path fixtures.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest
import yaml

from codefreedom.cli.setup.recipe import (
    _deepdiff_merge,
    _merge_env,
    _recursive_merge,
    _install_recipe_files,
)

pytestmark = pytest.mark.unit

# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture(name="manifest_fixture")
def recipe_manifest() -> Dict[str, Any]:
    return {
        "name": "test-recipe",
        "description": "Test recipe",
        "version": 1,
        "files": [
            {
                "path": "proxy/config/config.yaml",
                "target": "proxy/config/config.yaml",
                "merge": "deepdiff",
            },
            {"path": ".env.proxy", "target": ".env.proxy", "merge": "env"},
        ],
        "required_secrets": [
            {"var": "TEST_API_KEY", "prompt": "Test API key"},
        ],
        "config_vars": [
            {"var": "TEST_OPTION", "default": "default-value"},
        ],
    }


@pytest.fixture
def recipe_files() -> Dict[str, str]:
    return {
        "proxy/config/config.yaml": yaml.dump(
            {
                "general_settings": {"store_model_in_db": False},
                "router_settings": {"num_retries": 3},
            }
        ),
        ".env.proxy": "TEST_VAR=from-recipe\nNEW_VAR=value\n",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# DeepDiff Structural Merge
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeepDiffMerge:
    def test_adds_new_keys(self):
        existing = yaml.dump({"server": {"port": 4000, "host": "0.0.0.0"}})
        incoming = yaml.dump(
            {"server": {"port": 4000, "host": "0.0.0.0", "log_level": "INFO"}}
        )
        result = _deepdiff_merge(existing, incoming)
        assert result is not None
        parsed = yaml.safe_load(result)
        assert parsed["server"]["port"] == 4000
        assert parsed["server"]["host"] == "0.0.0.0"
        assert parsed["server"]["log_level"] == "INFO"

    def test_updates_changed_values(self):
        existing = yaml.dump({"model": "flash", "retries": 3})
        incoming = yaml.dump({"model": "ultra", "retries": 3})
        result = _deepdiff_merge(existing, incoming)
        assert result is not None
        parsed = yaml.safe_load(result)
        assert parsed["model"] == "ultra"
        assert parsed["retries"] == 3

    def test_preserves_unrelated_keys(self):
        existing = yaml.dump({"keep": "this", "update": "old"})
        incoming = yaml.dump({"update": "new"})
        result = _deepdiff_merge(existing, incoming)
        assert result is not None
        parsed = yaml.safe_load(result)
        assert parsed["keep"] == "this"
        assert parsed["update"] == "new"

    def test_returns_none_when_identical(self):
        content = yaml.dump({"a": 1, "b": {"c": 2}})
        result = _deepdiff_merge(content, content)
        assert result is None

    def test_handles_empty_existing(self):
        result = _deepdiff_merge("", yaml.dump({"key": "val"}))
        assert result is not None
        assert yaml.safe_load(result) == {"key": "val"}

    def test_handles_none_in_existing(self):
        result = _deepdiff_merge("null\n", yaml.dump({"key": "val"}))
        assert result is not None
        assert yaml.safe_load(result) == {"key": "val"}

    def test_nested_dict_merge(self):
        existing = yaml.dump(
            {
                "litellm_settings": {
                    "drop_params": True,
                    "callbacks": ["prometheus"],
                    "modify_params": False,
                }
            }
        )
        incoming = yaml.dump(
            {
                "litellm_settings": {
                    "drop_params": True,
                    "callbacks": ["prometheus", "new_callback"],
                    "modify_params": True,
                    "json_logs": True,
                }
            }
        )
        result = _deepdiff_merge(existing, incoming)
        assert result is not None
        parsed = yaml.safe_load(result)
        settings = parsed["litellm_settings"]
        assert settings["drop_params"] is True
        assert settings["modify_params"] is True
        assert "new_callback" in settings["callbacks"]
        assert settings["json_logs"] is True

    def test_yaml_content_merge(self):
        existing = yaml.dump({"a": 1, "b": 2})
        incoming = yaml.dump({"a": 1, "b": 3, "c": 4})
        result = _deepdiff_merge(existing, incoming)
        assert result is not None
        parsed = yaml.safe_load(result)
        assert parsed["a"] == 1
        assert parsed["b"] == 3
        assert parsed["c"] == 4

    def test_profile_yaml_merge(self):
        existing = {
            "profiles": {
                "default": {
                    "description": "Base profile",
                    "env": {
                        "CLAUDE_MODEL": "CodeFreedom/Flash",
                        "ANTHROPIC_BASE_URL": "http://localhost:4000",
                    },
                    "tools": ["chrome", "web"],
                },
                "pro": {
                    "description": "Inherits from default",
                    "env": {"CLAUDE_MODEL": "CodeFreedom/Pro"},
                },
            }
        }
        incoming = {
            "profiles": {
                "default": {
                    "description": "Base profile",
                    "env": {
                        "CLAUDE_MODEL": "CodeFreedom/Flash",
                        "ANTHROPIC_BASE_URL": "http://localhost:4000",
                        "ANTHROPIC_AUTH_TOKEN": "${LITELLM_MASTER_KEY}",
                    },
                    "tools": ["chrome", "web", "github"],
                },
                "pro": {
                    "description": "Inherits from default",
                    "env": {"CLAUDE_MODEL": "CodeFreedom/Pro"},
                },
                "ultra": {
                    "description": "Inherits from default",
                    "env": {"CLAUDE_MODEL": "CodeFreedom/Ultra"},
                },
            }
        }
        result = _deepdiff_merge(yaml.dump(existing), yaml.dump(incoming))
        assert result is not None
        parsed = yaml.safe_load(result)
        profiles = parsed["profiles"]
        assert "default" in profiles
        assert "pro" in profiles
        assert "ultra" in profiles
        assert profiles["default"]["description"] == "Base profile"
        assert "ANTHROPIC_AUTH_TOKEN" in profiles["default"]["env"]
        assert "github" in profiles["default"]["tools"]


# ═══════════════════════════════════════════════════════════════════════════════
# .env Key Merge
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnvMerge:
    def test_keeps_existing_keys(self):
        existing = "EXISTING_KEY=old_value\nANOTHER=stay\n"
        incoming = "EXISTING_KEY=new_value\nEXTRA=new_key\n"
        result = _merge_env(existing, incoming)
        assert "EXISTING_KEY=old_value" in result
        assert "ANOTHER=stay" in result
        assert "EXTRA=new_key" in result

    def test_adds_new_keys(self):
        existing = "EXISTING=value\n"
        incoming = "NEW_ONE=a\nNEW_TWO=b\n"
        result = _merge_env(existing, incoming)
        assert "EXISTING=value" in result
        assert "NEW_ONE=a" in result
        assert "NEW_TWO=b" in result

    def test_ignores_comments(self):
        existing = "KEY=value\n"
        incoming = "# This is a comment\nOTHER=val\n"
        result = _merge_env(existing, incoming)
        assert "KEY=value" in result
        assert "OTHER=val" in result

    def test_returns_same_string_when_no_new_keys(self):
        existing = "A=1\nB=2\n"
        incoming = "A=1\n# just a comment\n"
        result = _merge_env(existing, incoming)
        assert result == existing

    def test_empty_values_allowed(self):
        existing = "EXISTING=val\n"
        incoming = "NEW_KEY=\n"
        result = _merge_env(existing, incoming)
        assert "EXISTING=val" in result
        assert "NEW_KEY=" in result

    def test_preserves_whitespace_in_values(self):
        existing = "URL=http://localhost:4000\n"
        incoming = "TOKEN=sk-abc123\n"
        result = _merge_env(existing, incoming)
        assert "URL=http://localhost:4000" in result
        assert "TOKEN=sk-abc123" in result


# ═══════════════════════════════════════════════════════════════════════════════
# Installation & Merge Orchestration
# ═══════════════════════════════════════════════════════════════════════════════


class TestInstallRecipeFiles:
    def test_creates_new_files(self, tmp_path):
        manifest = {
            "files": [
                {
                    "path": "config.yaml",
                    "target": "config/config.yaml",
                    "merge": "deepdiff",
                },
                {"path": ".env.test", "target": ".env.test", "merge": "env"},
            ]
        }
        files = {
            "config/config.yaml": "key: value\n",
            ".env.test": "TEST=hello\n",
        }

        count = _install_recipe_files(manifest, files, tmp_path, config_dir=tmp_path)
        assert count == 2
        assert (tmp_path / "config" / "config.yaml").exists()
        assert (tmp_path / ".env.test").exists()

    def test_merges_existing_yaml(self, tmp_path):
        manifest = {
            "files": [
                {"path": "cfg.yaml", "target": "cfg.yaml", "merge": "deepdiff"},
            ]
        }
        (tmp_path / "cfg.yaml").write_text(yaml.dump({"keep": "this", "update": "old"}))
        files = {
            "cfg.yaml": yaml.dump({"keep": "this", "update": "new", "add": "extra"}),
        }

        count = _install_recipe_files(manifest, files, tmp_path, config_dir=tmp_path)
        assert count == 1
        parsed = yaml.safe_load((tmp_path / "cfg.yaml").read_text())
        assert parsed["keep"] == "this"
        assert parsed["update"] == "new"
        assert parsed["add"] == "extra"

    def test_merges_existing_env(self, tmp_path):
        manifest = {
            "files": [
                {"path": ".env", "target": ".env", "merge": "env"},
            ]
        }
        (tmp_path / ".env").write_text("EXISTING=stays\n")
        files = {".env": "EXISTING=changes\nNEW=added\n"}

        count = _install_recipe_files(manifest, files, tmp_path, config_dir=tmp_path)
        assert count == 1
        content = (tmp_path / ".env").read_text()
        assert "EXISTING=stays" in content
        assert "NEW=added" in content

    def test_auto_merge_env_by_name(self, tmp_path):
        manifest = {
            "files": [
                {"path": ".env.proxy", "target": ".env.proxy", "merge": "auto"},
            ]
        }
        (tmp_path / ".env.proxy").write_text("EXISTING=kept\n")
        files = {".env.proxy": "NEW_VAR=val\n"}
        count = _install_recipe_files(manifest, files, tmp_path, config_dir=tmp_path)
        assert count == 1
        content = (tmp_path / ".env.proxy").read_text()
        assert "EXISTING=kept" in content
        assert "NEW_VAR=val" in content

    def test_auto_detect_yaml(self, tmp_path):
        manifest = {
            "files": [
                {"path": "settings.yaml", "target": "settings.yaml", "merge": "auto"},
            ]
        }
        (tmp_path / "settings.yaml").write_text(yaml.dump({"keep": 1}))
        files = {"settings.yaml": yaml.dump({"keep": 1, "add": 2})}
        count = _install_recipe_files(manifest, files, tmp_path, config_dir=tmp_path)
        assert count == 1
        parsed = yaml.safe_load((tmp_path / "settings.yaml").read_text())
        assert parsed == {"keep": 1, "add": 2}


# ═══════════════════════════════════════════════════════════════════════════════
# Fallback Merge
# ═══════════════════════════════════════════════════════════════════════════════


class TestRecursiveMerge:
    def test_adds_new_keys(self):
        result = _recursive_merge({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_updates_existing_keys(self):
        result = _recursive_merge({"a": 1}, {"a": 99})
        assert result == {"a": 99}

    def test_preserves_unrelated(self):
        result = _recursive_merge(
            {"keep": "this", "update": "old"},
            {"update": "new"},
        )
        assert result == {"keep": "this", "update": "new"}

    def test_nested_merge(self):
        result = _recursive_merge(
            {"outer": {"inner": 1, "other": 2}},
            {"outer": {"inner": 99, "new": 3}},
        )
        assert result["outer"]["inner"] == 99
        assert result["outer"]["other"] == 2
        assert result["outer"]["new"] == 3
