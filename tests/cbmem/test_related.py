"""Tests for ``codebase_memory.related`` — related git path validation."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from codebase_memory import related


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def _make_repo(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    _git(directory, "init", "-q")
    _git(directory, "config", "user.email", "t@t")
    _git(directory, "config", "user.name", "t")
    (directory / "README.md").write_text("hi")
    _git(directory, "add", "README.md")
    _git(directory, "commit", "-q", "-m", "init")
    return directory


class TestValidateRelatedPaths:

    def test_empty_list_returns_empty(self, tmp_path):
        out = related.validate_related_paths(tmp_path, [])
        assert out == []

    def test_valid_git_repo(self, tmp_path):
        main = _make_repo(tmp_path / "main")
        extra = _make_repo(tmp_path / "extra")
        out = related.validate_related_paths(main, [{"path": str(extra)}])
        assert out == [{"path": str(extra.resolve()), "alias": ""}]

    def test_alias_preserved(self, tmp_path):
        main = _make_repo(tmp_path / "main")
        extra = _make_repo(tmp_path / "extra")
        out = related.validate_related_paths(main, [{"path": str(extra), "alias": "  lib  "}])
        assert out[0]["alias"] == "lib"

    def test_missing_path_raises(self, tmp_path):
        main = _make_repo(tmp_path / "main")
        with pytest.raises(related.RelatedPathError, match="does not exist"):
            related.validate_related_paths(main, [{"path": str(tmp_path / "nope")}])

    def test_non_git_path_raises(self, tmp_path):
        main = _make_repo(tmp_path / "main")
        non_git = tmp_path / "dir"
        non_git.mkdir()
        with pytest.raises(related.RelatedPathError, match="not a git repository"):
            related.validate_related_paths(main, [{"path": str(non_git)}])

    def test_subdir_of_main_raises(self, tmp_path):
        main = _make_repo(tmp_path / "main")
        sub = main / "packages" / "shared"
        sub.mkdir(parents=True)
        _git(sub, "init", "-q")
        _git(sub, "config", "user.email", "t@t")
        _git(sub, "config", "user.name", "t")
        (sub / "x").write_text("x")
        _git(sub, "add", "x")
        _git(sub, "commit", "-q", "-m", "init")
        with pytest.raises(related.RelatedPathError, match="subdirectory"):
            related.validate_related_paths(main, [{"path": str(sub)}])

    def test_duplicate_raises(self, tmp_path):
        main = _make_repo(tmp_path / "main")
        extra = _make_repo(tmp_path / "extra")
        with pytest.raises(related.RelatedPathError, match="duplicate"):
            related.validate_related_paths(
                main,
                [{"path": str(extra)}, {"path": str(extra)}],
            )

    def test_missing_path_key_raises(self, tmp_path):
        main = _make_repo(tmp_path / "main")
        with pytest.raises(related.RelatedPathError, match="missing 'path'"):
            related.validate_related_paths(main, [{"alias": "x"}])

    def test_non_dict_entry_raises(self, tmp_path):
        main = _make_repo(tmp_path / "main")
        with pytest.raises(related.RelatedPathError, match="must be a mapping"):
            related.validate_related_paths(main, ["not a dict"])  # type: ignore[list-item]

    def test_path_resolves_tilde(self, tmp_path, monkeypatch):
        main = _make_repo(tmp_path / "main")
        extra = _make_repo(tmp_path / "extra")
        home = tmp_path / "home"
        home.mkdir()
        # Symlink so `~/extra` is the extra repo
        link = home / "extra"
        link.symlink_to(extra)
        monkeypatch.setenv("HOME", str(home))
        out = related.validate_related_paths(main, [{"path": "~/extra"}])
        assert out[0]["path"] == str(extra.resolve())


class TestContainerSubpaths:

    def test_simple(self, tmp_path):
        main = tmp_path / "main"
        main.mkdir()
        out = related.container_subpaths(main, [{"path": "/foo/shared-lib"}])
        assert out == [("/foo/shared-lib", "/workspace/shared-lib")]

    def test_collision_appends_suffix(self, tmp_path):
        main = tmp_path / "main"
        main.mkdir()
        out = related.container_subpaths(
            main,
            [{"path": "/a/shared"}, {"path": "/b/shared"}],
        )
        assert out == [
            ("/a/shared", "/workspace/shared"),
            ("/b/shared", "/workspace/shared-1"),
        ]

    def test_three_way_collision(self, tmp_path):
        main = tmp_path / "main"
        main.mkdir()
        out = related.container_subpaths(
            main,
            [{"path": "/a/x"}, {"path": "/b/x"}, {"path": "/c/x"}],
        )
        assert out[1][1] == "/workspace/x-1"
        assert out[2][1] == "/workspace/x-2"
