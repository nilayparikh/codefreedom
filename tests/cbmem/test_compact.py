"""Tests for ``codebase_memory.compact`` — VACUUM the cache, optional artifact."""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from codebase_memory import compact, manifest


def _make_populated_db(path: Path, with_deleted_rows: bool = True) -> int:
    """Create a SQLite DB with a table; optionally delete rows to give VACUUM work to do.

    Returns the file size after setup.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE t (a INTEGER, b TEXT)")
        # Insert 100 rows of garbage, then delete most of them to bloat.
        for i in range(100):
            conn.execute("INSERT INTO t VALUES (?, ?)", (i, "x" * 200))
        conn.commit()
        if with_deleted_rows:
            conn.execute("DELETE FROM t WHERE a < 95")
            conn.commit()
    finally:
        conn.close()
    return path.stat().st_size


def _require_sqlite3() -> bool:
    return shutil.which("sqlite3") is not None


def _require_zstd() -> bool:
    return shutil.which("zstd") is not None


pytestmark = pytest.mark.skipif(
    not shutil.which("sqlite3"), reason="sqlite3 CLI not on $PATH"
)


class TestVacuumInto:

    def test_compacts_a_real_db(self, tmp_path):
        db = tmp_path / "data.db"
        before = _make_populated_db(db, with_deleted_rows=True)
        result = compact._vacuum_into(db)
        assert result.ok is True
        assert result.error == ""
        assert result.after_bytes <= before
        # The DB is still readable and the table survives.
        conn = sqlite3.connect(str(db))
        try:
            rows = conn.execute("SELECT count(*) FROM t").fetchone()[0]
            assert rows == 5  # the 5 rows we didn't delete
        finally:
            conn.close()

    def test_db_size_unchanged_when_no_deleted_rows(self, tmp_path):
        db = tmp_path / "data.db"
        before = _make_populated_db(db, with_deleted_rows=False)
        result = compact._vacuum_into(db)
        assert result.ok is True
        # No deleted rows; size is roughly the same (maybe a little smaller).
        assert abs(result.after_bytes - before) < before * 0.1

    def test_returns_failure_when_sqlite3_missing(self, tmp_path, monkeypatch):
        db = tmp_path / "data.db"
        db.write_text("not a real db")
        monkeypatch.setattr(shutil, "which", lambda x: None if x == "sqlite3" else shutil.which(x))
        result = compact._vacuum_into(db)
        assert result.ok is False
        assert "sqlite3" in result.error

    def test_drops_wal_and_shm_sidecars(self, tmp_path):
        db = tmp_path / "data.db"
        _make_populated_db(db, with_deleted_rows=False)
        # Force a WAL file by writing outside a transaction and then checkpointing.
        conn = sqlite3.connect(str(db))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("INSERT INTO t VALUES (1, 'x')")
        del conn
        wal = db.with_suffix(".db-wal")
        shm = db.with_suffix(".db-shm")
        if not wal.exists():
            # Some FS configs don't actually create a WAL — skip.
            pytest.skip("WAL not present; skipping")
        assert wal.exists()
        compact._vacuum_into(db)
        assert not wal.exists()
        assert not shm.exists()

    def test_atomic_swap(self, tmp_path):
        db = tmp_path / "data.db"
        _make_populated_db(db, with_deleted_rows=True)
        result = compact._vacuum_into(db)
        assert result.ok is True
        # The .compact sidecar should be gone after swap.
        assert not db.with_suffix(".db.compact").exists()


class TestCompact:
    def test_noop_on_missing_cache(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        summary = compact.compact(tmp_path, write_artifact=False)
        assert summary.results == []
        assert not summary.container_was_running

    def test_stops_container_first(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        repo = tmp_path / "proj"
        repo.mkdir()
        manifest.save(repo, {"id": "x", "container_name": "cbm-x"})
        data = manifest.load(repo)
        # Create the cache dir and put a DB in it.
        cache = compact._resolve_cache_dir(data)
        cache.mkdir(parents=True, exist_ok=True)
        db = cache / "x.db"
        _make_populated_db(db, with_deleted_rows=False)

        with patch.object(compact.manager, "container_exists", return_value=True), \
             patch.object(compact.manager, "_is_container_running", return_value=True), \
             patch.object(compact.manager, "_docker_stop") as mock_stop:
            summary = compact.compact(repo)
        assert summary.container_was_running is True
        mock_stop.assert_called_once()
        assert any(r.db_path == db and r.ok for r in summary.results)

    def test_no_stop_when_container_not_running(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        repo = tmp_path / "proj"
        repo.mkdir()
        manifest.save(repo, {"id": "x"})
        data = manifest.load(repo)
        cache = compact._resolve_cache_dir(data)
        cache.mkdir(parents=True, exist_ok=True)
        _make_populated_db(cache / "x.db", with_deleted_rows=False)

        with patch.object(compact.manager, "container_exists", return_value=False), \
             patch.object(compact.manager, "_docker_stop") as mock_stop:
            summary = compact.compact(repo)
        assert summary.container_was_running is False
        mock_stop.assert_not_called()


class TestArtifact:
    def test_artifact_disabled_means_no_artifact(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        repo = tmp_path / "proj"
        repo.mkdir()
        manifest.save(repo, {"id": "x"})
        cache = compact._resolve_cache_dir({"id": "x"})
        cache.mkdir(parents=True, exist_ok=True)
        _make_populated_db(cache / "x.db", with_deleted_rows=False)
        summary = compact.compact(repo, write_artifact=False)
        assert summary.artifact_path is None

    @pytest.mark.skipif(not _require_zstd(), reason="zstd not on $PATH")
    def test_artifact_written_when_requested(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        repo = tmp_path / "proj"
        repo.mkdir()
        manifest.save(repo, {"id": "x"})
        cache = compact._resolve_cache_dir({"id": "x"})
        cache.mkdir(parents=True, exist_ok=True)
        _make_populated_db(cache / "x.db", with_deleted_rows=True)

        summary = compact.compact(repo, write_artifact=True)
        assert summary.artifact_path is not None
        assert summary.artifact_path.is_file()
        assert summary.artifact_path.suffix == ".zst"
        assert summary.artifact_bytes > 0

    def test_artifact_no_dbs(self, tmp_path, monkeypatch):
        """With no DBs in the cache, no artifact is written."""
        monkeypatch.setenv("HOME", str(tmp_path))
        repo = tmp_path / "proj"
        repo.mkdir()
        manifest.save(repo, {"id": "x"})
        summary = compact.compact(repo, write_artifact=True)
        assert summary.artifact_path is None
