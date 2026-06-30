"""Integration tests for cf git — config loading, git operations."""

from __future__ import annotations

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

pytestmark = pytest.mark.integration


# ── Config loading ────────────────────────────────────────────────────────


class TestLoadGlobalGitConfig:
    def test_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_config_dir",
            lambda: tmp_path,
        )
        result = load_global_git_config()
        assert result == {}

    def test_loads_yaml(self, tmp_path, monkeypatch):
        (tmp_path / "profiles.yaml").write_text(
            yaml.dump({"tools": {"git": {"model": "gpt-4o", "signed_commit": False}}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_config_dir",
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
        """Legacy ``git:`` block fills keys the new schema doesn't set.

        New ``tools.git`` schema is the canonical path — it wins on any
        key it covers. The legacy block is a fallback for keys the new
        schema doesn't touch.
        """
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_git_root",
            lambda _=None: tmp_path,
        )
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_config_dir",
            lambda: tmp_path,
        )
        (tmp_path / "profiles.yaml").write_text(
            yaml.dump({"tools": {"git": {"model": "gpt-4o", "signed_commit": True}}}),
            encoding="utf-8",
        )
        (tmp_path / ".cf.yaml").write_text(
            yaml.dump({"git": {"model": "gpt-4o-mini"}}),
            encoding="utf-8",
        )
        config = load_git_config(tmp_path)
        assert config["model"] == "gpt-4o"
        assert config["signed_commit"] is True


class TestLoadGitConfigNewSchema:
    """``tools.git`` from override.yaml and .cf.yaml (full override schema)."""

    def test_tools_git_in_override_wins(self, tmp_path, monkeypatch):
        """``tools.git`` in ``override.yaml`` overrides ``profiles.yaml``."""
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_git_root",
            lambda _=None: None,
        )
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_config_dir",
            lambda: tmp_path,
        )
        (tmp_path / "profiles.yaml").write_text(
            yaml.dump({"tools": {"git": {"model": "from_profiles"}}}),
            encoding="utf-8",
        )
        (tmp_path / "override.yaml").write_text(
            yaml.dump({"tools": {"git": {"model": "from_override"}}}),
            encoding="utf-8",
        )
        config = load_git_config(tmp_path)
        assert get_model(config) == "from_override"

    def test_tools_git_in_cf_yaml_wins(self, tmp_path, monkeypatch):
        """``tools.git`` in ``.cf.yaml`` (explicit ``CF_CLI_CF_YAML``) wins."""
        monkeypatch.setenv("CF_CLI_CF_YAML", str(tmp_path / ".cf.yaml"))
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_config_dir",
            lambda: tmp_path,
        )
        (tmp_path / "profiles.yaml").write_text(
            yaml.dump({"tools": {"git": {"model": "from_profiles"}}}),
            encoding="utf-8",
        )
        (tmp_path / ".cf.yaml").write_text(
            yaml.dump({"tools": {"git": {"model": "from_cf_yaml"}}}),
            encoding="utf-8",
        )
        config = load_git_config(tmp_path)
        assert get_model(config) == "from_cf_yaml"

    def test_full_layering_chain(self, tmp_path, monkeypatch):
        """End-to-end: defaults < profiles < override < .cf.yaml < CF_CLI_*.

        CF_CLI_* overrides win when the YAML uses ``${VAR}`` interpolation.
        Here ``.cf.yaml`` sets ``model: ${GIT_MODEL}`` and we set
        ``CF_CLI_GIT_MODEL`` to verify the env var wins.
        """
        monkeypatch.setenv("CF_CLI_CF_YAML", str(tmp_path / ".cf.yaml"))
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_config_dir",
            lambda: tmp_path,
        )
        (tmp_path / "profiles.yaml").write_text(
            yaml.dump({"tools": {"git": {
                "model": "from_profiles",
                "signed_commit": True,
                "conventional_commit": True,
            }}}),
            encoding="utf-8",
        )
        (tmp_path / "override.yaml").write_text(
            yaml.dump({"tools": {"git": {"signed_commit": False}}}),
            encoding="utf-8",
        )
        (tmp_path / ".cf.yaml").write_text(
            yaml.dump({"tools": {"git": {"model": "${GIT_MODEL}"}}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("CF_CLI_GIT_MODEL", "from_cf_cli")

        config = load_git_config(tmp_path)
        assert get_model(config) == "from_cf_cli"
        assert is_signed_commit(config) is False
        assert is_conventional_commit(config) is True

    def test_legacy_git_block_still_works(self, tmp_path, monkeypatch):
        """Legacy ``git:`` block in .cf.yaml fills keys the new schema doesn't.

        Backward compat: a user with an old config (legacy block only,
        no ``tools.git`` in profiles.yaml) gets the legacy value.
        """
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_git_root",
            lambda _=None: tmp_path,
        )
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_config_dir",
            lambda: tmp_path,
        )
        (tmp_path / "profiles.yaml").write_text(
            "agents: {}\n",
            encoding="utf-8",
        )
        (tmp_path / ".cf.yaml").write_text(
            yaml.dump({"git": {"model": "from_legacy_block"}}),
            encoding="utf-8",
        )
        config = load_git_config(tmp_path)
        assert get_model(config) == "from_legacy_block"

    def test_new_schema_beats_legacy_block(self, tmp_path, monkeypatch):
        """When both ``tools.git`` and ``git:`` block exist in .cf.yaml, new wins."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_git_root",
            lambda _=None: tmp_path,
        )
        monkeypatch.setenv("CF_CLI_CF_YAML", str(tmp_path / ".cf.yaml"))
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_config_dir",
            lambda: tmp_path,
        )
        (tmp_path / "profiles.yaml").write_text(
            yaml.dump({"tools": {"git": {"model": "from_profiles"}}}),
            encoding="utf-8",
        )
        (tmp_path / ".cf.yaml").write_text(yaml.dump({
            "git": {"model": "from_legacy_block"},
            "tools": {"git": {"model": "from_new_schema"}},
        }), encoding="utf-8")
        config = load_git_config(tmp_path)
        assert get_model(config) == "from_new_schema"

    def test_cf_yaml_path_env_var_overrides(self, tmp_path, monkeypatch):
        """``CF_CLI_CF_YAML`` env var beats git-root auto-discovery."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_git_root",
            lambda _=None: tmp_path,
        )
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_config_dir",
            lambda: tmp_path,
        )
        (tmp_path / "profiles.yaml").write_text(
            yaml.dump({"tools": {"git": {"model": "from_profiles"}}}),
            encoding="utf-8",
        )
        (tmp_path / ".cf.yaml").write_text(
            yaml.dump({"tools": {"git": {"model": "from_git_root"}}}),
            encoding="utf-8",
        )
        other = tmp_path / "other"
        other.mkdir()
        (other / "custom.yaml").write_text(
            yaml.dump({"tools": {"git": {"model": "from_env_var"}}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("CF_CLI_CF_YAML", str(other / "custom.yaml"))

        config = load_git_config(tmp_path)
        assert get_model(config) == "from_env_var"

    def test_no_cf_yaml_falls_back_to_profiles(self, tmp_path, monkeypatch):
        """Without .cf.yaml anywhere, the result is the profiles.yaml value."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_git_root",
            lambda _=None: None,
        )
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_config_dir",
            lambda: tmp_path,
        )
        (tmp_path / "profiles.yaml").write_text(
            yaml.dump({"tools": {"git": {"model": "from_profiles"}}}),
            encoding="utf-8",
        )
        config = load_git_config(tmp_path)
        assert get_model(config) == "from_profiles"

    def test_missing_global_profiles_uses_defaults(self, tmp_path, monkeypatch):
        """If everything is missing, fall back to hard-coded ``_DEFAULTS``."""
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_git_root",
            lambda _=None: None,
        )
        monkeypatch.setattr(
            "codefreedom.cli.git.config.get_config_dir",
            lambda: tmp_path,
        )
        config = load_git_config(tmp_path)
        assert get_model(config) == "gpt-4o-mini"
        assert is_conventional_commit(config) is True


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
