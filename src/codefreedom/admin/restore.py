"""Restore operation."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path
from typing import List, Optional, Tuple

from codefreedom.admin._utils import (
    _compute_diff,
    _read_archive_bytes,
    _read_manifest_from_archive,
    CURRENT_SCHEMA_VERSION,
    BackupManifest,
    FileDiff,
)
from codefreedom.core.config import get_codefreedom_dir


def restore(
    archive_path: Path,
    target_dir: Optional[Path] = None,
    dry_run: bool = False,
    passphrase: Optional[str] = None,
) -> Tuple[List[FileDiff], BackupManifest]:
    if not archive_path.exists():
        raise FileNotFoundError(f"Backup file not found: {archive_path}")

    if target_dir is None:
        target_dir = get_codefreedom_dir()

    manifest = _read_manifest_from_archive(archive_path, passphrase=passphrase)

    if manifest.schema_version > CURRENT_SCHEMA_VERSION:
        raise ValueError(
            f"Backup schema v{manifest.schema_version} is newer than "
            f"this tool (v{CURRENT_SCHEMA_VERSION}). "
            "Upgrade CodeFreedom before restoring this backup."
        )

    diffs = _compute_diff(manifest, target_dir)

    if not dry_run:
        data_bytes = _read_archive_bytes(archive_path, passphrase=passphrase)
        with tarfile.open(fileobj=io.BytesIO(data_bytes), mode="r:gz") as tar:
            tar.extractall(
                str(target_dir),
                members=[m for m in tar.getmembers() if m.name != "manifest.json"],
                filter="data",
            )

    return diffs, manifest
