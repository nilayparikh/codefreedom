"""Backup, list, and inspect operations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Tuple

from codefreedom.admin._utils import (
    _backup_filename,
    _build_manifest,
    _collect_files,
    _dump_postgresql,
    _HAS_CRYPTOGRAPHY,
    _parse_backup_filename,
    _read_manifest_from_archive,
    _write_archive,
    BackupManifest,
    BackupSummary,
)
from codefreedom.core.config import get_backup_dir, get_codefreedom_dir


def backup(
    output_path: Optional[Path] = None,
    profile: str = "default",
    passphrase: Optional[str] = None,
    redact_secrets: Optional[bool] = None,
    skip_pg_dump: bool = False,
) -> Tuple[Path, BackupManifest]:
    if passphrase and not _HAS_CRYPTOGRAPHY:
        raise RuntimeError(
            "Encryption requires the 'cryptography' package.\n"
            "  Install: pip install codefreedom[encrypt]"
        )

    encrypting = bool(passphrase)
    source_dir = get_codefreedom_dir()
    if not source_dir.exists():
        raise FileNotFoundError(f"CodeFreedom home directory not found: {source_dir}")

    should_redact = redact_secrets if redact_secrets is not None else not encrypting

    if not skip_pg_dump:
        pg_backup_dir = get_codefreedom_dir() / "pg" / "backup"
        _dump_postgresql(pg_backup_dir)

    contents, categories = _collect_files(source_dir, redact_secrets=should_redact)

    manifest = _build_manifest(
        contents, categories, profile, secrets_redacted=should_redact
    )

    if output_path is None:
        backup_dir = get_backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)
        output_path = backup_dir / _backup_filename(profile)

    _write_archive(output_path, source_dir, manifest, passphrase=passphrase)

    return output_path, manifest


def list_backups(backup_dir: Optional[Path] = None) -> List[BackupSummary]:
    if backup_dir is None:
        backup_dir = get_backup_dir()

    if not backup_dir.exists():
        return []

    summaries: List[BackupSummary] = []
    for p in sorted(backup_dir.glob("*.tar.gz")):
        try:
            manifest = _read_manifest_from_archive(p)
            total_files = sum(len(e) for e in manifest.contents.values())
            total_size = sum(c.total_size for c in manifest.categories.values())
            summaries.append(
                BackupSummary(
                    path=p,
                    filename=p.name,
                    profile=manifest.profile,
                    created_at=manifest.created_at,
                    hostname=manifest.hostname,
                    total_files=total_files,
                    total_size=total_size,
                    secrets_redacted=manifest.secrets_redacted,
                )
            )
        except (OSError, json.JSONDecodeError, KeyError):
            continue
        except ValueError:
            info = _parse_backup_filename(p.name)
            summaries.append(
                BackupSummary(
                    path=p,
                    filename=p.name,
                    profile=info.get("profile", "?"),
                    created_at=info.get("created_at", ""),
                    hostname=info.get("hostname", "?"),
                    total_files=0,
                    total_size=p.stat().st_size,
                    secrets_redacted=False,
                )
            )

    summaries.sort(key=lambda s: s.created_at, reverse=True)
    return summaries


def inspect_backup(
    archive_path: Path,
    passphrase: Optional[str] = None,
) -> BackupManifest:
    if not archive_path.exists():
        raise FileNotFoundError(f"Backup file not found: {archive_path}")
    return _read_manifest_from_archive(archive_path, passphrase=passphrase)
