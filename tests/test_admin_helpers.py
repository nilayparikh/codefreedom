"""Pure-logic helpers for admin module.

Tests categorization, secrets detection, filename generation, SHA256,
manifest serialization, duration parsing, and encryption without I/O.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from codefreedom.admin import (
    CURRENT_SCHEMA_VERSION,
    BackupCategory,
    BackupFileEntry,
    BackupManifest,
    _backup_filename,
    _categorize,
    _decrypt_data,
    _encrypt_data,
    _is_encrypted_file,
    _is_managed,
    _is_secrets_file,
    _manifest_from_dict,
    _manifest_to_dict,
    _PG_DUMP_PREFIX,
    _sha256_file,
)
from codefreedom.cli.manage.admin import _parse_duration

pytestmark = pytest.mark.unit


# ── Secrets detection ─────────────────────────────────────────────────────────


class TestIsSecretsFile:
    def test_secrets_pattern(self):
        assert _is_secrets_file(".env.claude.secrets")
        assert _is_secrets_file("proxy/.env.proxy.secrets")
        assert _is_secrets_file(".secrets")
        assert _is_secrets_file("path/to/.env.secrets")

    def test_non_secrets(self):
        assert not _is_secrets_file(".env.claude")
        assert not _is_secrets_file("profiles/claude-code.yaml")
        assert not _is_secrets_file("proxy/config/config.yaml")
        assert not _is_secrets_file("some/other/file.txt")


# ── Categorization ────────────────────────────────────────────────────────────


class TestCategorize:
    def test_profiles(self):
        assert _categorize("profiles/claude-code.yaml") == "profiles"

    def test_proxy(self):
        assert _categorize("proxy/config/config.yaml") == "proxy"

    def test_sandbox(self):
        assert _categorize("sandbox/default/settings.json") == "sandbox"

    def test_proc(self):
        assert _categorize("proc/sessions/active.json") == "proc"

    def test_env(self):
        assert _categorize(".env.claude") == "env"

    def test_other(self):
        assert _categorize("some/random/file.txt") == "other"


class TestIsManaged:
    def test_profiles(self):
        assert _is_managed("profiles")
        assert _is_managed("profiles/claude-code.yaml")
        assert _is_managed("profiles/sub/dir/file.txt")

    def test_proxy(self):
        assert _is_managed("proxy")
        assert _is_managed("proxy/config/config.yaml")

    def test_scripts(self):
        assert _is_managed("scripts")
        assert _is_managed("scripts/setup.sh")

    def test_env_files(self):
        assert _is_managed(".env.user")
        assert _is_managed(".env.claude.secrets")
        assert _is_managed("proxy/.env.proxy.secrets")

    def test_not_managed(self):
        assert not _is_managed("sandbox/file.txt")
        assert not _is_managed("proc/data.json")
        assert not _is_managed("pg/backup.dump")


# ── Backup filename ───────────────────────────────────────────────────────────


class TestBackupFilename:
    def test_default_profile(self):
        name = _backup_filename("default")
        assert name.startswith("codefreedom-backup-default-")
        assert name.endswith(".tar.gz")
        parts = name.replace(".tar.gz", "").split("-")
        assert len(parts) >= 6

    def test_custom_profile(self):
        name = _backup_filename("my-work-profile")
        assert name.startswith("codefreedom-backup-my-work-profile-")

    def test_sanitized_profile(self):
        name = _backup_filename("test profile!!")
        assert "test_profile__" in name


# ── SHA256 ────────────────────────────────────────────────────────────────────


class TestSha256File:
    def test_compute_hash(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        h = _sha256_file(f)
        assert len(h) == 64
        assert h == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        h = _sha256_file(f)
        assert h == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


# ── Manifest serialization ────────────────────────────────────────────────────


class TestManifestSerialization:
    def test_roundtrip(self):
        manifest = BackupManifest(
            schema_version=CURRENT_SCHEMA_VERSION,
            tool_version="0.0.6",
            created_at="2026-06-04T14:30:22Z",
            hostname="test-machine",
            platform="linux",
            profile="default",
            secrets_redacted=True,
            contents={
                "profiles": [
                    BackupFileEntry(
                        path="test.json", size=10, sha256="abc", mode=0o644
                    ),
                ]
            },
            categories={
                "profiles": BackupCategory(count=1, total_size=10),
            },
        )
        d = _manifest_to_dict(manifest)
        m2 = _manifest_from_dict(d)
        assert m2.schema_version == manifest.schema_version
        assert m2.profile == manifest.profile
        assert m2.secrets_redacted == manifest.secrets_redacted
        assert m2.contents["profiles"][0].path == "test.json"
        assert m2.categories["profiles"].count == 1


# ── Duration parsing ──────────────────────────────────────────────────────────


class TestParseDuration:
    def test_days(self):
        assert _parse_duration("30d") == datetime.timedelta(days=30)

    def test_hours(self):
        assert _parse_duration("12h") == datetime.timedelta(hours=12)

    def test_minutes(self):
        assert _parse_duration("45m") == datetime.timedelta(minutes=45)

    def test_seconds(self):
        assert _parse_duration("30s") == datetime.timedelta(seconds=30)

    def test_weeks(self):
        assert _parse_duration("2w") == datetime.timedelta(weeks=2)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _parse_duration("invalid")
        with pytest.raises(ValueError):
            _parse_duration("30x")


# ── Encryption ────────────────────────────────────────────────────────────────


class TestEncryption:
    crypto = pytest.importorskip(
        "cryptography", reason="cryptography package not installed"
    )

    def test_roundtrip(self, tmp_path: Path):
        data = b"hello world sensitive data"
        encrypted = _encrypt_data(data, "my-passphrase")
        assert encrypted != data
        assert _is_encrypted_file(tmp_path) is False
        f = tmp_path / "backup.enc"
        f.write_bytes(encrypted)
        assert _is_encrypted_file(f) is True
        decrypted = _decrypt_data(encrypted, "my-passphrase")
        assert decrypted == data

    def test_wrong_passphrase_raises(self):
        data = b"secret data"
        encrypted = _encrypt_data(data, "correct-pass")
        with pytest.raises(Exception):
            _decrypt_data(encrypted, "wrong-pass")

    def test_no_cryptography_raises(self, monkeypatch):
        monkeypatch.setattr("codefreedom.admin._utils._HAS_CRYPTOGRAPHY", False)
        with pytest.raises(RuntimeError, match="cryptography"):
            _encrypt_data(b"data", "pass")

    def test_bad_magic_raises(self):
        with pytest.raises(ValueError, match="CodeFreedom"):
            _decrypt_data(b"garbage data", "pass")


# ── PostgreSQL dump ───────────────────────────────────────────────────────────


class TestPostgresDump:
    def test_pg_dump_prefix(self):
        assert _PG_DUMP_PREFIX == "codefreedom-pgdump"

    def test_categorize_pg_backup(self):
        assert (
            _categorize("pg/backup/codefreedom-pgdump-20260609-120000.dump")
            == "database"
        )

    def test_categorize_pg_data(self):
        assert _categorize("pg/data/somefile") == "database"
