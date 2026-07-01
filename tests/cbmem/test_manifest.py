"""Tests for ``codebase_memory.manifest``.

The manifest is the source of truth: a user-editable YAML file at
``<project_root>/.codefreedom/codebase-memory.yaml``. The loader is
permissive: missing fields get defaults, unknown fields are preserved.
"""
from __future__ import annotations

import datetime as _dt


from codebase_memory import manifest


class TestManifestPath:
    def test_path(self, tmp_path):
        assert manifest.manifest_path(tmp_path) == tmp_path / ".codefreedom" / "codebase-memory.yaml"

    def test_exists_false_for_missing(self, tmp_path):
        assert manifest.exists(tmp_path) is False

    def test_exists_true_for_present(self, tmp_path):
        manifest.save(tmp_path, {"id": "test"})
        assert manifest.exists(tmp_path) is True


class TestInitDefaults:
    def test_uses_sanitized_basename(self, tmp_path):
        project = tmp_path / "My-Cool_Project"
        project.mkdir()
        data = manifest.init_defaults(project)
        assert data["id"] == "my-cool-project"
        assert data["image"] == manifest.DEFAULTS["image"]
        assert data["memory_mb"] == 1024
        assert data["auto_open_ui"] is True

    def test_timestamps(self, tmp_path):
        project = tmp_path / "p"
        project.mkdir()
        data = manifest.init_defaults(project)
        # parseable as ISO 8601
        _dt.datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        _dt.datetime.fromisoformat(data["last_used_at"].replace("Z", "+00:00"))

    def test_contains_all_default_keys(self, tmp_path):
        project = tmp_path / "p"
        project.mkdir()
        data = manifest.init_defaults(project)
        for key in manifest.DEFAULTS:
            assert key in data


class TestLoad:
    def test_load_missing_returns_defaults(self, tmp_path):
        project = tmp_path / "p"
        project.mkdir()
        data = manifest.load(project)
        # id is derived from basename
        assert data["id"] == "p"

    def test_load_preserves_unknown_fields(self, tmp_path):
        project = tmp_path / "p"
        project.mkdir()
        manifest.save(project, {"id": "p", "my_custom_field": {"nested": 42}})
        data = manifest.load(project)
        assert data["my_custom_field"] == {"nested": 42}

    def test_load_fills_missing_with_defaults(self, tmp_path):
        project = tmp_path / "p"
        project.mkdir()
        manifest.save(project, {"id": "p", "memory_mb": 4096})
        data = manifest.load(project)
        # Custom value preserved
        assert data["memory_mb"] == 4096
        # Defaults filled in
        assert data["auto_open_ui"] is True
        assert data["shm_size_mb"] == 512

    def test_load_does_not_overwrite_id_with_basename(self, tmp_path):
        """The id in the YAML is what counts; we only re-derive if missing."""
        project = tmp_path / "p"
        project.mkdir()
        manifest.save(project, {"id": "custom-id"})
        data = manifest.load(project)
        assert data["id"] == "custom-id"

    def test_load_corrupt_file_returns_defaults(self, tmp_path):
        project = tmp_path / "p"
        project.mkdir()
        path = manifest.manifest_path(project)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not: valid: yaml: [")
        data = manifest.load(project)
        # Falls back to defaults; corrupt file is replaced on next save.
        assert isinstance(data, dict)
        assert "memory_mb" in data


class TestSave:
    def test_creates_parent_dirs(self, tmp_path):
        project = tmp_path / "deep" / "nested" / "p"
        project.mkdir(parents=True)
        manifest.save(project, {"id": "p"})
        assert manifest.manifest_path(project).is_file()

    def test_round_trip(self, tmp_path):
        project = tmp_path / "p"
        project.mkdir()
        manifest.save(project, {"id": "p", "mcp_port": 9753, "ui_port": 9753 + 1419})
        data = manifest.load(project)
        assert data["mcp_port"] == 9753
        assert data["ui_port"] == 9753 + 1419

    def test_save_preserves_user_fields_on_partial_update(self, tmp_path):
        project = tmp_path / "p"
        project.mkdir()
        manifest.save(project, {"id": "p", "my_notes": "hello", "mcp_port": 8330})
        # Partial update: only last_used_at changes.
        manifest.save(project, {"last_used_at": "2026-01-01T00:00:00Z"})
        data = manifest.load(project)
        assert data["my_notes"] == "hello"
        assert data["mcp_port"] == 8330
        assert data["last_used_at"] == "2026-01-01T00:00:00Z"

    def test_save_appends_gitignore(self, tmp_path):
        project = tmp_path / "p"
        project.mkdir()
        manifest.save(project, {"id": "p"})
        gi = project / ".gitignore"
        assert gi.is_file()
        content = gi.read_text()
        assert ".codefreedom/" in content

    def test_save_does_not_duplicate_gitignore_entry(self, tmp_path):
        project = tmp_path / "p"
        project.mkdir()
        gi = project / ".gitignore"
        gi.write_text("node_modules\n.codefreedom/\nbuild/\n")
        manifest.save(project, {"id": "p"})
        content = gi.read_text()
        # Only one ".codefreedom/" line.
        assert content.count(".codefreedom/") == 1

    def test_save_creates_gitignore_if_missing(self, tmp_path):
        project = tmp_path / "p"
        project.mkdir()
        assert not (project / ".gitignore").exists()
        manifest.save(project, {"id": "p"})
        assert (project / ".gitignore").is_file()

    def test_save_respects_existing_gitignore_content(self, tmp_path):
        project = tmp_path / "p"
        project.mkdir()
        gi = project / ".gitignore"
        gi.write_text("node_modules\n")  # no trailing newline
        manifest.save(project, {"id": "p"})
        content = gi.read_text()
        # Should not corrupt the existing entry; ".codefreedom/" appended on its own line.
        assert content.startswith("node_modules\n")
        assert ".codefreedom/" in content

    def test_save_recognizes_gitignore_entry_without_trailing_slash(self, tmp_path):
        project = tmp_path / "p"
        project.mkdir()
        gi = project / ".gitignore"
        gi.write_text(".codefreedom\n")
        manifest.save(project, {"id": "p"})
        # Already there; no duplicate.
        assert gi.read_text().count(".codefreedom") == 1


class TestUpdateLastUsed:
    def test_updates_timestamp(self, tmp_path):
        project = tmp_path / "p"
        project.mkdir()
        manifest.save(project, {"id": "p"})
        before = manifest.load(project)["last_used_at"]
        manifest.update_last_used(project)
        after = manifest.load(project)["last_used_at"]
        assert after >= before

    def test_noop_when_no_manifest(self, tmp_path):
        # Should not raise.
        manifest.update_last_used(tmp_path)
