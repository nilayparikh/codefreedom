"""Unit tests for the ``_write_cf_yaml`` recipe helper.

The helper is invoked by ``cf setup init --folder <path>`` to copy the
active ``override.yaml`` into a local ``.cf.yaml`` so the user can
edit per-folder overrides without touching the global config.

Tests are pure-function (no Docker, no network) — they exercise the
filesystem side-effects only.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from codefreedom.recipe.plan import _write_cf_yaml

pytestmark = pytest.mark.unit


class TestWriteCfYamlNoop:
    def test_no_op_when_folder_is_none(self, tmp_path: Path) -> None:
        """``folder=None`` must not create or touch any file."""
        _write_cf_yaml(tmp_path, None)
        assert list(tmp_path.iterdir()) == []

    def test_no_op_when_folder_is_empty_string(self, tmp_path: Path) -> None:
        _write_cf_yaml(tmp_path, "")
        assert list(tmp_path.iterdir()) == []


class TestWriteCfYamlCreatesFile:
    def test_creates_cf_yaml_in_target_folder(self, tmp_path: Path) -> None:
        """Writes ``<folder>/.cf.yaml`` containing the override contents."""
        override = tmp_path / "override.yaml"
        override.write_text(
            "vars:\n  SUFFIX_ID: coding\n",
            encoding="utf-8",
        )

        target = tmp_path / "out"
        _write_cf_yaml(tmp_path, str(target))

        out_file = target / ".cf.yaml"
        assert out_file.is_file()
        loaded = yaml.safe_load(out_file.read_text(encoding="utf-8"))
        assert loaded == {"vars": {"SUFFIX_ID": "coding"}}

    def test_creates_target_folder_if_missing(self, tmp_path: Path) -> None:
        """The target folder is auto-created."""
        (tmp_path / "override.yaml").write_text("x: 1\n", encoding="utf-8")

        target = tmp_path / "deep" / "nested" / "out"
        assert not target.exists()

        _write_cf_yaml(tmp_path, str(target))

        assert target.is_dir()
        assert (target / ".cf.yaml").is_file()

    def test_relative_folder_resolved_against_cwd(self, tmp_path: Path, monkeypatch) -> None:
        """Relative folder paths are resolved against the process CWD."""
        (tmp_path / "override.yaml").write_text("x: 1\n", encoding="utf-8")

        work = tmp_path / "work"
        work.mkdir()
        monkeypatch.chdir(work)

        _write_cf_yaml(tmp_path, "rel-out")

        assert (work / "rel-out" / ".cf.yaml").is_file()


class TestWriteCfYamlRefusesOverwrite:
    def test_skips_when_target_exists(self, tmp_path: Path) -> None:
        """If ``<folder>/.cf.yaml`` already exists, do not overwrite it."""
        (tmp_path / "override.yaml").write_text(
            "vars:\n  SUFFIX_ID: fresh\n", encoding="utf-8"
        )

        target = tmp_path / "out"
        target.mkdir()
        existing = target / ".cf.yaml"
        existing.write_text(
            "vars:\n  SUFFIX_ID: user_kept_this\n",
            encoding="utf-8",
        )

        _write_cf_yaml(tmp_path, str(target))

        kept = yaml.safe_load(existing.read_text(encoding="utf-8"))
        assert kept == {"vars": {"SUFFIX_ID": "user_kept_this"}}


class TestWriteCfYamlMissingOverride:
    def test_returns_silently_when_override_missing(self, tmp_path: Path, caplog) -> None:
        """If ``override.yaml`` is missing in cf_dir, do not crash — just skip."""
        target = tmp_path / "out"
        target.mkdir()

        _write_cf_yaml(tmp_path, str(target))

        assert not (target / ".cf.yaml").exists()


class TestWriteCfYamlContent:
    def test_copies_full_override_yaml_verbatim(self, tmp_path: Path) -> None:
        """The output is a byte-for-byte copy of the override.yaml file."""
        content = (
            "comment: User overrides\n"
            "vars:\n"
            "  SUFFIX_ID: demo\n"
            "  POSTGRES_HOST_PORT: '5433'\n"
            "tools:\n"
            "  chrome: {}\n"
        )
        (tmp_path / "override.yaml").write_text(content, encoding="utf-8")

        target = tmp_path / "out"
        _write_cf_yaml(tmp_path, str(target))

        out = (target / ".cf.yaml").read_text(encoding="utf-8")
        assert out == content
