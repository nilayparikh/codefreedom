"""Tests for ``codebase_memory.project_id``."""
from __future__ import annotations

import pytest

from codebase_memory import project_id


class TestSanitizeBasename:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("/home/user/proj-A", "proj-a"),
            ("/home/u/client.name", "client-name"),
            ("/srv/v2.api", "v2-api"),
            ("/some/path/My_Project", "my-project"),
            ("/path/with spaces", "with-spaces"),
            ("/path/with--dashes", "with-dashes"),
            ("/path/-leading-dash", "leading-dash"),
            ("/path/trailing-dash-", "trailing-dash"),
            ("/", "root"),
            ("", "root"),
        ],
    )
    def test_sanitization(self, raw, expected):
        assert project_id.sanitize_basename(raw) == expected


class TestContainerNameFor:
    def test_base_name(self):
        used: set[str] = set()
        assert project_id.container_name_for("proj-a", used) == "codefreedom-tools-codebase-memory-proj-a"
        assert "codefreedom-tools-codebase-memory-proj-a" in used

    def test_collision_appends_suffix(self):
        used = {"codefreedom-tools-codebase-memory-proj-a"}
        assert project_id.container_name_for("proj-a", used) == "codefreedom-tools-codebase-memory-proj-a-1"
        assert "codefreedom-tools-codebase-memory-proj-a-1" in used

    def test_multiple_collisions(self):
        used = {
            "codefreedom-tools-codebase-memory-proj-a",
            "codefreedom-tools-codebase-memory-proj-a-1",
        }
        assert project_id.container_name_for("proj-a", used) == "codefreedom-tools-codebase-memory-proj-a-2"

    def test_unique_ids_dont_collide(self):
        used = {"codefreedom-tools-codebase-memory-proj-a"}
        assert project_id.container_name_for("proj-b", used) == "codefreedom-tools-codebase-memory-proj-b"

    def test_no_used_set_works(self):
        assert project_id.container_name_for("proj-a") == "codefreedom-tools-codebase-memory-proj-a"


class TestContainerSubpathFor:
    def test_simple(self):
        used: set[str] = set()
        assert project_id.container_subpath_for("/path/to/repo", used) == "/workspace/repo"

    def test_collision(self):
        used = {"/workspace/repo"}
        assert project_id.container_subpath_for("/other/path/repo", used) == "/workspace/repo-1"

    def test_basename_root(self, monkeypatch):
        used: set[str] = set()
        # Trailing-slash roots have basename "" which becomes "root".
        from pathlib import Path
        monkeypatch.setattr(Path, "name", "")
        assert project_id.container_subpath_for("/", used) == "/workspace/root"
