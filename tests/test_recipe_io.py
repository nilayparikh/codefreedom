"""I/O-dependent tests for recipe system.

Tests GitHub fetch, local resolution, summary generation, and
end-to-end recipe apply with mocked network and real filesystem.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest
import yaml

from codefreedom.cli.setup.recipe import (
    _fetch_recipe_manifest,
    _fetch_recipe_files,
    _find_local_recipe,
    _print_summary,
    _parse_github_url,
    _list_recipes_from_store,
    _resolve_store,
    _resolve_recipe,
    _install_recipe_files,
)

pytestmark = pytest.mark.integration

# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture(name="manifest_fixture")
def recipe_manifest() -> dict:
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


# ═══════════════════════════════════════════════════════════════════════════════
# GitHub Fetch (mocked)
# ═══════════════════════════════════════════════════════════════════════════════


class TestGitHubFetch:
    def test_fetch_manifest_success(self):
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
    def test_find_local_recipe_not_found(self):
        result = _find_local_recipe("nonexistent-recipe-12345")
        assert result is None

    def test_resolve_recipe_falls_back_when_no_local(self):
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
    def test_prints_required_secrets(self, capsys, manifest_fixture):
        _print_summary(manifest_fixture, Path("/tmp"))
        captured = capsys.readouterr()
        assert "TEST_API_KEY" in captured.out
        assert "Test API key" in captured.out

    def test_prints_optional_config(self, capsys, manifest_fixture):
        _print_summary(manifest_fixture, Path("/tmp"))
        captured = capsys.readouterr()
        assert "TEST_OPTION" in captured.out
        assert "Configuration" in captured.out

    def test_prints_next_steps(self, capsys, manifest_fixture, monkeypatch):
        monkeypatch.setenv("CF_CLI_TEST_API_KEY", "sk-test")
        monkeypatch.setenv("CF_CLI_TEST_OPTION", "some-value")
        _print_summary(manifest_fixture, Path("/tmp"))
        captured = capsys.readouterr()
        assert "All secrets configured" in captured.out
        assert "Ready to start" in captured.out
        assert "cf r px start" in captured.out

    def test_no_required_secrets(self, capsys):
        manifest = {"name": "minimal", "files": []}
        _print_summary(manifest, Path("/tmp"))
        captured = capsys.readouterr()
        assert "Recipe: minimal" in captured.out


# ═══════════════════════════════════════════════════════════════════════════════
# Integration: Full Recipe Apply
# ═══════════════════════════════════════════════════════════════════════════════


class TestRecipeApply:
    def test_first_recipe_then_second_merge(self, tmp_path):
        cf_dir = tmp_path / ".codefreedom"
        config_dir = tmp_path / ".codefreedom" / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

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
        count1 = _install_recipe_files(recipe1, files1, cf_dir, config_dir=config_dir)
        assert count1 == 2

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

        if "codefreedom.cli.setup.recipe" in sys.modules:
            pass

        count2 = _install_recipe_files(recipe2, files2, cf_dir, config_dir=config_dir)
        assert count2 == 3

        cfg = yaml.safe_load((config_dir / "cfg.yaml").read_text())
        assert cfg["model"] == "ultra"
        assert cfg["retries"] == 3
        assert cfg["features"]["streaming"] is True
        assert cfg["features"]["logging"] is True

        env_content = (config_dir / ".env").read_text()
        assert "BASE_URL=http://localhost:4000" in env_content
        assert "NEW_KEY=value" in env_content

        extra = yaml.safe_load((config_dir / "extra.yaml").read_text())
        assert extra["added"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# Custom Store (--store flag)
# ═══════════════════════════════════════════════════════════════════════════════


class TestParseGithubUrl:
    def test_https_url_with_git_suffix(self):
        assert (
            _parse_github_url("https://github.com/nilayparikh/cf-recipes.git")
            == "nilayparikh-cf-recipes"
        )

    def test_https_url_without_git_suffix(self):
        assert (
            _parse_github_url("https://github.com/nilayparikh/cf-recipes")
            == "nilayparikh-cf-recipes"
        )

    def test_ssh_url(self):
        assert (
            _parse_github_url("git@github.com:nilayparikh/cf-recipes.git")
            == "nilayparikh-cf-recipes"
        )

    def test_https_url_trailing_slash(self):
        assert (
            _parse_github_url("https://github.com/nilayparikh/cf-recipes/")
            == "nilayparikh-cf-recipes"
        )

    def test_non_github_url(self):
        assert _parse_github_url("https://gitlab.com/owner/repo.git") is None

    def test_invalid_string(self):
        assert _parse_github_url("not-a-url") is None


class TestListRecipesFromStore:
    def test_finds_recipes_with_recipe_yaml(self, tmp_path):
        (tmp_path / "free" / "recipe.yaml").parent.mkdir()
        (tmp_path / "free" / "recipe.yaml").write_text("name: free\n")
        (tmp_path / "deepseek" / "recipe.yaml").parent.mkdir()
        (tmp_path / "deepseek" / "recipe.yaml").write_text("name: deepseek\n")
        (tmp_path / "_default" / "recipe.yaml").parent.mkdir()
        (tmp_path / "_default" / "recipe.yaml").write_text("name: _default\n")

        recipes = _list_recipes_from_store(tmp_path)
        assert "free" in recipes
        assert "deepseek" in recipes
        assert "_default" not in recipes

    def test_skips_non_recipe_dirs(self, tmp_path):
        (tmp_path / "free" / "recipe.yaml").parent.mkdir()
        (tmp_path / "free" / "recipe.yaml").write_text("name: free\n")
        (tmp_path / "not-a-recipe").mkdir()
        (tmp_path / "some-file.txt").write_text("hello")

        recipes = _list_recipes_from_store(tmp_path)
        assert recipes == ["free"]

    def test_empty_store(self, tmp_path):
        assert _list_recipes_from_store(tmp_path) == []

    def test_missing_directory(self):
        assert _list_recipes_from_store(Path("/nonexistent/path")) == []


class TestResolveStore:
    def test_local_absolute_path(self, tmp_path):
        result = _resolve_store(str(tmp_path))
        assert result == tmp_path.resolve()

    def test_local_path_with_expanduser(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        home_dir = tmp_path
        (home_dir / "my-recipes").mkdir()

        result = _resolve_store("~/my-recipes")
        assert result == home_dir.resolve() / "my-recipes"

    def test_nonexistent_local_path(self):
        result = _resolve_store("/tmp/nonexistent-recipe-store-12345")
        assert result is None

    def test_dot_relative_path(self, tmp_path):
        cwd = Path.cwd()
        result = _resolve_store(".")
        assert result == cwd.resolve()

    def test_github_url_parsing(self):
        url = "https://github.com/nilayparikh/cf-recipes.git"
        name = _parse_github_url(url)
        assert name == "nilayparikh-cf-recipes"


# ═══════════════════════════════════════════════════════════════════════════════
# Generated Artifacts Integration
# ═══════════════════════════════════════════════════════════════════════════════


class TestGeneratedArtifacts:
    def test_init_recipe_with_generated_artifacts(self, tmp_path, monkeypatch):
        cf_dir = tmp_path / ".codefreedom"
        cf_dir.mkdir()

        manifest = {
            "name": "gen-recipe",
            "files": [
                {
                    "path": "proxy/config/config.yaml",
                    "target": "proxy/config/config.yaml",
                    "merge": "deepdiff",
                },
            ],
            "required_secrets": [
                {"var": "MY_API_KEY", "prompt": "Enter your API key"},
            ],
            "generated_artifacts": [
                {"kind": "setup_script_bash", "target": "scripts/setup.sh"},
            ],
        }
        files = {"proxy/config/config.yaml": "key: val\n"}

        monkeypatch.setattr(
            "codefreedom.recipe.plan.get_codefreedom_dir", lambda: cf_dir
        )
        monkeypatch.setattr(
            "codefreedom.recipe.plan.get_config_dir", lambda: cf_dir / "config"
        )
        monkeypatch.setattr(
            "codefreedom.recipe.plan._resolve_store",
            lambda store, branch=None: tmp_path / "store",
        )
        monkeypatch.setattr(
            "codefreedom.recipe.plan._resolve_recipe_branch",
            lambda: "main",
        )

        store = tmp_path / "store"
        recipe_dir = store / "gen-recipe"
        recipe_dir.mkdir(parents=True)
        (recipe_dir / "recipe.yaml").write_text(yaml.dump(manifest))
        (recipe_dir / "proxy" / "config").mkdir(parents=True)
        (recipe_dir / "proxy" / "config" / "config.yaml").write_text("key: val\n")

        monkeypatch.setattr(
            "codefreedom.recipe.plan._store_resolve_recipe",
            lambda name, store_path=None: (manifest, files),
        )

        from codefreedom.recipe.plan import init_recipe

        rc = init_recipe("gen-recipe")
        assert rc == 0

        setup_script = cf_dir / "config" / "scripts" / "setup.sh"
        assert setup_script.exists()
        content = setup_script.read_text()
        assert "#!/usr/bin/env bash" in content
        assert "MY_API_KEY" in content

    def test_init_recipe_persists_extended_recipe_vars(self, tmp_path, monkeypatch):
        cf_dir = tmp_path / ".codefreedom"
        cf_dir.mkdir()

        base_manifest = {
            "name": "_default",
            "vars": {
                "TOOL_IMAGE_BASE": "docker.io/nilayparikh/codefreedom",
                "CHROME_IMAGE_TAG": "latest",
                "WEB_IMAGE_TAG": "latest",
                "GITHUB_IMAGE_TAG": "latest",
                "WEB_BRIDGE_IMAGE_TAG": "latest",
            },
            "files": [],
        }
        base_files = {}
        child_manifest = {
            "name": "child",
            "extends": "_default",
            "files": [
                {
                    "path": "profiles.yaml",
                    "target": "profiles.yaml",
                    "merge": "deepdiff",
                }
            ],
        }
        child_files = {
            "profiles.yaml": yaml.dump(
                {
                    "agents": {"claude-code": {"profiles": {"default": {"env": {}}}}},
                    "tools": {
                        "chrome": {
                            "image": "${TOOL_IMAGE_BASE}:chrome-${CHROME_IMAGE_TAG}",
                            "container_name": "codefreedom-tools-chrome",
                            "port": 9222,
                        }
                    },
                },
                sort_keys=False,
            )
        }

        monkeypatch.setattr(
            "codefreedom.recipe.plan.get_codefreedom_dir", lambda: cf_dir
        )
        monkeypatch.setattr(
            "codefreedom.recipe.plan.get_config_dir", lambda: cf_dir / "config"
        )
        monkeypatch.setattr(
            "codefreedom.recipe.plan._resolve_store",
            lambda store, branch=None: tmp_path / "store",
        )
        monkeypatch.setattr(
            "codefreedom.recipe.plan._resolve_recipe_branch",
            lambda: "main",
        )

        def resolve_recipe(name, store_path=None):
            if name == "_default":
                return base_manifest, base_files
            if name == "child":
                return child_manifest, child_files
            return None, {}

        monkeypatch.setattr("codefreedom.recipe.plan._store_resolve_recipe", resolve_recipe)

        from codefreedom.recipe.plan import init_recipe

        rc = init_recipe("child")
        assert rc == 0

        recipe_yaml = yaml.safe_load((cf_dir / "config" / "recipe.yaml").read_text(encoding="utf-8"))
        assert recipe_yaml["vars"]["TOOL_IMAGE_BASE"] == "docker.io/nilayparikh/codefreedom"
        assert recipe_yaml["vars"]["CHROME_IMAGE_TAG"] == "latest"
        assert recipe_yaml["vars"]["WEB_IMAGE_TAG"] == "latest"
        assert recipe_yaml["vars"]["GITHUB_IMAGE_TAG"] == "latest"
        assert recipe_yaml["vars"]["WEB_BRIDGE_IMAGE_TAG"] == "latest"

    def test_plan_recipe_with_generated_artifacts(self, tmp_path, monkeypatch, capsys):
        cf_dir = tmp_path / ".codefreedom"
        cf_dir.mkdir()

        manifest = {
            "name": "gen-recipe",
            "files": [
                {
                    "path": "proxy/config/config.yaml",
                    "target": "proxy/config/config.yaml",
                    "merge": "deepdiff",
                },
            ],
            "required_secrets": [
                {"var": "MY_API_KEY", "prompt": "Enter your API key"},
            ],
            "generated_artifacts": [
                {"kind": "setup_script_bash", "target": "scripts/setup.sh"},
            ],
        }
        files = {"proxy/config/config.yaml": "key: val\n"}

        monkeypatch.setattr(
            "codefreedom.recipe.plan.get_codefreedom_dir", lambda: cf_dir
        )
        monkeypatch.setattr(
            "codefreedom.recipe.plan._resolve_store",
            lambda store, branch=None: tmp_path / "store",
        )
        monkeypatch.setattr(
            "codefreedom.recipe.plan._resolve_recipe_branch",
            lambda: "main",
        )
        monkeypatch.setattr(
            "codefreedom.recipe.plan._store_resolve_recipe",
            lambda name, store_path=None: (manifest, files),
        )

        from codefreedom.recipe.plan import plan_recipe

        rc = plan_recipe("gen-recipe")
        assert rc == 0

        captured = capsys.readouterr()
        assert "gen-recipe" in captured.out
        assert "scripts/setup.sh" in captured.out


# ═══════════════════════════════════════════════════════════════════════════════
# Custom Store (--store flag)
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolveRecipeWithStore:
    def test_store_takes_priority(self, tmp_path):
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
        with mock.patch(
            "codefreedom.recipe.store._find_local_recipe",
            return_value=None,
        ):
            store = tmp_path / "empty-store"
            store.mkdir()
            manifest, files = _resolve_recipe("fallback-recipe", store_path=store)
            assert manifest is None
            assert files == {}


# ═══════════════════════════════════════════════════════════════════════════════
# Vars Interpolation
# ═══════════════════════════════════════════════════════════════════════════════


class TestVarsInterpolation:
    def test_install_recipe_files_interpolates_vars(self, tmp_path):
        from codefreedom.recipe.apply import _install_recipe_files

        manifest = {
            "files": [
                {"path": "test.yaml", "target": "test.yaml", "merge": "deepdiff"},
            ]
        }
        files = {"test.yaml": "proxy_url: ${PROXY_BASE_URL}\n"}
        vars_dict = {"PROXY_BASE_URL": "http://localhost:4000"}

        count = _install_recipe_files(
            manifest, files, tmp_path, vars_dict=vars_dict, config_dir=tmp_path
        )
        assert count == 1

        content = (tmp_path / "test.yaml").read_text()
        assert "http://localhost:4000" in content
        assert "${PROXY_BASE_URL}" not in content


# ═══════════════════════════════════════════════════════════════════════════════


def test_plan_recipe_splits_by_key(monkeypatch, tmp_path, capsys):
    from codefreedom.recipe import plan as plan_module

    cf_dir = tmp_path / ".codefreedom"
    cf_dir.mkdir()

    manifest = {
        "name": "test",
        "files": [
            {
                "path": "coding-agents.yaml",
                "target": "profiles/",
                "merge": "deepdiff",
                "split_by_key": "profiles",
            }
        ],
    }

    combined_content = yaml.dump(
        {
            "common": {"tools": ["chrome"]},
            "profiles": {
                "claude-code": {"description": "Claude"},
                "mimo-code": {"description": "MiMo"},
            },
        },
        default_flow_style=False,
    )

    files = {"coding-agents.yaml": combined_content}

    monkeypatch.setattr(plan_module, "get_codefreedom_dir", lambda: cf_dir)
    monkeypatch.setattr(
        plan_module,
        "_store_resolve_recipe",
        lambda name, store_path=None: (manifest, files),
    )
    monkeypatch.setattr(
        plan_module,
        "_resolve_store",
        lambda store, branch=None: None,
    )
    monkeypatch.setattr(
        plan_module,
        "_resolve_recipe_branch",
        lambda: "main",
    )

    rc = plan_module.plan_recipe("test")
    assert rc == 0

    captured = capsys.readouterr()
    assert "profiles/claude-code.yaml" in captured.out
    assert "profiles/mimo-code.yaml" in captured.out
