"""Integration tests for the ``cf s i -f <folder>`` flag and .cf.yaml wiring.

End-to-end coverage of:
  - ``cf setup init --folder <path>`` writes ``<path>/.cf.yaml`` from
    the current ``override.yaml``.
  - ``load_config(cf_yaml_path=...)`` reads .cf.yaml as the highest
    YAML layer (above override.yaml, below CF_CLI_*).
  - The display layer reports the .cf.yaml source correctly.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest import mock

import pytest
import yaml

from codefreedom.cli.main import _build_init_args, _dispatch_init
from codefreedom.config import load_config
from codefreedom.config.display import resolve_value_source

pytestmark = pytest.mark.integration


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


class TestInitRecipeWithFolderFlag:
    def test_folder_flag_writes_cf_yaml(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """``cf s i -f <folder>`` (with no recipe) creates ``<folder>/.cf.yaml``.

        We can't reach ``init_recipe`` without a real recipe network fetch,
        so we exercise the dispatch + flag plumbing with a mocked
        ``init_recipe`` and a seeded ``override.yaml`` in CODEFREEDOM_HOME.
        """
        cf_dir = tmp_path / ".codefreedom"
        config_dir = cf_dir / "config"
        config_dir.mkdir(parents=True)
        _write_yaml(config_dir / "override.yaml", {
            "vars": {"SUFFIX_ID": "demo"},
            "tools": {"chrome": {}},
        })
        monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_dir))

        target_folder = tmp_path / "myproject"

        captured: dict = {}

        def fake_init(name, store=None, staging=False, folder=None):
            captured["name"] = name
            captured["folder"] = folder
            from codefreedom.recipe.plan import _write_cf_yaml
            _write_cf_yaml(config_dir, folder)
            return 0

        with mock.patch(
            "codefreedom.cli.setup.recipe.init_recipe", side_effect=fake_init
        ):
            with pytest.raises(SystemExit) as exc_info:
                _dispatch_init(argparse.Namespace(
                    recipe="my-recipe",
                    list=False,
                    apply=None,
                    plan_and_apply=None,
                    plan=None,
                    store=None,
                    staging=False,
                    folder=str(target_folder),
                ))

        assert exc_info.value.code == 0
        assert captured["folder"] == str(target_folder)

        out = target_folder / ".cf.yaml"
        assert out.is_file()
        loaded = yaml.safe_load(out.read_text(encoding="utf-8"))
        assert loaded == {
            "vars": {"SUFFIX_ID": "demo"},
            "tools": {"chrome": {}},
        }

    def test_folder_flag_refuses_overwrite(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """Existing ``<folder>/.cf.yaml`` is left alone — init warns and continues."""
        cf_dir = tmp_path / ".codefreedom"
        config_dir = cf_dir / "config"
        config_dir.mkdir(parents=True)
        _write_yaml(config_dir / "override.yaml", {
            "vars": {"SUFFIX_ID": "fresh"},
        })
        monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_dir))

        target_folder = tmp_path / "myproject"
        target_folder.mkdir()
        existing = target_folder / ".cf.yaml"
        existing.write_text(
            "vars:\n  SUFFIX_ID: user_kept\n",
            encoding="utf-8",
        )

        from codefreedom.recipe.plan import _write_cf_yaml
        _write_cf_yaml(config_dir, str(target_folder))

        kept = yaml.safe_load(existing.read_text(encoding="utf-8"))
        assert kept == {"vars": {"SUFFIX_ID": "user_kept"}}

    def test_folder_flag_creates_missing_folder(self, tmp_path: Path, monkeypatch) -> None:
        cf_dir = tmp_path / ".codefreedom"
        config_dir = cf_dir / "config"
        config_dir.mkdir(parents=True)
        _write_yaml(config_dir / "override.yaml", {"vars": {"SUFFIX_ID": "x"}})
        monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_dir))

        target = tmp_path / "deep" / "nested" / "out"
        assert not target.exists()

        from codefreedom.recipe.plan import _write_cf_yaml
        _write_cf_yaml(config_dir, str(target))

        assert target.is_dir()
        assert (target / ".cf.yaml").is_file()


class TestArgparseFolderFlag:
    def test_folder_flag_is_parsed(self) -> None:
        """``-f <path>`` and ``--folder <path>`` populate ``args.folder``."""
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd")
        init = sub.add_parser("init")
        _build_init_args(init)

        ns = parser.parse_args(["init", "-f", "/tmp/foo"])
        assert ns.folder == "/tmp/foo"

        ns2 = parser.parse_args(["init", "--folder", "/tmp/bar"])
        assert ns2.folder == "/tmp/bar"

    def test_folder_flag_optional(self) -> None:
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd")
        init = sub.add_parser("init")
        _build_init_args(init)

        ns = parser.parse_args(["init"])
        assert ns.folder is None


class TestCfYamlEndToEnd:
    def test_full_layering_chain(self, tmp_path: Path, monkeypatch) -> None:
        """End-to-end: profiles < recipe < override < .cf.yaml < CF_CLI_*.

        Sets a distinct value at each layer and verifies the final
        resolved config picks the highest-precedence source.
        """
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))

        _write_yaml(config_dir / "profiles.yaml", {
            "agents": {"claude-code": {"profiles": {"default": {"env": {
                "A": "base", "B": "base", "C": "base", "D": "base",
            }}}}},
        })
        _write_yaml(config_dir / "recipe.yaml", {
            "vars": {},
            "agents": {"claude-code": {"profiles": {"default": {"env": {
                "B": "recipe", "C": "recipe", "D": "recipe",
            }}}}},
        })
        _write_yaml(config_dir / "override.yaml", {
            "agents": {"claude-code": {"profiles": {"default": {"env": {
                "C": "override", "D": "override",
            }}}}},
        })
        cf_yaml = config_dir / ".cf.yaml"
        _write_yaml(cf_yaml, {
            "agents": {"claude-code": {"profiles": {"default": {"env": {
                "D": "cf_yaml",
            }}}}},
        })

        config = load_config(config_dir, cf_yaml_path=cf_yaml)
        env = config.for_agent("claude-code").env
        assert env["A"] == "base"
        assert env["B"] == "recipe"
        assert env["C"] == "override"
        assert env["D"] == "cf_yaml"

    def test_cf_yaml_does_not_block_when_omitted(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        _write_yaml(config_dir / "profiles.yaml", {
            "agents": {"claude-code": {"profiles": {"default": {"env": {"A": "base"}}}}}
        })
        _write_yaml(config_dir / "override.yaml", {
            "agents": {"claude-code": {"profiles": {"default": {"env": {"A": "ov"}}}}}
        })

        config = load_config(config_dir)
        assert config.for_agent("claude-code").env["A"] == "ov"


class TestCfYamlSourceLabel:
    def test_source_label_reports_cf_yaml(self, tmp_path: Path, monkeypatch) -> None:
        """The display layer identifies a value as coming from ``.cf.yaml``."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        _write_yaml(config_dir / "profiles.yaml", {
            "vars": {"SUFFIX_ID": "base"},
        })

        cf_yaml = config_dir / ".cf.yaml"
        _write_yaml(cf_yaml, {"vars": {"SUFFIX_ID": "cf_yaml_value"}})

        monkeypatch.setenv("CF_CLI_CF_YAML", str(cf_yaml))
        monkeypatch.delenv("CF_CLI_SUFFIX_ID", raising=False)
        monkeypatch.delenv("SUFFIX_ID", raising=False)

        source = resolve_value_source(
            "SUFFIX_ID", "cf_yaml_value", config_dir, {}
        )

        assert source == ".cf.yaml"
