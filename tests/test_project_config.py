"""Unit tests for project_config — generic .cf.yaml management."""

from __future__ import annotations

import pytest

from codefreedom.cli.project_config import (
    find_cf_yaml,
    load_cf_yaml,
    save_cf_yaml,
    update_cf_yaml,
)

pytestmark = pytest.mark.unit


class TestLoadCfYaml:
    def test_missing_file(self, tmp_path):
        assert load_cf_yaml(tmp_path / ".cf.yaml") == {}

    def test_valid_yaml(self, tmp_path):
        path = tmp_path / ".cf.yaml"
        path.write_text("git:\n  model: gpt-4o\n", encoding="utf-8")
        result = load_cf_yaml(path)
        assert result["git"]["model"] == "gpt-4o"

    def test_invalid_yaml(self, tmp_path):
        path = tmp_path / ".cf.yaml"
        path.write_text("{{invalid", encoding="utf-8")
        assert load_cf_yaml(path) == {}


class TestSaveCfYaml:
    def test_creates_file(self, tmp_path):
        path = tmp_path / ".cf.yaml"
        save_cf_yaml(path, {"git": {"model": "gpt-4o"}})
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "git:" in content
        assert "model: gpt-4o" in content

    def test_preserves_multiple_blocks(self, tmp_path):
        path = tmp_path / ".cf.yaml"
        save_cf_yaml(path, {"git": {"model": "gpt-4o"}, "docker": {"image": "test"}})
        content = path.read_text(encoding="utf-8")
        assert "git:" in content
        assert "docker:" in content


class TestUpdateCfYaml:
    def test_creates_with_block(self, tmp_path):
        path = tmp_path / ".cf.yaml"
        result = update_cf_yaml(path, "git", {"model": "gpt-4o"})
        assert result == 0
        data = load_cf_yaml(path)
        assert data["git"]["model"] == "gpt-4o"

    def test_adds_block_to_existing(self, tmp_path):
        path = tmp_path / ".cf.yaml"
        save_cf_yaml(path, {"docker": {"image": "test"}})
        result = update_cf_yaml(path, "git", {"model": "gpt-4o"})
        assert result == 0
        data = load_cf_yaml(path)
        assert "git" in data
        assert "docker" in data

    def test_skips_when_block_exists(self, tmp_path):
        path = tmp_path / ".cf.yaml"
        save_cf_yaml(path, {"git": {"model": "gpt-4o"}})
        result = update_cf_yaml(path, "git", {"model": "gpt-4o-mini"})
        assert result == 2
        data = load_cf_yaml(path)
        assert data["git"]["model"] == "gpt-4o"

    def test_force_overwrites_block(self, tmp_path):
        path = tmp_path / ".cf.yaml"
        save_cf_yaml(path, {"git": {"model": "gpt-4o"}})
        result = update_cf_yaml(path, "git", {"model": "gpt-4o-mini"}, force=True)
        assert result == 0
        data = load_cf_yaml(path)
        assert data["git"]["model"] == "gpt-4o-mini"

    def test_preserves_other_blocks(self, tmp_path):
        path = tmp_path / ".cf.yaml"
        save_cf_yaml(path, {"docker": {"image": "test"}})
        update_cf_yaml(path, "git", {"model": "gpt-4o"})
        data = load_cf_yaml(path)
        assert "docker" in data
        assert "git" in data


class TestFindCfYaml:
    def test_finds_in_git_root(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "codefreedom.cli.project_config.get_git_root", lambda _p: tmp_path
        )
        (tmp_path / ".cf.yaml").write_text("git: {}", encoding="utf-8")
        result = find_cf_yaml(tmp_path)
        assert result is not None
        assert result.name == ".cf.yaml"

    def test_returns_none_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "codefreedom.cli.project_config.get_git_root", lambda _p: tmp_path
        )
        result = find_cf_yaml(tmp_path)
        assert result is None

    def test_returns_none_outside_repo(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "codefreedom.cli.project_config.get_git_root", lambda _p: None
        )
        result = find_cf_yaml(tmp_path)
        assert result is None
