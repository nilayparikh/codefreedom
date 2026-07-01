"""Cache compaction: VACUUM the per-project cache, optionally write artifact.

The user invokes ``cf r tl cbmem compact`` when they want to reclaim
space in a project's cache. The command:

1. Stops the project's container if it's running (SQLite locks the DB
   otherwise).
2. For each ``<project>.db`` in the cache directory, runs
   ``sqlite3 <db> 'VACUUM INTO <db>.compact'`` and atomic-swaps the
   file. WAL/SHM sidecars are dropped — SQLite re-creates them on
   next open.
3. Reports size before / after for each DB.
4. Does not auto-restart the container — the user runs ``start`` when
   they want it back.

With ``--artifact``, also writes the upstream's
``.codebase-memory/graph.db.zst`` team-shared artifact next to the
project root. The artifact is created by ``VACUUM INTO`` followed by
zstd compression, matching the upstream's recipe.
"""
from __future__ import annotations

import contextlib
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from codebase_memory import manager, manifest


_log = logging.getLogger(__name__)


@dataclass
class CompactResult:
    db_path: Path
    before_bytes: int
    after_bytes: int
    ok: bool
    error: str = ""


@dataclass
class CompactSummary:
    results: list[CompactResult]
    cache_dir: Path
    container_was_running: bool
    artifact_path: Path | None = None
    artifact_bytes: int = 0


def compact(
    project_root: Path,
    *,
    write_artifact: bool = False,
    zstd_level: int = 9,
) -> CompactSummary:
    """Run ``VACUUM`` on every ``.db`` file in the project's cache.

    Stops the container first. Reports per-file size deltas. If
    ``write_artifact`` is True, also writes
    ``<project_root>/.codebase-memory/graph.db.zst``.
    """
    data = manifest.load(project_root)
    cache_dir = _resolve_cache_dir(data)

    container_name = str(data.get("container_name", "") or "")
    container_was_running = False
    if container_name and manager.container_exists(container_name) and manager._is_container_running(container_name):
        container_was_running = True
        _log.info("stopping container %s for VACUUM", container_name)
        manager._docker_stop(container_name)

    results: list[CompactResult] = []
    if cache_dir.is_dir():
        for db in sorted(cache_dir.glob("*.db")):
            results.append(_vacuum_into(db))

    artifact_path: Path | None = None
    artifact_bytes = 0
    if write_artifact:
        artifact_path, artifact_bytes = _write_artifact(project_root, cache_dir, zstd_level)

    return CompactSummary(
        results=results,
        cache_dir=cache_dir,
        container_was_running=container_was_running,
        artifact_path=artifact_path,
        artifact_bytes=artifact_bytes,
    )


def _vacuum_into(db: Path) -> CompactResult:
    """VACUUM INTO ``db.tmp`` then atomically swap. Captures size delta."""
    if not db.is_file():
        return CompactResult(db_path=db, before_bytes=0, after_bytes=0, ok=True)

    before = db.stat().st_size
    tmp = db.with_suffix(db.suffix + ".compact")
    if tmp.exists():
        tmp.unlink()

    sqlite = shutil.which("sqlite3")
    if sqlite is None:
        return CompactResult(
            db_path=db,
            before_bytes=before,
            after_bytes=before,
            ok=False,
            error="sqlite3 CLI not found on $PATH",
        )

    proc = subprocess.run(
        [sqlite, str(db), f"VACUUM INTO '{tmp.as_posix()}'"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        return CompactResult(
            db_path=db,
            before_bytes=before,
            after_bytes=before,
            ok=False,
            error=(proc.stderr or proc.stdout or "VACUUM failed").strip(),
        )

    # Drop WAL/SHM sidecars — SQLite re-creates on next open.
    for sidecar in (db.with_suffix(db.suffix + "-wal"), db.with_suffix(db.suffix + "-shm")):
        with contextlib.suppress(FileNotFoundError):
            sidecar.unlink()

    tmp.replace(db)
    after = db.stat().st_size
    return CompactResult(db_path=db, before_bytes=before, after_bytes=after, ok=True)


def _write_artifact(project_root: Path, cache_dir: Path, zstd_level: int) -> tuple[Path | None, int]:
    """Write the upstream's ``graph.db.zst`` team-shared artifact."""
    if not cache_dir.is_dir():
        return None, 0

    dbs = sorted(cache_dir.glob("*.db"))
    if not dbs:
        return None, 0

    # If there are multiple DBs (related projects), pick the largest —
    # the user can rename it if they want a different one.
    primary = max(dbs, key=lambda p: p.stat().st_size)

    artifact_dir = project_root / ".codebase-memory"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    raw_path = artifact_dir / "graph.db"
    if raw_path.exists():
        raw_path.unlink()

    sqlite = shutil.which("sqlite3")
    if sqlite is None:
        return None, 0
    proc = subprocess.run(
        [sqlite, str(primary), f"VACUUM INTO '{raw_path.as_posix()}'"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not raw_path.is_file():
        return None, 0

    zstd = shutil.which("zstd")
    artifact_path = artifact_dir / "graph.db.zst"
    if zstd is None:
        # No zstd: keep the uncompressed file.
        return raw_path, raw_path.stat().st_size

    subprocess.run(
        [zstd, f"-{zstd_level}", "-q", "-f", "-o", str(artifact_path), str(raw_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    with contextlib.suppress(FileNotFoundError):
        raw_path.unlink()
    if not artifact_path.is_file():
        return None, 0
    return artifact_path, artifact_path.stat().st_size


def _resolve_cache_dir(data: dict) -> Path:
    """Mirror ``manager._cache_dir`` so tests can stub it."""
    import os
    from pathlib import Path as _P

    home = _P(os.environ.get("HOME") or str(_P.home()))
    return home / ".codefreedom" / "cache" / "codebase-memory" / str(data["id"])


# Re-exports for tests
del Iterable  # silence unused
