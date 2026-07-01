"""Tests for ``codebase_memory.manager`` — port allocation, mount
construction, label encoding, and reconcile+start orchestration.

The manager is the heart of the package. These tests focus on the pure
parts (port allocation, label building, manifest hashing) and stub the
docker subprocess calls so we can verify the orchestration logic
without actually launching containers.
"""
from __future__ import annotations

import socket
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from codebase_memory import manager, manifest


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


# ── Port allocation ─────────────────────────────────────────────────────


class TestIsFree:
    def test_free_port_is_free(self):
        # Pick a random unused high port.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        assert manager._is_free("127.0.0.1", port) is True

    def test_bound_port_is_not_free(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
        server.listen(1)
        try:
            assert manager._is_free("127.0.0.1", port) is False
        finally:
            server.close()


class TestUiPairFor:
    def test_default_offset(self):
        assert manager._ui_pair_for(8330) == 9749

    def test_offsets_propagate(self):
        assert manager._ui_pair_for(8331) == 9750
        assert manager._ui_pair_for(8500) == 9919


class TestEnsurePorts:
    def test_uses_manifest_ports_when_free(self, tmp_path, monkeypatch):
        # Mark 8330 and 9749 as "in use" by binding them.
        for p in (8330, 9749):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.bind(("127.0.0.1", p))
                s.listen(1)
                monkeypatch.setattr(manager, "_is_free", lambda h, port, _s=s: port not in (8330, 9749) and True)
                s.close()  # actually let it go
            except OSError:
                pass

        # Even simpler: monkey-patch _is_free to a free-port list.
        monkeypatch.setattr(manager, "_is_free", lambda h, port: port in (8330, 9749))
        data = {"mcp_port": 8330, "ui_port": 9749}
        manager._ensure_ports(tmp_path, data)
        assert data["mcp_port"] == 8330
        assert data["ui_port"] == 9749

    def test_advances_when_taken(self, tmp_path, monkeypatch):
        # Claim 8330, free 8331.
        free_ports = {8331, 9750}

        def fake_free(h, port):
            return port in free_ports

        monkeypatch.setattr(manager, "_is_free", fake_free)
        data = {"mcp_port": 8330, "ui_port": 9749}
        manager._ensure_ports(tmp_path, data)
        assert data["mcp_port"] == 8331
        assert data["ui_port"] == 9750

    def test_persists_new_ports(self, tmp_path, monkeypatch):
        free_ports = {8342, 9761}

        def fake_free(h, port):
            return port in free_ports

        monkeypatch.setattr(manager, "_is_free", fake_free)
        manager.populate_manifest_for_init(_make_repo(tmp_path / "proj"))
        # Manifest now has a container_name. We test _ensure_ports on a
        # data dict directly.
        data = manifest.load(tmp_path / "proj")
        manager._ensure_ports(tmp_path / "proj", data)
        # Persisted?
        reloaded = manifest.load(tmp_path / "proj")
        assert reloaded["mcp_port"] == 8342
        assert reloaded["ui_port"] == 9761

    def test_raises_when_no_free_pair(self, tmp_path, monkeypatch):
        monkeypatch.setattr(manager, "_is_free", lambda h, port: False)
        with pytest.raises(RuntimeError, match="No free MCP port pair"):
            manager._ensure_ports(tmp_path, {"mcp_port": 8330, "ui_port": 9749})


# ── Hash + labels ──────────────────────────────────────────────────────


class TestManifestHash:
    def test_deterministic(self):
        data = {"id": "x", "memory_mb": 1024, "related_paths": []}
        h1 = manager.manifest_hash(data)
        h2 = manager.manifest_hash(data)
        assert h1 == h2

    def test_changes_with_related_paths(self):
        d1 = {"id": "x", "related_paths": []}
        d2 = {"id": "x", "related_paths": [{"path": "/a", "alias": "a"}]}
        assert manager.manifest_hash(d1) != manager.manifest_hash(d2)

    def test_changes_with_memory_mb(self):
        d1 = {"id": "x", "memory_mb": 1024}
        d2 = {"id": "x", "memory_mb": 4096}
        assert manager.manifest_hash(d1) != manager.manifest_hash(d2)

    def test_ignores_unrelated_fields(self):
        # HASH_FIELDS doesn't include arbitrary unknown fields; they shouldn't affect hash.
        d1 = {"id": "x", "noise": 1}
        d2 = {"id": "x", "noise": 2}
        assert manager.manifest_hash(d1) == manager.manifest_hash(d2)

    def test_includes_image(self):
        d1 = {"id": "x", "image": "a:latest"}
        d2 = {"id": "x", "image": "b:latest"}
        assert manager.manifest_hash(d1) != manager.manifest_hash(d2)


class TestBuildLabels:
    def test_basic_labels(self):
        data = {
            "id": "proj-a",
            "memory_mb": 1024,
            "auto_open_ui": True,
            "related_paths": [],
        }
        labels = manager.build_labels(data)
        assert labels[f"{manager.LABEL_PREFIX}.id"] == "proj-a"
        assert labels[f"{manager.LABEL_PREFIX}.memory-mb"] == "1024"
        assert labels[f"{manager.LABEL_PREFIX}.auto-open-ui"] == "true"
        assert f"{manager.LABEL_PREFIX}.managed-by" in labels
        assert f"{manager.LABEL_PREFIX}.manifest-hash" in labels

    def test_related_paths_in_label(self):
        data = {
            "id": "x",
            "related_paths": [
                {"path": "/a/lib"},
                {"path": "/b/sibling"},
            ],
        }
        labels = manager.build_labels(data)
        paths = labels[f"{manager.LABEL_PREFIX}.related-paths"]
        assert paths == "/a/lib,/b/sibling"

    def test_auto_open_ui_false(self):
        data = {"id": "x", "auto_open_ui": False, "related_paths": []}
        labels = manager.build_labels(data)
        assert labels[f"{manager.LABEL_PREFIX}.auto-open-ui"] == "false"


# ── Build run args ─────────────────────────────────────────────────────


class TestBuildRunArgs:
    def test_basic_run_args(self, tmp_path, monkeypatch):
        # Pin HOME so _cache_dir returns a stable path inside tmp_path.
        monkeypatch.setenv("HOME", str(tmp_path))
        repo = _make_repo(tmp_path / "proj")
        manifest.save(repo, {"id": "proj"})
        data = manifest.load(repo)
        data["path"] = str(repo.resolve())
        data["container_name"] = "codefreedom-tools-codebase-memory-proj"
        data["mcp_port"] = 8330
        data["ui_port"] = 9749
        data["memory_mb"] = 1024
        data["shm_size_mb"] = 512
        args = manager._build_run_args(data)
        # The image is the last positional arg.
        assert args[-1] == data["image"]
        # 2 -v flags: 1 for /cache + 1 for the main project.
        v_count = sum(1 for a in args if a == "-v")
        assert v_count == 2
        # Find the main-project mount: it ends in /workspace/proj:ro.
        main_mount = next(
            v for v in (args[args.index("-v", i) + 1] for i, a in enumerate(args) if a == "-v")
            if v.endswith("/workspace/proj:ro")
        )
        assert main_mount == f"{repo.resolve()}:/workspace/proj:ro"

    def test_includes_related_paths(self, tmp_path):
        repo = _make_repo(tmp_path / "proj")
        extra = _make_repo(tmp_path / "extra")
        manifest.save(repo, {"id": "proj"})
        data = manifest.load(repo)
        data["path"] = str(repo.resolve())
        data["container_name"] = "codefreedom-tools-codebase-memory-proj"
        data["mcp_port"] = 8330
        data["ui_port"] = 9749
        data["related_paths"] = [{"path": str(extra.resolve()), "alias": "shared"}]
        args = manager._build_run_args(data)
        v_indices = [i for i, a in enumerate(args) if a == "-v"]
        # 1 for /cache, 1 for main, 1 for related.
        assert len(v_indices) == 3
        # Related path is mounted at /workspace/extra:ro.
        related_mounts = [args[i + 1] for i in v_indices]
        assert any(":ro" in m and "/workspace/extra" in m for m in related_mounts)

    def test_includes_extra_env(self, tmp_path):
        repo = _make_repo(tmp_path / "proj")
        manifest.save(repo, {"id": "proj"})
        data = manifest.load(repo)
        data["path"] = str(repo.resolve())
        data["container_name"] = "x"
        data["mcp_port"] = 8330
        data["ui_port"] = 9749
        data["env"] = {"CBM_LOG_LEVEL": "debug", "MY_TOKEN": "abc"}
        args = manager._build_run_args(data)
        # Two extra -e flags added.
        env_indices = [i for i, a in enumerate(args) if a == "-e"]
        env_values = {args[i + 1] for i in env_indices}
        assert "CBM_LOG_LEVEL=debug" in env_values
        assert "MY_TOKEN=abc" in env_values

    def test_publishes_both_ports(self, tmp_path):
        repo = _make_repo(tmp_path / "proj")
        manifest.save(repo, {"id": "proj"})
        data = manifest.load(repo)
        data["path"] = str(repo.resolve())
        data["container_name"] = "x"
        data["mcp_port"] = 8400
        data["ui_port"] = 9819
        args = manager._build_run_args(data)
        p_indices = [i for i, a in enumerate(args) if a == "-p"]
        p_values = {args[i + 1] for i in p_indices}
        assert "127.0.0.1:8400:8330" in p_values
        assert "127.0.0.1:9819:9749" in p_values


# ── ensure_running (orchestration) ─────────────────────────────────────


class TestEnsureRunning:

    def test_remote_url_short_circuits(self, tmp_path):
        repo = _make_repo(tmp_path / "proj")
        manifest.save(repo, {"id": "proj", "remote_url": "https://x/mcp"})
        data = manifest.load(repo)
        data["path"] = str(repo.resolve())
        data["container_name"] = "x"
        manifest.save(repo, data)
        # No docker calls expected.
        with patch.object(manager, "_docker_run") as mock_run:
            status, payload = manager.ensure_running(repo)
        assert status == manager.StartStatus.ALREADY_RUNNING
        assert payload["remote_url"] == "https://x/mcp"
        mock_run.assert_not_called()

    def test_auto_start_false_short_circuits(self, tmp_path):
        repo = _make_repo(tmp_path / "proj")
        manifest.save(repo, {"id": "proj", "auto_start": False})
        data = manifest.load(repo)
        data["path"] = str(repo.resolve())
        data["container_name"] = "x"
        manifest.save(repo, data)
        with patch.object(manager, "_docker_run") as mock_run:
            status, payload = manager.ensure_running(repo)
        assert status == manager.StartStatus.ALREADY_RUNNING
        mock_run.assert_not_called()

    def test_no_container_creates(self, tmp_path):
        repo = _make_repo(tmp_path / "proj")
        manifest.save(repo, {"id": "proj"})
        data = manifest.load(repo)
        data["path"] = str(repo.resolve())
        data["container_name"] = "x"
        manifest.save(repo, data)

        with patch.object(manager, "container_exists", return_value=False), \
             patch.object(manager, "_docker_run") as mock_run, \
             patch.object(manager, "_auto_index_workspace"):
            mock_run.return_value = subprocess.CompletedProcess(
                args=(), returncode=0, stdout="abc123", stderr=""
            )
            status, _ = manager.ensure_running(repo)
        assert status == manager.StartStatus.CREATED
        mock_run.assert_called_once()

    def test_manifest_changed_restarts(self, tmp_path):
        repo = _make_repo(tmp_path / "proj")
        manifest.save(repo, {"id": "proj"})
        data = manifest.load(repo)
        data["path"] = str(repo.resolve())
        data["container_name"] = "x"
        data["mcp_port"] = 8330
        data["ui_port"] = 9749
        manifest.save(repo, data)

        # Container exists, running, but its label hash differs.
        actual_hash = "deadbeef00000000"  # not equal to the computed hash
        with patch.object(manager, "container_exists", return_value=True), \
             patch.object(manager, "_is_container_running", return_value=True), \
             patch.object(manager, "container_label", return_value=actual_hash), \
             patch.object(manager, "_docker_stop") as mock_stop, \
             patch.object(manager, "_docker_rm") as mock_rm, \
             patch.object(manager, "_docker_run") as mock_run, \
             patch.object(manager, "_auto_index_workspace"):
            mock_run.return_value = subprocess.CompletedProcess(
                args=(), returncode=0, stdout="", stderr=""
            )
            status, _ = manager.ensure_running(repo)
        assert status == manager.StartStatus.RESTARTED
        mock_stop.assert_called_once()
        mock_rm.assert_called_once()

    def test_unchanged_running_returns_noop(self, tmp_path, monkeypatch):
        # Make port allocation deterministic.
        monkeypatch.setattr(manager, "_is_free", lambda h, port: port in (8330, 9749))
        repo = _make_repo(tmp_path / "proj")
        manifest.save(repo, {"id": "proj"})
        data = manifest.load(repo)
        data["path"] = str(repo.resolve())
        data["container_name"] = "x"
        data["mcp_port"] = 8330
        data["ui_port"] = 9749
        manifest.save(repo, data)
        with patch.object(manager, "container_exists", return_value=True), \
             patch.object(manager, "_is_container_running", return_value=True), \
             patch.object(manager, "container_label") as mock_label, \
             patch.object(manager, "_docker_run") as mock_run:
            mock_label.return_value = manager.manifest_hash(data)
            status, _ = manager.ensure_running(repo)
        assert status == manager.StartStatus.ALREADY_RUNNING
        mock_run.assert_not_called()

    def test_stopped_container_starts(self, tmp_path, monkeypatch):
        monkeypatch.setattr(manager, "_is_free", lambda h, port: port in (8330, 9749))
        repo = _make_repo(tmp_path / "proj")
        manifest.save(repo, {"id": "proj"})
        data = manifest.load(repo)
        data["path"] = str(repo.resolve())
        data["container_name"] = "x"
        data["mcp_port"] = 8330
        data["ui_port"] = 9749
        manifest.save(repo, data)
        with patch.object(manager, "container_exists", return_value=True), \
             patch.object(manager, "_is_container_running", return_value=False), \
             patch.object(manager, "container_label") as mock_label, \
             patch.object(manager, "_docker_start") as mock_start:
            mock_label.return_value = manager.manifest_hash(data)
            status, _ = manager.ensure_running(repo)
        assert status == manager.StartStatus.RESTARTED
        mock_start.assert_called_once()

    def test_create_failure_returns_failed(self, tmp_path):
        repo = _make_repo(tmp_path / "proj")
        manifest.save(repo, {"id": "proj"})
        data = manifest.load(repo)
        data["path"] = str(repo.resolve())
        data["container_name"] = "x"
        manifest.save(repo, data)
        with patch.object(manager, "container_exists", return_value=False), \
             patch.object(manager, "_docker_run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=(), returncode=125, stdout="", stderr="boom"
            )
            status, _ = manager.ensure_running(repo)
        assert status == manager.StartStatus.FAILED

    def test_create_auto_indexes_main_and_related_paths(self, tmp_path):
        repo = _make_repo(tmp_path / "proj")
        extra = _make_repo(tmp_path / "extra")
        shared = _make_repo(tmp_path / "shared")
        manifest.save(
            repo,
            {
                "id": "proj",
                "related_paths": [
                    {"path": str(extra.resolve()), "alias": "extra"},
                    {"path": str(shared.resolve()), "alias": "shared"},
                ],
            },
        )
        data = manifest.load(repo)
        data["path"] = str(repo.resolve())
        data["container_name"] = "x"
        manifest.save(repo, data)

        with patch.object(manager, "container_exists", return_value=False), \
             patch.object(manager, "_docker_run") as mock_run, \
             patch.object(manager, "_auto_index_workspace") as mock_auto_index:
            mock_run.return_value = subprocess.CompletedProcess(
                args=(), returncode=0, stdout="abc123", stderr=""
            )
            status, _ = manager.ensure_running(repo)

        assert status == manager.StartStatus.CREATED
        mock_auto_index.assert_called_once()
        payload, repo_paths = mock_auto_index.call_args.args
        assert payload["mcp_port"] > 0
        assert repo_paths == ["/workspace/proj", "/workspace/extra", "/workspace/shared"]


# ── reset / cache dir helpers ─────────────────────────────────────────


class TestReset:
    def test_reset_full(self, tmp_path):
        repo = _make_repo(tmp_path / "proj")
        manifest.save(repo, {"id": "proj"})
        data = manifest.load(repo)
        data["path"] = str(repo.resolve())
        data["container_name"] = "x"
        manifest.save(repo, data)
        # Pre-create cache dir with a file.
        cache = manager._cache_dir(data)
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "test.db").write_text("x")
        assert manifest.manifest_path(repo).is_file()

        with patch.object(manager, "container_exists", return_value=False):
            manager.reset(repo)

        assert not manifest.manifest_path(repo).exists()
        assert not cache.exists()

    def test_reset_keep_manifest(self, tmp_path):
        repo = _make_repo(tmp_path / "proj")
        manifest.save(repo, {"id": "proj"})
        data = manifest.load(repo)
        data["path"] = str(repo.resolve())
        data["container_name"] = "x"
        manifest.save(repo, data)
        with patch.object(manager, "container_exists", return_value=False):
            manager.reset(repo, keep_manifest=True)
        assert manifest.manifest_path(repo).is_file()


class TestPopulateManifestForInit:
    def test_sets_path_and_container_name(self, tmp_path):
        repo = _make_repo(tmp_path / "My_Project")
        data = manager.populate_manifest_for_init(repo)
        assert data["id"] == "my-project"
        assert data["path"] == str(repo.resolve())
        assert data["container_name"] == "codefreedom-tools-codebase-memory-my-project"
