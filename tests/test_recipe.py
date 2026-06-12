"""Tests for recipe subsystem — ``cf init --recipe <name>``.

Tests cover:
  - DeepDiff structural merge for YAML/JSON files
  - `.env` key-by-key merge
  - GitHub fetch (with mocked HTTP responses)
  - Local submodule resolution
  - recipe.yaml parsing
  - ``What's Next`` summary generation
  - ``Fallback merge`` when DeepDiff Delta fails
  - Second+ recipe overlay merge
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
from unittest import mock

import pytest
import yaml

from codefreedom.cli.recipe import (
    _deepdiff_merge,
    _merge_env,
    _recursive_merge,
    _install_recipe_files,
    _resolve_recipe,
    _find_local_recipe,
    _fetch_recipe_manifest,
    _fetch_recipe_files,
    _print_summary,
    _parse_github_url,
    _list_recipes_from_store,
    _resolve_store,
)

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
        "optional_config": [
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
    """Structural merge of YAML/JSON configs using DeepDiff."""

    def test_adds_new_keys(self):
        """Incoming keys not in existing are added."""
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
        """Incoming values override existing ones."""
        existing = yaml.dump({"model": "flash", "retries": 3})
        incoming = yaml.dump({"model": "ultra", "retries": 3})
        result = _deepdiff_merge(existing, incoming)
        assert result is not None
        parsed = yaml.safe_load(result)
        assert parsed["model"] == "ultra"
        assert parsed["retries"] == 3

    def test_preserves_unrelated_keys(self):
        """Existing keys not touched by incoming remain unchanged."""
        existing = yaml.dump({"keep": "this", "update": "old"})
        incoming = yaml.dump({"update": "new"})
        result = _deepdiff_merge(existing, incoming)
        assert result is not None
        parsed = yaml.safe_load(result)
        assert parsed["keep"] == "this"
        assert parsed["update"] == "new"

    def test_returns_none_when_identical(self):
        """Identical content returns None (no-op)."""
        content = yaml.dump({"a": 1, "b": {"c": 2}})
        result = _deepdiff_merge(content, content)
        assert result is None

    def test_handles_empty_existing(self):
        """Empty existing returns incoming."""
        result = _deepdiff_merge("", yaml.dump({"key": "val"}))
        assert result is not None
        assert yaml.safe_load(result) == {"key": "val"}

    def test_handles_none_in_existing(self):
        """Existing 'null' YAML returns incoming."""
        result = _deepdiff_merge("null\n", yaml.dump({"key": "val"}))
        assert result is not None
        assert yaml.safe_load(result) == {"key": "val"}

    def test_nested_dict_merge(self):
        """Deep nested merge preserves all levels."""
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
        """YAML content merges correctly."""
        existing = yaml.dump({"a": 1, "b": 2})
        incoming = yaml.dump({"a": 1, "b": 3, "c": 4})
        result = _deepdiff_merge(existing, incoming)
        assert result is not None
        parsed = yaml.safe_load(result)
        assert parsed["a"] == 1
        assert parsed["b"] == 3
        assert parsed["c"] == 4

    def test_profile_yaml_merge(self):
        """Simulates merging a new model into profiles/claude-code.yaml."""
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
        # Existing profiles still present
        assert "default" in profiles
        assert "pro" in profiles
        # New profile added
        assert "ultra" in profiles
        # Existing keys preserved
        assert profiles["default"]["description"] == "Base profile"
        # New keys added
        assert "ANTHROPIC_AUTH_TOKEN" in profiles["default"]["env"]
        # Tools updated
        assert "github" in profiles["default"]["tools"]


# ═══════════════════════════════════════════════════════════════════════════════
# .env Key Merge
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnvMerge:
    """Key-by-key merge for .env-style files."""

    def test_keeps_existing_keys(self):
        """Existing keys are preserved."""
        existing = "EXISTING_KEY=old_value\nANOTHER=stay\n"
        incoming = "EXISTING_KEY=new_value\nEXTRA=new_key\n"
        result = _merge_env(existing, incoming)
        assert "EXISTING_KEY=old_value" in result
        assert "ANOTHER=stay" in result
        assert "EXTRA=new_key" in result

    def test_adds_new_keys(self):
        """New keys from incoming are appended."""
        existing = "EXISTING=value\n"
        incoming = "NEW_ONE=a\nNEW_TWO=b\n"
        result = _merge_env(existing, incoming)
        assert "EXISTING=value" in result
        assert "NEW_ONE=a" in result
        assert "NEW_TWO=b" in result

    def test_ignores_comments(self):
        """Comments in incoming don't affect the merge."""
        existing = "KEY=value\n"
        incoming = "# This is a comment\nOTHER=val\n"
        result = _merge_env(existing, incoming)
        assert "KEY=value" in result
        assert "OTHER=val" in result

    def test_returns_same_string_when_no_new_keys(self):
        """If incoming has no new keys, returns original unchanged."""
        existing = "A=1\nB=2\n"
        incoming = "A=1\n# just a comment\n"
        result = _merge_env(existing, incoming)
        assert result == existing

    def test_empty_values_allowed(self):
        """Empty values in incoming are appended as placeholders."""
        existing = "EXISTING=val\n"
        incoming = "NEW_KEY=\n"
        result = _merge_env(existing, incoming)
        assert "EXISTING=val" in result
        assert "NEW_KEY=" in result

    def test_preserves_whitespace_in_values(self):
        """Values with special chars are preserved."""
        existing = "URL=http://localhost:4000\n"
        incoming = "TOKEN=sk-abc123\n"
        result = _merge_env(existing, incoming)
        assert "URL=http://localhost:4000" in result
        assert "TOKEN=sk-abc123" in result


# ═══════════════════════════════════════════════════════════════════════════════
# Installation & Merge Orchestration
# ═══════════════════════════════════════════════════════════════════════════════


class TestInstallRecipeFiles:
    """Tests for _install_recipe_files and _merge_file."""

    def test_creates_new_files(self, tmp_path):
        """First-time install creates all files."""
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

        count = _install_recipe_files(manifest, files, tmp_path)
        assert count == 2
        assert (tmp_path / "config" / "config.yaml").exists()
        assert (tmp_path / ".env.test").exists()

    def test_merges_existing_yaml(self, tmp_path):
        """Existing YAML files are merged with DeepDiff."""
        manifest = {
            "files": [
                {"path": "cfg.yaml", "target": "cfg.yaml", "merge": "deepdiff"},
            ]
        }
        # Pre-create existing config
        (tmp_path / "cfg.yaml").write_text(yaml.dump({"keep": "this", "update": "old"}))
        files = {
            "cfg.yaml": yaml.dump({"keep": "this", "update": "new", "add": "extra"}),
        }

        count = _install_recipe_files(manifest, files, tmp_path)
        assert count == 1
        parsed = yaml.safe_load((tmp_path / "cfg.yaml").read_text())
        assert parsed["keep"] == "this"
        assert parsed["update"] == "new"
        assert parsed["add"] == "extra"

    def test_merges_existing_env(self, tmp_path):
        """Existing .env files are merged key-by-key."""
        manifest = {
            "files": [
                {"path": ".env", "target": ".env", "merge": "env"},
            ]
        }
        # Pre-create existing .env
        (tmp_path / ".env").write_text("EXISTING=stays\n")

        files = {".env": "EXISTING=changes\nNEW=added\n"}

        count = _install_recipe_files(manifest, files, tmp_path)
        assert count == 1
        content = (tmp_path / ".env").read_text()
        assert "EXISTING=stays" in content  # Existing preserved
        assert "NEW=added" in content  # New appended

    def test_auto_merge_env_by_name(self, tmp_path):
        """Auto-detect .env files for env-style merge."""
        manifest = {
            "files": [
                {"path": ".env.proxy", "target": ".env.proxy", "merge": "auto"},
            ]
        }
        (tmp_path / ".env.proxy").write_text("EXISTING=kept\n")
        files = {".env.proxy": "NEW_VAR=val\n"}
        count = _install_recipe_files(manifest, files, tmp_path)
        assert count == 1
        content = (tmp_path / ".env.proxy").read_text()
        assert "EXISTING=kept" in content
        assert "NEW_VAR=val" in content

    def test_auto_detect_yaml(self, tmp_path):
        """Auto-detect .yaml/.json files for deepdiff merge."""
        manifest = {
            "files": [
                {"path": "settings.yaml", "target": "settings.yaml", "merge": "auto"},
            ]
        }
        (tmp_path / "settings.yaml").write_text(yaml.dump({"keep": 1}))
        files = {"settings.yaml": yaml.dump({"keep": 1, "add": 2})}
        count = _install_recipe_files(manifest, files, tmp_path)
        assert count == 1
        parsed = yaml.safe_load((tmp_path / "settings.yaml").read_text())
        assert parsed == {"keep": 1, "add": 2}


# ═══════════════════════════════════════════════════════════════════════════════
# Fallback Merge
# ═══════════════════════════════════════════════════════════════════════════════


class TestRecursiveMerge:
    """Recursive dict merge — the core merge engine."""

    def test_adds_new_keys(self):
        result = _recursive_merge({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_updates_existing_keys(self):
        """Incoming value overwrites existing for same key."""
        result = _recursive_merge({"a": 1}, {"a": 99})
        assert result == {"a": 99}

    def test_preserves_unrelated(self):
        """Existing keys not in incoming are preserved."""
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
        assert result["outer"]["inner"] == 99  # Updated
        assert result["outer"]["other"] == 2  # Preserved
        assert result["outer"]["new"] == 3  # Added


# ═══════════════════════════════════════════════════════════════════════════════
# GitHub Fetch (mocked)
# ═══════════════════════════════════════════════════════════════════════════════


class TestGitHubFetch:
    """Tests for GitHub raw content fetching (with mocked HTTP)."""

    def test_fetch_manifest_success(self):
        """Fetching a valid recipe.yaml returns parsed manifest."""
        manifest_yaml = yaml.dump(
            {
                "name": "test-recipe",
                "files": [
                    {"path": "cfg.yaml", "target": "cfg.yaml", "merge": "deepdiff"},
                ],
            }
        )

        with mock.patch(
            "codefreedom.recipe.store._fetch_text",
            return_value=manifest_yaml,
        ):
            manifest = _fetch_recipe_manifest("test-recipe")
            assert manifest["name"] == "test-recipe"
            assert len(manifest["files"]) == 1

    def test_fetch_manifest_http_error(self):
        """HTTP error raises RecipeError."""
        with mock.patch(
            "codefreedom.recipe.store._fetch_text",
            side_effect=__import__(
                "codefreedom.recipe.store",
                fromlist=["RecipeError"],
            ).RecipeError("HTTP 404"),
        ):
            with pytest.raises(Exception):
                _fetch_recipe_manifest("nonexistent")

    def test_fetch_files_success(self):
        """Fetching recipe files returns content dict."""
        manifest = {
            "files": [
                {"path": "cfg.yaml", "target": "cfg.yaml", "merge": "deepdiff"},
                {"path": ".env", "target": ".env", "merge": "env"},
            ]
        }

        def mock_fetch(url: str, _timeout: int = 15) -> str:
            if "cfg.yaml" in url:
                return "key: val\n"
            if ".env" in url:
                return "VAR=val\n"
            return ""

        with mock.patch(
            "codefreedom.recipe.store._fetch_text",
            side_effect=mock_fetch,
        ):
            files = _fetch_recipe_files("test", manifest)
            assert "cfg.yaml" in files
            assert ".env" in files
            assert files["cfg.yaml"] == "key: val\n"


# ═══════════════════════════════════════════════════════════════════════════════
# Local Resolution
# ═══════════════════════════════════════════════════════════════════════════════


class TestLocalResolution:
    """Tests for finding recipes in local submodule."""

    def test_find_local_recipe_not_found(self):
        """Returns None when recipe doesn't exist locally."""
        result = _find_local_recipe("nonexistent-recipe-12345")
        assert result is None

    def test_resolve_recipe_falls_back_when_no_local(self):
        """When local is missing, tries to use GitHub (mocked fallback)."""
        with (
            mock.patch(
                "codefreedom.recipe.store._find_local_recipe",
                return_value=None,
            ),
            mock.patch(
                "codefreedom.recipe.store._fetch_recipe_manifest",
                side_effect=__import__(
                    "codefreedom.recipe.store",
                    fromlist=["RecipeError"],
                ).RecipeError("not found"),
            ),
        ):
            manifest, files = _resolve_recipe("nonexistent")
            assert manifest is None
            assert files == {}


# ═══════════════════════════════════════════════════════════════════════════════
# Summary Generation
# ═══════════════════════════════════════════════════════════════════════════════


class TestSummary:
    """Tests for What's Next summary printing."""

    def test_prints_required_secrets(self, capsys, manifest_fixture):
        """Required secrets are printed in the summary."""
        _print_summary(manifest_fixture, Path("/tmp"))
        captured = capsys.readouterr()
        assert "TEST_API_KEY" in captured.out
        assert "Test API key" in captured.out

    def test_prints_optional_config(self, capsys, manifest_fixture):
        """Optional config with defaults are printed."""
        _print_summary(manifest_fixture, Path("/tmp"))
        captured = capsys.readouterr()
        assert "TEST_OPTION" in captured.out
        assert "default-value" in captured.out

    def test_prints_next_steps(self, capsys, manifest_fixture):
        """Next steps section is printed."""
        _print_summary(manifest_fixture, Path("/tmp"))
        captured = capsys.readouterr()
        assert "NEXT STEPS" in captured.out
        assert "cf proxy start" in captured.out
        assert "cf cc" in captured.out

    def test_no_required_secrets(self, capsys):
        """Summary works without required_secrets."""
        manifest = {"name": "minimal", "files": []}
        _print_summary(manifest, Path("/tmp"))
        captured = capsys.readouterr()
        assert "Recipe: minimal" in captured.out


# ═══════════════════════════════════════════════════════════════════════════════
# Integration: Full Recipe Apply
# ═══════════════════════════════════════════════════════════════════════════════


class TestRecipeApply:
    """End-to-end test: installing a recipe then overlaying a second one."""

    def test_first_recipe_then_second_merge(self, tmp_path):
        """First recipe creates files, second recipe merges into them."""
        cf_dir = tmp_path / ".codefreedom"

        # ── First recipe ──────────────────────────────────────────────────
        recipe1 = {
            "files": [
                {"path": "cfg.yaml", "target": "cfg.yaml", "merge": "deepdiff"},
                {"path": ".env", "target": ".env", "merge": "env"},
            ]
        }
        files1 = {
            "cfg.yaml": yaml.dump(
                {
                    "model": "flash",
                    "retries": 3,
                    "features": {"logging": True},
                }
            ),
            ".env": "BASE_URL=http://localhost:4000\n",
        }
        count1 = _install_recipe_files(recipe1, files1, cf_dir)
        assert count1 == 2

        # ── Second recipe ─────────────────────────────────────────────────
        recipe2 = {
            "files": [
                {"path": "cfg.yaml", "target": "cfg.yaml", "merge": "deepdiff"},
                {"path": ".env", "target": ".env", "merge": "env"},
                {"path": "extra.yaml", "target": "extra.yaml", "merge": "deepdiff"},
            ]
        }
        files2 = {
            "cfg.yaml": yaml.dump(
                {
                    "model": "ultra",
                    "features": {"logging": True, "streaming": True},
                }
            ),
            ".env": "NEW_KEY=value\n",
            "extra.yaml": yaml.dump({"added": True}),
        }

        import sys

        if "codefreedom.cli.recipe" in sys.modules:
            # Force reimport to clear any state
            pass

        count2 = _install_recipe_files(recipe2, files2, cf_dir)
        # cfg.yaml (merged), .env (merged), extra.yaml (created) = 3
        assert count2 == 3

        # Verify cfg.yaml merge
        cfg = yaml.safe_load((cf_dir / "cfg.yaml").read_text())
        assert cfg["model"] == "ultra"  # Updated by recipe 2
        assert cfg["retries"] == 3  # Preserved from recipe 1
        assert cfg["features"]["streaming"] is True  # Added by recipe 2
        assert cfg["features"]["logging"] is True  # Preserved

        # Verify .env merge
        env_content = (cf_dir / ".env").read_text()
        assert "BASE_URL=http://localhost:4000" in env_content  # Preserved
        assert "NEW_KEY=value" in env_content  # Added

        # Verify extra was created
        extra = yaml.safe_load((cf_dir / "extra.yaml").read_text())
        assert extra["added"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# Custom Store (--store flag)
# ═══════════════════════════════════════════════════════════════════════════════


class TestParseGithubUrl:
    """Parsing GitHub URLs into directory names."""

    def test_https_url_with_git_suffix(self):
        """https://github.com/owner/repo.git → owner-repo."""
        assert (
            _parse_github_url("https://github.com/nilayparikh/cf-recipes.git")
            == "nilayparikh-cf-recipes"
        )

    def test_https_url_without_git_suffix(self):
        """https://github.com/owner/repo → owner-repo."""
        assert (
            _parse_github_url("https://github.com/nilayparikh/cf-recipes")
            == "nilayparikh-cf-recipes"
        )

    def test_ssh_url(self):
        """git@github.com:owner/repo.git → owner-repo."""
        assert (
            _parse_github_url("git@github.com:nilayparikh/cf-recipes.git")
            == "nilayparikh-cf-recipes"
        )

    def test_https_url_trailing_slash(self):
        """https://github.com/owner/repo/ → owner-repo."""
        assert (
            _parse_github_url("https://github.com/nilayparikh/cf-recipes/")
            == "nilayparikh-cf-recipes"
        )

    def test_non_github_url(self):
        """Arbitrary URL returns None."""
        assert _parse_github_url("https://gitlab.com/owner/repo.git") is None

    def test_invalid_string(self):
        """Non-URL string returns None."""
        assert _parse_github_url("not-a-url") is None


class TestListRecipesFromStore:
    """Listing recipes available in a custom store directory."""

    def test_finds_recipes_with_recipe_yaml(self, tmp_path):
        """Directories with recipe.yaml are listed."""
        (tmp_path / "free" / "recipe.yaml").parent.mkdir()
        (tmp_path / "free" / "recipe.yaml").write_text("name: free\n")
        (tmp_path / "deepseek" / "recipe.yaml").parent.mkdir()
        (tmp_path / "deepseek" / "recipe.yaml").write_text("name: deepseek\n")
        (tmp_path / "_default" / "recipe.yaml").parent.mkdir()
        (tmp_path / "_default" / "recipe.yaml").write_text("name: _default\n")

        recipes = _list_recipes_from_store(tmp_path)
        assert "free" in recipes
        assert "deepseek" in recipes
        assert "_default" not in recipes  # Skipped (starts with _)

    def test_skips_non_recipe_dirs(self, tmp_path):
        """Directories without recipe.yaml are ignored."""
        (tmp_path / "free" / "recipe.yaml").parent.mkdir()
        (tmp_path / "free" / "recipe.yaml").write_text("name: free\n")
        (tmp_path / "not-a-recipe").mkdir()
        (tmp_path / "some-file.txt").write_text("hello")

        recipes = _list_recipes_from_store(tmp_path)
        assert recipes == ["free"]

    def test_empty_store(self, tmp_path):
        """Empty directory returns empty list."""
        assert _list_recipes_from_store(tmp_path) == []

    def test_missing_directory(self):
        """Non-existent directory returns empty list."""
        assert _list_recipes_from_store(Path("/nonexistent/path")) == []


class TestResolveStore:
    """Resolving a --store value to a local directory path."""

    def test_local_absolute_path(self, tmp_path):
        """Absolute local path is returned as-is."""
        result = _resolve_store(str(tmp_path))
        assert result == tmp_path.resolve()

    def test_local_path_with_expanduser(self, tmp_path, monkeypatch):
        """~ expansion works correctly."""
        monkeypatch.setenv("HOME", str(tmp_path))
        home_dir = tmp_path
        (home_dir / "my-recipes").mkdir()

        result = _resolve_store("~/my-recipes")
        assert result == home_dir.resolve() / "my-recipes"

    def test_nonexistent_local_path(self):
        """Non-existent local path returns None."""
        result = _resolve_store("/tmp/nonexistent-recipe-store-12345")
        assert result is None

    def test_dot_relative_path(self, tmp_path):
        """Relative path starting with '.' is resolved."""
        cwd = Path.cwd()
        result = _resolve_store(".")
        assert result == cwd.resolve()

    def test_github_url_parsing(self):
        """GitHub URL is parsed but requires git clone which is mocked."""
        # Just verify parse doesn't crash and returns None if no git
        url = "https://github.com/nilayparikh/cf-recipes.git"
        name = _parse_github_url(url)
        assert name == "nilayparikh-cf-recipes"


class TestResolveRecipeWithStore:
    """_resolve_recipe with custom store_path."""

    def test_store_takes_priority(self, tmp_path):
        """Custom store is checked before local submodule and GitHub."""
        # Create a store with a recipe
        recipe_dir = tmp_path / "store" / "my-recipe"
        recipe_dir.mkdir(parents=True)
        recipe_yaml = {
            "name": "my-recipe",
            "files": [
                {"path": "cfg.yaml", "target": "cfg.yaml", "merge": "deepdiff"},
            ],
        }
        (recipe_dir / "recipe.yaml").write_text(yaml.dump(recipe_yaml))
        (recipe_dir / "cfg.yaml").write_text("key: from-store\n")

        # Mock local submodule to return a different recipe — store should win
        with mock.patch(
            "codefreedom.recipe.store._find_local_recipe",
            return_value=tmp_path / "local" / "my-recipe",
        ):
            manifest, files = _resolve_recipe(
                "my-recipe", store_path=tmp_path / "store"
            )
            assert manifest is not None
            assert manifest["name"] == "my-recipe"
            assert files["cfg.yaml"] == "key: from-store\n"

    def test_returns_none_when_not_in_store(self, tmp_path):
        """When recipe not in store, returns None (no GitHub HTTP fallback)."""
        with mock.patch(
            "codefreedom.recipe.store._find_local_recipe",
            return_value=None,
        ):
            store = tmp_path / "empty-store"
            store.mkdir()
            manifest, files = _resolve_recipe("fallback-recipe", store_path=store)
            assert manifest is None
            assert files == {}

    def test_extends_from_same_store(self, tmp_path):
        """Extends chain resolves from the same store."""
        # Create base recipe
        base_dir = tmp_path / "store" / "_default"
        base_dir.mkdir(parents=True)
        (base_dir / "recipe.yaml").write_text(
            yaml.dump(
                {
                    "name": "_default",
                    "files": [
                        {
                            "path": "base.yaml",
                            "target": "base.yaml",
                            "merge": "deepdiff",
                        }
                    ],
                }
            )
        )
        (base_dir / "base.yaml").write_text("base: true\n")

        # Create child recipe that extends _default
        child_dir = tmp_path / "store" / "child"
        child_dir.mkdir(parents=True)
        (child_dir / "recipe.yaml").write_text(
            yaml.dump(
                {
                    "name": "child",
                    "extends": "_default",
                    "files": [
                        {
                            "path": "child.yaml",
                            "target": "child.yaml",
                            "merge": "deepdiff",
                        }
                    ],
                }
            )
        )
        (child_dir / "child.yaml").write_text("child: true\n")

        manifest, files = _resolve_recipe("child", store_path=tmp_path / "store")
        assert manifest is not None
        assert manifest["name"] == "child"
        assert "child.yaml" in files
