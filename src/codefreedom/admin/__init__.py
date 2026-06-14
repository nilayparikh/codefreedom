"""Backup and restore engine for CodeFreedom configuration."""

from __future__ import annotations

from codefreedom.admin.backup import backup, inspect_backup, list_backups
from codefreedom.admin.prune import prune_backups
from codefreedom.admin.restore import restore
from codefreedom.admin._utils import (  # noqa: F401
    BackupCategory,
    BackupFileEntry,
    BackupManifest,
    BackupSummary,
    CURRENT_SCHEMA_VERSION,
    FileDiff,
    _backup_filename,
    _categorize,
    _decrypt_data,
    _dump_postgresql,
    _encrypt_data,
    _find_litellm_container,
    _is_encrypted_file,
    _is_managed,
    _is_secrets_file,
    _manifest_from_dict,
    _manifest_to_dict,
    _PG_DUMP_PREFIX,
    _read_manifest_from_archive,
    _sha256_file,
)

__all__ = [
    "backup",
    "list_backups",
    "inspect_backup",
    "restore",
    "prune_backups",
    "BackupSummary",
    "FileDiff",
]
