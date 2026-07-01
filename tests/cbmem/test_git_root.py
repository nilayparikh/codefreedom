"""Tests for ``codebase_memory.git_root``.

The package is git-locked: a workspace is a git repo, and the project
root is whatever ``git rev-parse --show-toplevel`` returns. These tests
cover the lookup, the level bound, and the failure modes.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from codebase_memory import git_root


def _git(cwd: Path, *args: str) -> None:
    """Run a git command in ``cwd`` (raises on failure)."""
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def _make_repo(directory: Path) -> Path:
    """Initialize a git repo at ``directory`` with one commit."""
    directory.mkdir(parents=True, exist_ok=True)
    _git(directory, "init", "-q")
    _git(directory, "config", "user.email", "test@test.local")
    _git(directory, "config", "user.name", "Test")
    (directory / "README.md").write_text("hello\n")
    _git(directory, "add", "README.md")
    _git(directory, "commit", "-q", "-m", "init")
    return directory


class TestIsGitAvailable:
    def test_returns_true_when_git_on_path(self):
        assert git_root.is_git_available() is True


class TestFindProjectRoot:

    def test_cwd_at_repo_root(self, tmp_path):
        repo = _make_repo(tmp_path / "proj")
        assert git_root.find_project_root(repo) == repo.resolve()

    def test_cwd_in_subdirectory(self, tmp_path):
        repo = _make_repo(tmp_path / "proj")
        sub = repo / "src" / "api" / "v2"
        sub.mkdir(parents=True)
        assert git_root.find_project_root(sub) == repo.resolve()

    def test_cwd_one_level_above(self, tmp_path):
        """The walk goes 3 levels up max. From a sibling dir 1 level above,
        no .git is found, so it raises."""
        _make_repo(tmp_path / "proj")
        sibling = tmp_path / "sibling"
        sibling.mkdir()
        with pytest.raises(git_root.NotInGitRepo):
            git_root.find_project_root(sibling)

    def test_cwd_inside_repo_with_2_level_bound(self, tmp_path):
        """From 4 levels deep, the walk stops at level 3 (3 parents up)."""
        repo = _make_repo(tmp_path / "proj")
        deep = repo / "a" / "b" / "c" / "d" / "e"  # 5 levels deep
        deep.mkdir(parents=True)
        # From 'e', parents are: d (1), c (2), b (3), a (4), repo (5)
        # The bound is 3 levels up from the original CWD, so 'b' is the
        # last level we check. 'b' has no .git, so we raise.
        with pytest.raises(git_root.NotInGitRepo):
            git_root.find_project_root(deep)

    def test_cwd_at_repo_root_works_with_3_level_bound(self, tmp_path):
        """From 3 levels deep in a repo, the walk finds the toplevel."""
        repo = _make_repo(tmp_path / "proj")
        three_deep = repo / "a" / "b" / "c"
        three_deep.mkdir(parents=True)
        assert git_root.find_project_root(three_deep) == repo.resolve()

    def test_raises_when_cwd_not_directory(self, tmp_path):
        missing = tmp_path / "nope"
        with pytest.raises(git_root.NotInGitRepo):
            git_root.find_project_root(missing)

    def test_raises_when_cwd_has_no_git(self, tmp_path):
        with pytest.raises(git_root.NotInGitRepo):
            git_root.find_project_root(tmp_path)

    def test_resolves_relative_path(self, tmp_path, monkeypatch):
        repo = _make_repo(tmp_path / "proj")
        monkeypatch.chdir(repo)
        assert git_root.find_project_root(Path(".")) == repo.resolve()

    def test_worktree_git_file_is_recognized(self, tmp_path):
        """A ``.git`` *file* (worktree pointer) should also count."""
        # Create a main repo.
        main = _make_repo(tmp_path / "main")
        # Create a worktree.
        wt_dir = tmp_path / "wt"
        result = subprocess.run(
            [
                "git",
                "-C",
                str(main),
                "worktree",
                "add",
                "-b",
                f"wt-branch-{uuid4().hex[:8]}",
                str(wt_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.skip(result.stderr.strip() or "git worktree add unavailable")
        # The worktree's ``.git`` is a file that points at ``main/.git/worktrees/wt``.
        # From the worktree, find_project_root should return the worktree's
        # working tree (because git rev-parse knows about worktrees).
        assert git_root.find_project_root(wt_dir) == wt_dir.resolve()

    def test_bare_repo_falls_back_to_git_dir(self, tmp_path):
        """A repo with ``core.bare=true`` (misconfigured non-bare) should
        still resolve via ``--git-dir`` fallback.
        """
        repo = _make_repo(tmp_path / "proj")
        _git(repo, "config", "core.bare", "true")
        result = git_root.find_project_root(repo)
        assert result == repo.resolve()

    def test_bare_repo_from_subdirectory(self, tmp_path):
        """From a subdirectory of a bare-flagged repo, the walk finds it."""
        repo = _make_repo(tmp_path / "proj")
        _git(repo, "config", "core.bare", "true")
        sub = repo / "src" / "api"
        sub.mkdir(parents=True)
        result = git_root.find_project_root(sub)
        assert result == repo.resolve()
