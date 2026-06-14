"""Tests for admin.py — backup, restore, list, inspect, prune."""

from __future__ import annotations

import datetime
import io
import json
from typing import Any
import tarfile
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
    _dump_postgresql,
    _encrypt_data,
    _find_litellm_container,
    _is_encrypted_file,
    _is_secrets_file,
    _manifest_from_dict,
    _manifest_to_dict,
    _PG_DUMP_PREFIX,
    _read_manifest_from_archive,
    _sha256_file,
    backup as engine_backup,
    inspect_backup,
    list_backups,
    prune_backups,
    restore as engine_restore,
)
from codefreedom.cli.manage.admin import _parse_duration

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(name="cf_home_dir")
def _cf_home_fixture(monkeypatch, tmp_path: Path) -> Path:
    """Create a temporary CodeFreedom home with realistic config files."""
    home = tmp_path / "codefreedom-home"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(home))
    _populate_cf_home(home)
    return home


def _populate_cf_home(home: Path) -> None:
    """Populate *home* with a standard set of test config files."""
    files = {
        "profiles/claude-code.yaml": "model: claude-sonnet-4\n",
        "profiles/chrome.yaml": "port: 9222\nheadless: true\n",
        "profiles/web.yaml": "port: 8420\n",
        "proxy/config/config.yaml": "general:\n  debug: false\n",
        "proxy/config/providers/deepseek.yaml": "model: deepseek-chat",
        "proxy/docker-compose.yaml": "version: '3'\nservices:\n  litellm:\n",
        "scripts/setup-secrets.sh": "#!/bin/bash\necho setup\n",
        ".env.claude": "ANTHROPIC_BASE_URL=http://localhost:4000",
        ".env.claude.secrets": "ANTHROPIC_AUTH_TOKEN=sk-secret-abc",
        ".env.mimo.secrets": "MIMO_API_KEY=sk-mimo-abc",
        ".env.opencode.secrets": "OPENCODE_API_KEY=sk-opencode-abc",
        ".env.proxy": "LITELLM_MASTER_KEY=sk-test-key",
        ".env.proxy.secrets": "LITELLM_DB_PASSWORD=supersecret",
        ".env.user": "CUSTOM_VAR=custom_value",
        "proc/sessions/active.json": '{"session_id": "abc123"}',
        "proc/tools/chrome.yaml": "status: running\n",
        "sandbox/default/.claude/settings.json": '{"theme": "dark"}',
        "sandbox/tools/chrome/data.txt": "browser cache data",
    }
    for rel, content in files.items():
        p = home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)


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


# ── Backup filename ───────────────────────────────────────────────────────────


class TestBackupFilename:
    def test_default_profile(self):
        name = _backup_filename("default")
        assert name.startswith("codefreedom-backup-default-")
        assert name.endswith(".tar.gz")
        # Check date format embedded
        parts = name.replace(".tar.gz", "").split("-")
        assert (
            len(parts) >= 6
        )  # codefreedom, backup, default, YYYYMMDD, HHMMSS, hostname

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
        assert len(h) == 64  # hex-encoded SHA-256
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


# ── Backup ────────────────────────────────────────────────────────────────────


@pytest.mark.usefixtures("cf_home_dir")
class TestBackup:
    def test_basic_backup(self):
        out_path, manifest = engine_backup(profile="test")
        assert out_path.exists()
        assert out_path.suffixes == [".tar", ".gz"]
        assert manifest.profile == "test"
        assert manifest.secrets_redacted is True
        assert manifest.schema_version == CURRENT_SCHEMA_VERSION
        assert manifest.hostname

    def test_all_categories(self):
        _out_path, manifest = engine_backup()
        assert "profiles" in manifest.categories
        assert "proxy" in manifest.categories
        assert "scripts" in manifest.categories
        assert "env" in manifest.categories
        # sandbox/ and proc/ are not in managed scope
        assert "sandbox" not in manifest.categories
        assert "proc" not in manifest.categories

    def test_secrets_redacted(self):
        """Secrets files ARE backed up but with redacted values."""
        _out_path, manifest = engine_backup()
        all_paths = set()
        for entries in manifest.contents.values():
            for e in entries:
                all_paths.add(e.path)
        # Secrets should be present (redacted)
        assert ".env.claude.secrets" in all_paths
        assert ".env.proxy.secrets" in all_paths
        assert ".env.mimo.secrets" in all_paths
        assert ".env.opencode.secrets" in all_paths
        # Non-secrets env files SHOULD be present
        assert ".env.claude" in all_paths
        assert ".env.proxy" in all_paths
        assert ".env.user" in all_paths

    def test_correct_file_count(self):
        """14 managed files should be backed up (10 regular + 4 secrets)."""
        _out_path, manifest = engine_backup(skip_pg_dump=True)
        total = sum(len(e) for e in manifest.contents.values())
        assert total == 14

    def test_archive_is_valid_tar_gz(self):
        out_path, _manifest = engine_backup()
        # Verify it's a valid gzip + tar archive with manifest.json
        with tarfile.open(str(out_path), "r:gz") as tar:
            names = tar.getnames()
            assert "manifest.json" in names

    def test_manifest_is_first_entry(self):
        """manifest.json should be the first entry for fast extraction."""
        out_path, _manifest = engine_backup()
        with tarfile.open(str(out_path), "r:gz") as tar:
            names = tar.getnames()
            assert names[0] == "manifest.json"

    def test_manifest_content(self):
        out_path, manifest = engine_backup()
        read_manifest = _read_manifest_from_archive(out_path)
        assert read_manifest.profile == manifest.profile
        assert read_manifest.created_at == manifest.created_at
        assert read_manifest.schema_version == CURRENT_SCHEMA_VERSION

    def test_custom_output_path(self, tmp_path: Path):
        custom_path = tmp_path / "my-backup.tar.gz"
        out_path, manifest = engine_backup(output_path=custom_path, profile="custom")
        assert out_path == custom_path
        assert custom_path.exists()
        assert manifest.profile == "custom"

    def test_nonexistent_home_raises(self, monkeypatch):
        monkeypatch.setenv("CODEFREEDOM_HOME", "/nonexistent/codefreedom-home")
        with pytest.raises(FileNotFoundError):
            engine_backup()


# ── List backups ──────────────────────────────────────────────────────────────


@pytest.mark.usefixtures("cf_home_dir")
class TestListBackups:
    def test_empty_dir(self, tmp_path: Path):
        summaries = list_backups(backup_dir=tmp_path / "nonexistent")
        assert summaries == []

    def test_lists_backups(self):
        engine_backup(profile="p1")
        engine_backup(profile="p2")
        summaries = list_backups()
        assert len(summaries) == 2
        # Newest first
        assert summaries[0].created_at >= summaries[1].created_at

    def test_summary_fields(self):
        engine_backup(profile="test-profile")
        s = list_backups()[0]
        assert s.filename.startswith("codefreedom-backup-test-profile-")
        assert s.profile == "test-profile"
        assert s.total_files > 0
        assert s.total_size > 0
        assert s.secrets_redacted is True


# ── Inspect ───────────────────────────────────────────────────────────────────


@pytest.mark.usefixtures("cf_home_dir")
class TestInspect:
    def test_inspect_valid(self):
        out_path, _manifest = engine_backup()
        m = inspect_backup(out_path)
        assert m.schema_version == CURRENT_SCHEMA_VERSION
        assert m.profile == "default"

    def test_inspect_missing(self):
        with pytest.raises(FileNotFoundError):
            inspect_backup(Path("/nonexistent/backup.tar.gz"))


# ── Restore ───────────────────────────────────────────────────────────────────


class TestRestore:
    def test_dry_run(self, cf_home_dir: Path):
        out_path, _manifest = engine_backup()
        target = cf_home_dir.parent / "restore-target"
        target.mkdir()
        diffs, _ = engine_restore(out_path, target_dir=target, dry_run=True)
        assert len(diffs) > 0
        # Nothing should be written
        assert not (target / ".env.claude").exists()

    def test_actual_restore(self, cf_home_dir: Path):
        out_path, _manifest = engine_backup()
        target = cf_home_dir.parent / "restore-target"
        target.mkdir()
        engine_restore(out_path, target_dir=target, dry_run=False)
        assert (target / ".env.claude").exists()
        assert (target / "profiles/claude-code.yaml").exists()
        # Secrets ARE restored (with redacted values)
        assert (target / ".env.claude.secrets").exists()
        # Verify redacted content
        secrets_content = (target / ".env.claude.secrets").read_text()
        assert "sk***c" in secrets_content

    def test_diff_statuses(self, cf_home_dir: Path):
        out_path, _manifest = engine_backup()
        target = cf_home_dir.parent / "restore-target"
        target.mkdir()

        # All ADD
        diffs, _ = engine_restore(out_path, target_dir=target, dry_run=True)
        assert all(d.status == "ADD" for d in diffs)

        # Restore first, then some should be OK, some MOD
        engine_restore(out_path, target_dir=target, dry_run=False)
        # Modify one file
        (target / ".env.claude").write_text("MODIFIED_CONTENT")
        diffs2, _ = engine_restore(out_path, target_dir=target, dry_run=True)
        statuses = {d.status for d in diffs2}
        assert "MOD" in statuses
        assert "OK" in statuses

    @pytest.mark.usefixtures("cf_home_dir")
    def test_invalid_schema_version(self, tmp_path: Path):
        """Create a backup with a future schema version and verify it's rejected."""
        out_path, _manifest = engine_backup()
        # Corrupt the manifest
        with tarfile.open(str(out_path), "r:gz") as tar:
            entry = tar.extractfile("manifest.json")
            assert entry is not None, "manifest.json not found in archive"
            data = json.loads(entry.read())
        data["schema_version"] = 999
        # Rewrite
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            info = tarfile.TarInfo(name="manifest.json")
            payload = json.dumps(data).encode()
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))

        corrupted = tmp_path / "bad-backup.tar.gz"
        corrupted.write_bytes(buf.getvalue())

        with pytest.raises(ValueError, match="schema"):
            engine_restore(corrupted, dry_run=True)


# ── Prune ─────────────────────────────────────────────────────────────────────


class TestPrune:
    @pytest.mark.usefixtures("cf_home_dir")
    def test_prune_nothing(self):
        """Prune with no backups is a no-op."""
        result = prune_backups(keep=5)
        assert result.deleted == []
        assert result.kept == []

    @pytest.mark.usefixtures("cf_home_dir")
    def test_prune_keep_2(self):
        for i in range(5):
            engine_backup(profile=f"test-{i}")
        result = prune_backups(keep=2)
        assert len(result.deleted) == 3
        assert len(result.kept) == 2
        assert result.space_reclaimed > 0

    @pytest.mark.usefixtures("cf_home_dir")
    def test_prune_keep_all(self):
        for i in range(3):
            engine_backup(profile=f"test-{i}")
        result = prune_backups(keep=10)
        assert len(result.deleted) == 0
        assert len(result.kept) == 3

    def test_prune_older_than(self, cf_home_dir: Path):
        """Create a backup with an old timestamp and a recent one."""
        # Create a backup with old date by writing the archive directly
        old_backup = (
            cf_home_dir
            / "backup"
            / "codefreedom-backup-old-20250101-000000-oldhost.tar.gz"
        )
        old_backup.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(
            {
                "schema_version": 1,
                "tool_version": "0.0.6",
                "created_at": "2025-01-01T00:00:00Z",
                "hostname": "oldhost",
                "platform": "linux",
                "profile": "old",
                "secrets_excluded": True,
                "contents": {},
                "categories": {},
            }
        ).encode()
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            info = tarfile.TarInfo(name="manifest.json")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        old_backup.write_bytes(buf.getvalue())

        # Create a recent backup
        engine_backup(profile="recent")

        result = prune_backups(older_than=datetime.timedelta(days=30))
        assert len(result.deleted) == 1
        assert len(result.kept) == 1
        assert "old" in result.deleted[0].name


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

    @pytest.mark.usefixtures("cf_home_dir")
    def test_encrypted_backup_has_full_secrets(self):
        """With passphrase, secrets are not redacted."""
        out_path, manifest = engine_backup(passphrase="test-pass")
        assert manifest.secrets_redacted is False
        assert out_path.exists()
        # Archive should have encryption magic header
        assert _is_encrypted_file(out_path)

    @pytest.mark.usefixtures("cf_home_dir")
    def test_encrypted_backup_needs_passphrase(self):
        out_path, _manifest = engine_backup(passphrase="test-pass")
        # Without passphrase, should error
        with pytest.raises(ValueError, match="passphrase"):
            _read_manifest_from_archive(out_path)

    def test_encrypted_restore(self, cf_home_dir: Path):
        out_path, _manifest = engine_backup(passphrase="secret-123")
        target = cf_home_dir.parent / "enc-restore-target"
        target.mkdir()
        engine_restore(out_path, target_dir=target, passphrase="secret-123")
        assert (target / ".env.claude").exists()
        assert (target / ".env.claude.secrets").exists()
        # Full secret values should be present
        secrets_content = (target / ".env.claude.secrets").read_text()
        assert "sk-secret-abc" in secrets_content  # full value, not redacted

    @pytest.mark.usefixtures("cf_home_dir")
    def test_encrypted_without_passphrase_fails(self):
        out_path, _manifest = engine_backup(passphrase="test-pass")
        with pytest.raises(ValueError, match="passphrase"):
            engine_restore(out_path, dry_run=True)

    @pytest.mark.usefixtures("cf_home_dir")
    def test_inspect_encrypted(self):
        out_path, _manifest = engine_backup(passphrase="inspect-pass")
        manifest = inspect_backup(out_path, passphrase="inspect-pass")
        assert manifest.schema_version == CURRENT_SCHEMA_VERSION

    @pytest.mark.usefixtures("cf_home_dir")
    def test_inspect_encrypted_without_passphrase(self):
        out_path, _manifest = engine_backup(passphrase="inspect-pass")
        with pytest.raises(ValueError, match="passphrase"):
            inspect_backup(out_path)


# ── PostgreSQL dump ───────────────────────────────────────────────────────────


class TestPostgresDump:
    def test_pg_dump_prefix(self):
        """Verify the pg dump prefix constant."""
        assert _PG_DUMP_PREFIX == "codefreedom-pgdump"

    def test_categorize_pg_backup(self):
        """PG backup files should be categorized as 'database'."""
        assert (
            _categorize("pg/backup/codefreedom-pgdump-20260609-120000.dump")
            == "database"
        )

    def test_categorize_pg_data(self):
        """PG data directory is also categorized as 'database'."""
        assert _categorize("pg/data/somefile") == "database"

    def test_managed_paths_includes_pg(self, cf_home_dir: Path):
        """PG backup dir within managed scope should be collected."""
        # Create a test pg dump file
        pg_backup = cf_home_dir / "pg" / "backup"
        pg_backup.mkdir(parents=True, exist_ok=True)
        (pg_backup / "codefreedom-pgdump-20260609-120000.dump").write_text(
            "PG_DUMP_CONTENT"
        )

        _out_path, manifest = engine_backup(profile="pg-test", skip_pg_dump=True)
        all_paths = set()
        for entries in manifest.contents.values():
            for e in entries:
                all_paths.add(e.path)

        assert "pg/backup/codefreedom-pgdump-20260609-120000.dump" in all_paths
        assert "database" in manifest.categories

    def test_backup_with_pg_dump_success(self, cf_home_dir: Path, monkeypatch):
        """Simulate a successful pg_dump and verify the dump is included."""
        pg_backup = cf_home_dir / "pg" / "backup"
        pg_backup.mkdir(parents=True, exist_ok=True)

        call_count = [0]

        def mock_subprocess_run(*args: Any, **_kwargs: Any) -> Any:
            import subprocess

            nonlocal call_count
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: docker ps (find container)
                return subprocess.CompletedProcess(
                    args[0] if args else [],
                    returncode=0,
                    stdout="litellm-codefreedom-0000\n",
                    stderr="",
                )
            elif call_count[0] == 2:
                # Second call: pg_dump
                dump_path = pg_backup / "codefreedom-pgdump-20260609-120000.dump"
                dump_path.write_text("SIMULATED_PG_DUMP")
                return subprocess.CompletedProcess(
                    args[0] if args else [], returncode=0, stdout="", stderr=""
                )
            return subprocess.CompletedProcess(
                args[0] if args else [], returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr("codefreedom.admin._utils.subprocess.run", mock_subprocess_run)

        _out_path, manifest = engine_backup(profile="pg-success-test")

        all_paths = set()
        for entries in manifest.contents.values():
            for e in entries:
                all_paths.add(e.path)

        pg_dump_files = [p for p in all_paths if _PG_DUMP_PREFIX in p]
        assert len(pg_dump_files) == 1, f"Expected 1 pg dump file, got {pg_dump_files}"
        assert "database" in manifest.categories

    @pytest.mark.usefixtures("cf_home_dir")
    def test_backup_with_skip_pg_dump(self, monkeypatch):
        """skip_pg_dump=True should skip the pg_dump call entirely."""
        import sys

        called = [False]

        def mock_run(*_: Any, **__: Any) -> None:
            called[0] = True

        monkeypatch.setattr(
            sys.modules["codefreedom.admin.backup"], "_dump_postgresql", mock_run
        )

        engine_backup(profile="skip-pg-test", skip_pg_dump=True)

        # _dump_postgresql should NOT have been called
        assert called[0] is False

    @pytest.mark.usefixtures("cf_home_dir")
    def test_backup_without_skip_pg_dump_calls_dump(self, monkeypatch):
        """skip_pg_dump=False (default) should call _dump_postgresql."""
        import sys

        called = [False]

        def mock_dump(*_: Any, **__: Any) -> None:
            called[0] = True

        monkeypatch.setattr(
            sys.modules["codefreedom.admin.backup"], "_dump_postgresql", mock_dump
        )

        engine_backup(profile="call-pg-test")

        assert called[0] is True

    def test_find_litellm_container_no_docker(self, monkeypatch):
        """_find_litellm_container returns None when docker is not available."""

        def mock_run(*args: Any, **_kwargs: Any) -> Any:
            raise FileNotFoundError("docker not found")

        monkeypatch.setattr("codefreedom.admin._utils.subprocess.run", mock_run)
        result = _find_litellm_container()
        assert result is None

    def test_find_litellm_container_running(self, monkeypatch):
        """_find_litellm_container returns container name when running."""

        def mock_run(*args: Any, **_kwargs: Any) -> Any:
            import subprocess

            return subprocess.CompletedProcess(
                args[0] if args else [],
                returncode=0,
                stdout="litellm-codefreedom-0000\n",
                stderr="",
            )

        monkeypatch.setattr("codefreedom.admin._utils.subprocess.run", mock_run)
        result = _find_litellm_container()
        assert result == "litellm-codefreedom-0000"

    def test_find_litellm_container_not_running(self, monkeypatch):
        """_find_litellm_container returns None when no container is running."""

        def mock_run(*args: Any, **_kwargs: Any) -> Any:
            import subprocess

            return subprocess.CompletedProcess(
                args[0] if args else [],
                returncode=0,
                stdout="",
                stderr="",
            )

        monkeypatch.setattr("codefreedom.admin._utils.subprocess.run", mock_run)
        result = _find_litellm_container()
        assert result is None

    def test_dump_postgresql_no_container(self, cf_home_dir: Path, monkeypatch):
        """_dump_postgresql returns None when no container is running."""
        monkeypatch.setattr("codefreedom.admin._utils._find_litellm_container", lambda: None)
        pg_backup = cf_home_dir / "pg" / "backup"
        result = _dump_postgresql(pg_backup)
        assert result is None

    def test_dump_postgresql_success(self, cf_home_dir: Path, monkeypatch):
        """_dump_postgresql returns the dump path on success."""
        pg_backup = cf_home_dir / "pg" / "backup"
        pg_backup.mkdir(parents=True, exist_ok=True)

        frozen_now = datetime.datetime(
            2026, 6, 9, 12, 0, 0, tzinfo=datetime.timezone.utc
        )

        monkeypatch.setattr(
            "codefreedom.admin._utils._find_litellm_container",
            lambda: "litellm-codefreedom-0000",
        )
        monkeypatch.setattr(
            "codefreedom.admin._utils.datetime.datetime",
            # Mock datetime.now to return frozen time
            type(
                "MockDateTime",
                (),
                {
                    "now": staticmethod(lambda tz=None: frozen_now),
                    "timezone": datetime.timezone,
                },
            ),
        )

        def mock_run(*args: Any, **_kwargs: Any) -> Any:
            import subprocess

            if args and "pg_dump" in str(args):
                # Simulate file creation by pg_dump using the same filename pattern
                dump_filename = f"{_PG_DUMP_PREFIX}-20260609-120000.dump"
                dump_path = pg_backup / dump_filename
                dump_path.write_text("PG_DUMP_SIMULATED")
                return subprocess.CompletedProcess(
                    args[0] if args else [],
                    returncode=0,
                    stdout="",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args[0] if args else [],
                returncode=0,
                stdout="",
                stderr="",
            )

        monkeypatch.setattr("codefreedom.admin._utils.subprocess.run", mock_run)
        result = _dump_postgresql(pg_backup)
        assert result is not None
        assert result.exists()
        assert _PG_DUMP_PREFIX in result.name

    def test_dump_postgresql_failure(self, cf_home_dir: Path, monkeypatch):
        """_dump_postgresql returns None when pg_dump fails."""
        pg_backup = cf_home_dir / "pg" / "backup"
        pg_backup.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(
            "codefreedom.admin._utils._find_litellm_container",
            lambda: "litellm-codefreedom-0000",
        )

        def mock_run(*args: Any, **_kwargs: Any) -> Any:
            import subprocess

            return subprocess.CompletedProcess(
                args[0] if args else [],
                returncode=1,
                stdout="",
                stderr="pg_dump: error: connection to server failed",
            )

        monkeypatch.setattr("codefreedom.admin._utils.subprocess.run", mock_run)
        result = _dump_postgresql(pg_backup)
        assert result is None
