"""Integration tests for cf git — config loading, init, git operations."""

from __future__ import annotations

import subprocess

import pytest
import yaml

from codefreedom.cli.git.config import (
    get_model,
    get_modules,
    is_conventional_commit,
    is_signed_commit,
    load_global_git_config,
    load_project_git_config,
    load_git_config,
)
from codefreedom.cli.git.git_ops import (
    commit,
    get_changed_files,
    get_current_branch,
    get_git_root,
    get_staged_diff,
    get_staged_files,
    get_status,
    is_git_repo,
    parse_remote_owner_repo,
    stage_files,
)
from codefreedom.cli.git.init_cmd import _detect_modules, run_init

pytestmark = pytest.mark.integration


@pytest.fixture
def git_repo(tmp_path):
    subprocess.run(["git", "init"], capture_output=True, cwd=str(tmp_path))
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        capture_output=True, cwd=str(tmp_path),
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        capture_output=True, cwd=str(tmp_path),
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"],
        capture_output=True, cwd=str(tmp_path),
    )
    return tmp_path


# ── Config loading ────────────────────────────────────────────────────────


class TestLoadGlobalGitConfig:
    def test_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_codefreedom_dir",
            lambda: tmp_path,
        )
        result = load_global_git_config()
        assert result == {}

    def test_loads_yaml(self, tmp_path, monkeypatch):
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / "git.yaml").write_text(
            yaml.dump({"git": {"model": "gpt-4o", "signed_commit": False}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_codefreedom_dir",
            lambda: tmp_path,
        )
        result = load_global_git_config()
        assert result["model"] == "gpt-4o"
        assert result["signed_commit"] is False


class TestLoadProjectGitConfig:
    def test_no_git_root(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_git_root",
            lambda _=None: None,
        )
        result = load_project_git_config(tmp_path)
        assert result == {}

    def test_loads_cf_yaml(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_git_root",
            lambda _=None: tmp_path,
        )
        (tmp_path / ".cf.yaml").write_text(
            yaml.dump({"git": {"modules": ["cli", "core"]}}),
            encoding="utf-8",
        )
        result = load_project_git_config(tmp_path)
        assert result["modules"] == ["cli", "core"]


class TestLoadGitConfig:
    def test_resolution_order(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_git_root",
            lambda _=None: tmp_path,
        )
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_codefreedom_dir",
            lambda: tmp_path,
        )
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / "git.yaml").write_text(
            yaml.dump({"git": {"model": "gpt-4o", "signed_commit": True}}),
            encoding="utf-8",
        )
        (tmp_path / ".cf.yaml").write_text(
            yaml.dump({"git": {"model": "gpt-4o-mini"}}),
            encoding="utf-8",
        )
        config = load_git_config(tmp_path)
        assert config["model"] == "gpt-4o-mini"
        assert config["signed_commit"] is True


class TestConfigHelpers:
    def test_get_model_default(self):
        assert get_model({}) == "gpt-4o-mini"

    def test_get_model_custom(self):
        assert get_model({"model": "gpt-4o"}) == "gpt-4o"

    def test_get_modules_default(self):
        assert get_modules({}) == []

    def test_get_modules_custom(self):
        assert get_modules({"modules": ["a", "b"]}) == ["a", "b"]

    def test_is_conventional_default(self):
        assert is_conventional_commit({}) is True

    def test_is_conventional_disabled(self):
        assert is_conventional_commit({"conventional_commit": False}) is False

    def test_is_signed_default(self):
        assert is_signed_commit({}) is True

    def test_is_signed_disabled(self):
        assert is_signed_commit({"signed_commit": False}) is False


# ── Git operations (real git repo) ────────────────────────────────────────


class TestGitOps:
    def test_is_git_repo(self, git_repo):
        assert is_git_repo(git_repo) is True

    def test_not_git_repo(self, tmp_path):
        assert is_git_repo(tmp_path) is False

    def test_get_git_root(self, git_repo):
        assert get_git_root(git_repo) == git_repo

    def test_get_current_branch(self, git_repo):
        branch = get_current_branch(git_repo)
        assert branch in ("main", "master")

    def test_get_status(self, git_repo):
        assert get_status(git_repo) == ""

    def test_stage_and_diff(self, git_repo):
        (git_repo / "file.txt").write_text("hello")
        stage_files(["file.txt"], cwd=git_repo)
        files = get_staged_files(git_repo)
        assert "file.txt" in files

        diff = get_staged_diff(git_repo)
        assert "hello" in diff

    def test_commit(self, git_repo):
        (git_repo / "file.txt").write_text("hello")
        stage_files(["file.txt"], cwd=git_repo)
        ok, _ = commit("test: initial commit", cwd=git_repo)
        assert ok is True
        assert get_staged_files(git_repo) == []

    def test_get_changed_files(self, git_repo):
        (git_repo / "file.txt").write_text("hello")
        files = get_changed_files(git_repo)
        assert "file.txt" in files

    def test_parse_remote_owner_repo_https(self):
        result = parse_remote_owner_repo("https://github.com/owner/repo.git")
        assert result == ("owner", "repo")

    def test_parse_remote_owner_repo_ssh(self):
        result = parse_remote_owner_repo("git@github.com:owner/repo.git")
        assert result == ("owner", "repo")

    def test_parse_remote_owner_repo_invalid(self):
        result = parse_remote_owner_repo("https://gitlab.com/owner/repo.git")
        assert result is None


# ── Module detection ──────────────────────────────────────────────────────


class TestDetectModules:
    def test_detects_src_dirs(self, tmp_path):
        src = tmp_path / "src" / "codefreedom"
        for d in ["cli", "core", "sandbox", "tools"]:
            (src / d).mkdir(parents=True)
        (src / "__init__.py").touch()
        modules = _detect_modules(tmp_path)
        assert modules == ["cli", "core", "sandbox", "tools"]

    def test_ignores_underscore_dirs(self, tmp_path):
        src = tmp_path / "src" / "codefreedom"
        (src / "cli").mkdir(parents=True)
        (src / "_internal").mkdir(parents=True)
        modules = _detect_modules(tmp_path)
        assert modules == ["cli"]

    def test_no_src_dir(self, tmp_path):
        assert _detect_modules(tmp_path) == []


# ── cf git init ───────────────────────────────────────────────────────────


class TestGitInit:
    def test_creates_cf_yaml(self, git_repo, monkeypatch):
        monkeypatch.chdir(git_repo)
        args = type("Args", (), {"force": False})()
        result = run_init(args)
        assert result == 0
        assert (git_repo / ".cf.yaml").exists()
        content = (git_repo / ".cf.yaml").read_text(encoding="utf-8")
        assert "git:" in content

    def test_adds_git_block_to_existing(self, git_repo, monkeypatch):
        monkeypatch.chdir(git_repo)
        existing = "# existing config\ndocker:\n  image: test\n"
        (git_repo / ".cf.yaml").write_text(existing, encoding="utf-8")
        args = type("Args", (), {"force": False})()
        result = run_init(args)
        assert result == 0
        content = (git_repo / ".cf.yaml").read_text(encoding="utf-8")
        assert "git:" in content
        assert "docker:" in content

    def test_skips_when_git_block_exists(self, git_repo, monkeypatch):
        monkeypatch.chdir(git_repo)
        content = "git:\n  model: gpt-4o\n"
        (git_repo / ".cf.yaml").write_text(content, encoding="utf-8")
        args = type("Args", (), {"force": False})()
        result = run_init(args)
        assert result == 0
        assert (git_repo / ".cf.yaml").read_text(encoding="utf-8") == content

    def test_force_updates_git_block(self, git_repo, monkeypatch):
        monkeypatch.chdir(git_repo)
        (git_repo / ".cf.yaml").write_text("git:\n  model: old\n", encoding="utf-8")
        args = type("Args", (), {"force": True})()
        result = run_init(args)
        assert result == 0
        content = (git_repo / ".cf.yaml").read_text(encoding="utf-8")
        assert "old" not in content
        assert "git:" in content

    def test_not_git_repo(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "codefreedom.cli.git.init_cmd.get_git_root",
            lambda _=None: None,
        )
        args = type("Args", (), {"force": False})()
        result = run_init(args)
        assert result == 1
