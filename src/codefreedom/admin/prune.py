"""Prune old backups."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import List, Optional, Set

from codefreedom.admin._utils import (
    _read_manifest_from_archive,
    PruneResult,
)
from codefreedom.config import get_backup_dir
from codefreedom.log import eprint


def prune_backups(
    keep: Optional[int] = None,
    older_than: Optional[datetime.timedelta] = None,
    backup_dir: Optional[Path] = None,
) -> PruneResult:
    if backup_dir is None:
        backup_dir = get_backup_dir()

    if not backup_dir.exists():
        return PruneResult(deleted=[], kept=[], space_reclaimed=0)

    all_backups = sorted(backup_dir.glob("*.tar.gz"))
    to_delete: set[Path] = set()
    now = datetime.datetime.now(datetime.timezone.utc)

    if older_than is not None:
        cutoff = now - older_than
        for p in all_backups:
            try:
                m = _read_manifest_from_archive(p)
                created = datetime.datetime.strptime(
                    m.created_at, "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=datetime.timezone.utc)
                if created < cutoff:
                    to_delete.add(p)
            except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
                if isinstance(exc, ValueError) and "passphrase" in str(exc).lower():
                    eprint(
                        f"[ADMIN] Warning: cannot evaluate encrypted backup: {p.name}."
                    )
                continue

    if keep is not None and keep > 0:
        remaining = [p for p in all_backups if p not in to_delete]
        remaining_sorted = sorted(remaining)
        to_delete.update(
            remaining_sorted[:-keep] if len(remaining_sorted) > keep else []
        )

    after_delete = [p for p in all_backups if p not in to_delete]
    if not after_delete and len(all_backups) > 0 and len(to_delete) == len(all_backups):
        newest = max(all_backups, key=lambda p: p.stat().st_mtime)
        to_delete.discard(newest)

    space_reclaimed = 0
    deleted: List[Path] = []
    for p in sorted(to_delete):
        try:
            space_reclaimed += p.stat().st_size
            p.unlink()
            deleted.append(p)
        except OSError:
            continue

    kept = [p for p in all_backups if p not in to_delete]
    return PruneResult(
        deleted=deleted,
        kept=sorted(kept),
        space_reclaimed=space_reclaimed,
    )
