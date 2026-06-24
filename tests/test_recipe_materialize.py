"""Tests for recipe materialization module."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


class TestFlattenRecipeChain:
    def test_flatten_recipe_chain_merges_base(self) -> None:
        from codefreedom.recipe.materialize import flatten_recipe_chain

        base = {
            "name": "base",
            "version": 1,
            "files": [
                {"path": "base/file.txt", "merge": "auto"},
            ],
            "required_secrets": [{"var": "BASE_KEY"}],
            "dirs": ["data"],
        }
        child = {
            "name": "child",
            "extends": "base",
            "files": [
                {"path": "child/file.txt", "merge": "overwrite"},
            ],
            "required_secrets": [{"var": "CHILD_KEY"}],
        }
        result = flatten_recipe_chain(child, base)
        assert result["name"] == "child"
        file_targets = [f["target"] for f in result["files"]]
        assert "child/file.txt" in file_targets
        assert "base/file.txt" in file_targets
        secret_vars = [s["var"] for s in result["required_secrets"]]
        assert "CHILD_KEY" in secret_vars
        assert "BASE_KEY" in secret_vars
        assert result["dirs"] == ["data"]

    def test_flatten_recipe_chain_child_overrides(self) -> None:
        from codefreedom.recipe.materialize import flatten_recipe_chain

        base = {
            "name": "base",
            "files": [
                {"path": "shared/file.txt", "merge": "auto"},
            ],
            "required_secrets": [{"var": "SHARED_KEY", "prompt": "Base prompt"}],
        }
        child = {
            "name": "child",
            "files": [
                {"path": "shared/file.txt", "merge": "overwrite"},
            ],
            "required_secrets": [{"var": "SHARED_KEY", "prompt": "Child prompt"}],
        }
        result = flatten_recipe_chain(child, base)
        secrets_by_var = {s["var"]: s for s in result["required_secrets"]}
        assert secrets_by_var["SHARED_KEY"]["prompt"] == "Child prompt"
        files_by_target = {f["target"]: f for f in result["files"]}
        assert files_by_target["shared/file.txt"]["merge"] == "overwrite"

    def test_flatten_recipe_chain_no_base(self) -> None:
        from codefreedom.recipe.materialize import flatten_recipe_chain

        child = {
            "name": "solo",
            "files": [{"path": "a.txt"}],
        }
        result = flatten_recipe_chain(child, None)
        assert result == child


def test_recipe_schema_accepts_split_by_key():
    from codefreedom.schemas.recipe import RecipeConfig

    data = {
        "name": "demo",
        "files": [
            {
                "path": "coding-agents.yaml",
                "target": "profiles/",
                "merge": "deepdiff",
                "split_by_key": "profiles",
            }
        ],
    }
    model = RecipeConfig.model_validate(data)
    assert model.files[0].split_by_key == "profiles"


def test_recipe_schema_accepts_vars_field():
    from codefreedom.schemas.recipe import RecipeConfig

    data = {
        "name": "demo",
        "files": [],
        "vars": "recipe.vars.yaml",
    }
    model = RecipeConfig.model_validate(data)
    assert model.vars == "recipe.vars.yaml"


class TestMergeRecipeBlocks:
    def test_merge_recipe_blocks_resolves_secrets(self) -> None:
        from codefreedom.recipe.materialize import merge_recipe_blocks

        manifest = {
            "name": "demo",
            "files": [{"path": "config.yaml"}],
            "common_blocks": {
                "secret_groups": {
                    "proxy": {
                        "required_secrets": [
                            {"var": "LITELLM_MASTER_KEY", "prompt": "Proxy key"},
                            {"var": "OPENROUTER_API_KEY", "prompt": "OpenRouter key"},
                        ]
                    }
                }
            },
        }
        result = merge_recipe_blocks(manifest)
        secret_vars = [s["var"] for s in result["required_secrets"]]
        assert "LITELLM_MASTER_KEY" in secret_vars
        assert "OPENROUTER_API_KEY" in secret_vars

    def test_merge_recipe_blocks_merges_all_groups(self) -> None:
        from codefreedom.recipe.materialize import merge_recipe_blocks

        manifest = {
            "name": "multi",
            "files": [],
            "required_secrets": [{"var": "EXISTING_KEY"}],
            "common_blocks": {
                "secret_groups": {
                    "proxy": {
                        "required_secrets": [
                            {"var": "PROXY_KEY", "prompt": "Proxy"},
                        ]
                    },
                    "azure": {
                        "required_secrets": [
                            {"var": "AZURE_KEY", "prompt": "Azure"},
                        ]
                    },
                }
            },
        }
        result = merge_recipe_blocks(manifest)
        secret_vars = [s["var"] for s in result["required_secrets"]]
        assert "EXISTING_KEY" in secret_vars
        assert "PROXY_KEY" in secret_vars
        assert "AZURE_KEY" in secret_vars

    def test_merge_recipe_blocks_no_common_blocks(self) -> None:
        from codefreedom.recipe.materialize import merge_recipe_blocks

        manifest = {
            "name": "plain",
            "files": [{"path": "a.txt"}],
            "required_secrets": [{"var": "KEY"}],
        }
        result = merge_recipe_blocks(manifest)
        assert result["required_secrets"] == [{"var": "KEY"}]


class TestMaterializeRecipe:
    def test_materialize_recipe_preserves_static_files(self) -> None:
        from codefreedom.recipe.materialize import materialize_recipe

        manifest = {
            "name": "static-recipe",
            "files": [
                {"path": "config.yaml", "target": "config.yaml", "merge": "auto"},
                {"path": "proxy/config/providers/opencode.yaml", "merge": "deepdiff"},
            ],
        }
        files = {
            "config.yaml": "key: value",
            "proxy/config/providers/opencode.yaml": "providers:\n  - name: test",
        }
        result = materialize_recipe(manifest, files)
        entries = [e for e in result["entries"] if e["type"] == "static"]
        assert len(entries) == 2
        targets = {e["target"] for e in entries}
        assert "config.yaml" in targets
        assert "proxy/config/providers/opencode.yaml" in targets
        for e in entries:
            assert e["content"]
            assert e["merge"] in ("auto", "deepdiff", "env", "overwrite")

    def test_materialize_recipe_outputs_generated_setup_script(self) -> None:
        from codefreedom.recipe.materialize import materialize_recipe

        manifest = {
            "name": "demo",
            "files": [],
            "required_secrets": [
                {"var": "LITELLM_MASTER_KEY", "prompt": "Proxy key"},
            ],
            "generated_artifacts": [
                {
                    "kind": "setup_script_bash",
                    "target": "scripts/demo/setup-secrets.sh",
                },
            ],
        }
        files = {}
        result = materialize_recipe(manifest, files)
        generated = [e for e in result["entries"] if e["type"] == "generated"]
        assert len(generated) == 1
        assert generated[0]["target"] == "scripts/demo/setup-secrets.sh"
        assert generated[0]["kind"] == "setup_script_bash"
        assert "#!/usr/bin/env bash" in generated[0]["content"]

    def test_materialize_recipe_managed_targets_complete(self) -> None:
        from codefreedom.recipe.materialize import materialize_recipe

        manifest = {
            "name": "full",
            "files": [
                {"path": "config.yaml", "target": "config.yaml"},
            ],
            "generated_artifacts": [
                {
                    "kind": "env_template",
                    "target": ".env.secrets",
                },
            ],
            "required_secrets": [
                {"var": "API_KEY", "prompt": "API key"},
            ],
        }
        files = {"config.yaml": "data: true"}
        result = materialize_recipe(manifest, files)
        assert "config.yaml" in result["managed_targets"]
        assert ".env.secrets" in result["managed_targets"]

    def test_materialize_recipe_summary_metadata(self) -> None:
        from codefreedom.recipe.materialize import materialize_recipe

        manifest = {
            "name": "summary-test",
            "files": [
                {"path": "a.yaml"},
                {"path": "b.yaml"},
            ],
            "required_secrets": [
                {"var": "S1"},
                {"var": "S2"},
                {"var": "S3"},
            ],
            "config_vars": [
                {"var": "C1"},
            ],
            "generated_artifacts": [
                {
                    "kind": "setup_script_bash",
                    "target": "scripts/setup.sh",
                },
                {
                    "kind": "env_template",
                    "target": ".env.secrets",
                },
            ],
        }
        files = {"a.yaml": "a: 1", "b.yaml": "b: 2"}
        result = materialize_recipe(manifest, files)
        summary = result["summary"]
        assert summary["recipe"] == "summary-test"
        assert summary["static_count"] == 2
        assert summary["generated_count"] == 2
        assert summary["secret_count"] == 3
        assert summary["config_count"] == 1
