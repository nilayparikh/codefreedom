"""Integration tests for the ``cf s folder [path]`` subcommand and .cf.yaml wiring.

End-to-end coverage of:
  - ``cf setup folder <path>`` writes ``<path>/.cf.yaml`` from the
    current ``override.yaml`` (default path is current directory).
  - The standalone ``seed_cf_yaml()`` public entry point.
  - Argparse wiring: ``cf s folder``, ``cf s f``, ``--force``.
  - ``load_config(cf_yaml_path=...)`` reads .cf.yaml as the highest
    YAML layer (above override.yaml, below CF_CLI_*).
  - The display layer reports the .cf.yaml source correctly.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
import yaml

from codefreedom.cli.main import _build_folder_args, _dispatch_folder
from codefreedom.config import load_config
from codefreedom.config.display import resolve_value_source
from codefreedom.recipe.plan import seed_cf_yaml

pytestmark = pytest.mark.integration


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def _seed_config_dir(cf_dir: Path, override: dict | None = None) -> Path:
    """Create a minimal ``override.yaml`` under ``cf_dir/config``.

    Returns the config dir (so callers can pass it to ``seed_cf_yaml``).
    """
    config_dir = cf_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    _write_yaml(config_dir / "override.yaml", override or {
        "vars": {"SUFFIX_ID": "demo"},
        "tools": {"chrome": {}},
    })
    return config_dir


class TestSeedCfYamlPublic:
    def test_seed_writes_cf_yaml_to_target(self, tmp_path: Path, monkeypatch) -> None:
        config_dir = _seed_config_dir(tmp_path / "cf")
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path / "cf"))

        target = tmp_path / "myproject"
        rc = seed_cf_yaml(config_dir=config_dir, folder=str(target))

        assert rc == 0
        out = target / ".cf.yaml"
        assert out.is_file()
        loaded = yaml.safe_load(out.read_text(encoding="utf-8"))
        assert loaded == {
            "vars": {"SUFFIX_ID": "demo"},
            "tools": {"chrome": {}},
        }

    def test_seed_defaults_to_cwd(self, tmp_path: Path, monkeypatch) -> None:
        config_dir = _seed_config_dir(tmp_path / "cf")
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path / "cf"))
        monkeypatch.chdir(tmp_path)

        rc = seed_cf_yaml(config_dir=config_dir)

        assert rc == 0
        assert (tmp_path / ".cf.yaml").is_file()

    def test_seed_refuses_overwrite_without_force(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        config_dir = _seed_config_dir(tmp_path / "cf")
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path / "cf"))

        target = tmp_path / "out"
        target.mkdir()
        existing = target / ".cf.yaml"
        existing.write_text("vars:\n  SUFFIX_ID: user_kept\n", encoding="utf-8")

        rc = seed_cf_yaml(config_dir=config_dir, folder=str(target))

        assert rc == 1
        kept = yaml.safe_load(existing.read_text(encoding="utf-8"))
        assert kept == {"vars": {"SUFFIX_ID": "user_kept"}}

    def test_seed_force_overwrites(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        config_dir = _seed_config_dir(
            tmp_path / "cf",
            override={"vars": {"SUFFIX_ID": "fresh"}},
        )
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path / "cf"))

        target = tmp_path / "out"
        target.mkdir()
        existing = target / ".cf.yaml"
        existing.write_text("vars:\n  SUFFIX_ID: stale\n", encoding="utf-8")

        rc = seed_cf_yaml(config_dir=config_dir, folder=str(target), force=True)

        assert rc == 0
        loaded = yaml.safe_load(existing.read_text(encoding="utf-8"))
        assert loaded == {"vars": {"SUFFIX_ID": "fresh"}}

    def test_seed_fails_when_override_missing(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """No override.yaml in config_dir — return failure (no crash)."""
        config_dir = tmp_path / "cf" / "config"
        config_dir.mkdir(parents=True)
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path / "cf"))

        rc = seed_cf_yaml(config_dir=config_dir, folder=str(tmp_path / "out"))
        assert rc == 1
        assert not (tmp_path / "out" / ".cf.yaml").exists()


class TestDispatchFolder:
    def test_dispatch_writes_cf_yaml_to_arg_path(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        _seed_config_dir(tmp_path / "cf")
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path / "cf"))

        target = tmp_path / "myproject"

        with pytest.raises(SystemExit) as exc_info:
            _dispatch_folder(argparse.Namespace(path=str(target), force=False))

        assert exc_info.value.code == 0
        assert (target / ".cf.yaml").is_file()

    def test_dispatch_defaults_to_cwd(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        _seed_config_dir(tmp_path / "cf")
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path / "cf"))
        monkeypatch.chdir(tmp_path)

        with pytest.raises(SystemExit) as exc_info:
            _dispatch_folder(argparse.Namespace(path=".", force=False))

        assert exc_info.value.code == 0
        assert (tmp_path / ".cf.yaml").is_file()

    def test_dispatch_force_overwrites(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        _seed_config_dir(
            tmp_path / "cf",
            override={"vars": {"SUFFIX_ID": "from_init"}},
        )
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path / "cf"))

        target = tmp_path / "out"
        target.mkdir()
        (target / ".cf.yaml").write_text(
            "vars:\n  SUFFIX_ID: user_kept\n", encoding="utf-8"
        )

        with pytest.raises(SystemExit) as exc_info:
            _dispatch_folder(argparse.Namespace(path=str(target), force=True))

        assert exc_info.value.code == 0
        loaded = yaml.safe_load((target / ".cf.yaml").read_text(encoding="utf-8"))
        assert loaded == {"vars": {"SUFFIX_ID": "from_init"}}


class TestArgparseFolderCommand:
    def test_path_is_positional_and_optional(self) -> None:
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd")
        folder = sub.add_parser("folder")
        _build_folder_args(folder)

        ns = parser.parse_args(["folder"])
        assert ns.path == "."
        assert ns.force is False

    def test_path_explicit(self) -> None:
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd")
        folder = sub.add_parser("folder")
        _build_folder_args(folder)

        ns = parser.parse_args(["folder", "/tmp/myproj"])
        assert ns.path == "/tmp/myproj"

    def test_force_flag(self) -> None:
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd")
        folder = sub.add_parser("folder")
        _build_folder_args(folder)

        ns = parser.parse_args(["folder", ".", "--force"])
        assert ns.force is True


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
