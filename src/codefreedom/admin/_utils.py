"""Shared helpers for backup, restore, and prune operations."""

from __future__ import annotations

import datetime
import hashlib
import io
import json
import os
import platform
import re
import secrets as secrets_module
import stat
import subprocess
import sys
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from codefreedom import __version__
from codefreedom.log import eprint

# ── Optional cryptography ─────────────────────────────────────────────────────

_HAS_CRYPTOGRAPHY = False
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    _HAS_CRYPTOGRAPHY = True
except ImportError:
    pass

# ── Encryption constants ─────────────────────────────────────────────────────

_ENC_MAGIC = b"CFe\x01"
_ENC_SALT_LEN = 16
_ENC_NONCE_LEN = 12
_ENC_PBKDF_ITERATIONS = 600000
_ENC_HEADER_LEN = len(_ENC_MAGIC) + _ENC_SALT_LEN


# ── Encryption helpers ────────────────────────────────────────────────────────


def _is_encrypted_file(path: Path) -> bool:
    try:
        head = path.open("rb").read(len(_ENC_MAGIC))
        return head == _ENC_MAGIC
    except OSError:
        return False


def _encrypt_data(data: bytes, passphrase: str) -> bytes:
    if not _HAS_CRYPTOGRAPHY:
        raise RuntimeError(
            "Encryption requires the 'cryptography' package.\n"
            "  Install: pip install codefreedom[encrypt]"
        )
    salt = secrets_module.token_bytes(_ENC_SALT_LEN)
    nonce = secrets_module.token_bytes(_ENC_NONCE_LEN)
    key = _derive_key(passphrase, salt)
    ciphertext = AESGCM(key).encrypt(nonce, data, None)
    return _ENC_MAGIC + salt + nonce + ciphertext


def _decrypt_data(encrypted: bytes, passphrase: str) -> bytes:
    if not _HAS_CRYPTOGRAPHY:
        raise RuntimeError(
            "Decryption requires the 'cryptography' package.\n"
            "  Install: pip install codefreedom[encrypt]"
        )
    if encrypted[: len(_ENC_MAGIC)] != _ENC_MAGIC:
        raise ValueError("Not a CodeFreedom encrypted backup")
    salt = encrypted[len(_ENC_MAGIC) : len(_ENC_MAGIC) + _ENC_SALT_LEN]
    nonce = encrypted[
        len(_ENC_MAGIC)
        + _ENC_SALT_LEN : len(_ENC_MAGIC)
        + _ENC_SALT_LEN
        + _ENC_NONCE_LEN
    ]
    ciphertext = encrypted[len(_ENC_MAGIC) + _ENC_SALT_LEN + _ENC_NONCE_LEN :]
    key = _derive_key(passphrase, salt)
    return AESGCM(key).decrypt(nonce, ciphertext, None)


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_ENC_PBKDF_ITERATIONS,
    )
    return kdf.derive(passphrase.encode("utf-8"))


# ── Schema ────────────────────────────────────────────────────────────────────

CURRENT_SCHEMA_VERSION = 1

_SECRET_PATTERNS: List[str] = [
    ".secrets",
    ".secrets.",
    "secrets.json",
    ".credentials.json",
    ".env.secrets",
]

# ── Data structures ───────────────────────────────────────────────────────────


@dataclass
class BackupFileEntry:
    path: str
    size: int
    sha256: str
    mode: int
    redacted: bool = False
    redacted_content: Optional[bytes] = None


@dataclass
class BackupCategory:
    count: int
    total_size: int


@dataclass
class BackupManifest:
    schema_version: int
    tool_version: str
    created_at: str
    hostname: str
    platform: str
    profile: str
    secrets_redacted: bool
    contents: Dict[str, List[BackupFileEntry]]
    categories: Dict[str, BackupCategory]


@dataclass
class BackupSummary:
    path: Path
    filename: str
    profile: str
    created_at: str
    hostname: str
    total_files: int
    total_size: int
    secrets_redacted: bool


# ── Diff / restore ────────────────────────────────────────────────────────────


@dataclass
class FileDiff:
    status: str
    rel_path: str
    backup_size: int
    backup_sha256: str
    current_sha256: Optional[str] = None


# ── Managed file whitelist ────────────────────────────────────────────────────

_MANAGED_PATHS: List[str] = [
    "profiles",
    "proxy",
    "pg/backup",
    ".env.claude",
    ".env.claude.secrets",
    ".env.proxy",
    ".env.proxy.secrets",
]


def _is_managed(rel_path: str) -> bool:
    for prefix in _MANAGED_PATHS:
        if rel_path == prefix or rel_path.startswith(prefix + "/"):
            return True
    return False


def _could_contain_managed(rel_path: str) -> bool:
    if _is_managed(rel_path):
        return True
    for prefix in _MANAGED_PATHS:
        if prefix.startswith(rel_path + "/"):
            return True
    return False


# ── Secrets detection and redaction ────────────────────────────────────────────


def _is_secrets_file(rel_path: str) -> bool:
    for pattern in _SECRET_PATTERNS:
        if pattern in rel_path:
            return True
    return False


def _redact_value(value: str) -> str:
    stripped = value.strip().strip("\"'")
    if len(stripped) < 4:
        return "****"
    return stripped[:2] + "***" + stripped[-1:]


def _redact_secrets_content(content: bytes) -> bytes:
    result: List[str] = []
    for line in content.decode("utf-8", errors="replace").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, _, raw_value = line.partition("=")
            redacted = _redact_value(raw_value)
            result.append(f"{key}={redacted}")
        else:
            result.append(line)
    return "\n".join(result).encode("utf-8")


# ── File collection ───────────────────────────────────────────────────────────


def _collect_files(
    source_dir: Path,
    redact_secrets: bool = True,
) -> Tuple[Dict[str, List[BackupFileEntry]], Dict[str, BackupCategory]]:
    contents: Dict[str, List[BackupFileEntry]] = {}
    categories: Dict[str, BackupCategory] = {}

    for root, dirs, files in os.walk(source_dir):
        root_rel = Path(root).relative_to(source_dir)

        dirs[:] = [d for d in dirs if _could_contain_managed(str(root_rel / d))]

        for filename in sorted(files):
            full_path = Path(root) / filename
            rel_path = str(root_rel / filename) if str(root_rel) != "." else filename

            if not _is_managed(rel_path):
                continue

            if _is_secrets_file(rel_path) and redact_secrets:
                try:
                    original_bytes = full_path.read_bytes()
                except OSError:
                    continue
                redacted_bytes = _redact_secrets_content(original_bytes)
                sha = hashlib.sha256(redacted_bytes).hexdigest()
                file_size = len(redacted_bytes)
                try:
                    st = full_path.lstat()
                    file_mode = stat.S_IMODE(st.st_mode)
                except OSError:
                    file_mode = 0o600

                entry = BackupFileEntry(
                    path=rel_path,
                    size=file_size,
                    sha256=sha,
                    mode=file_mode,
                    redacted=True,
                    redacted_content=redacted_bytes,
                )
                cat = _categorize(rel_path)
                contents.setdefault(cat, []).append(entry)
                continue

            try:
                st = full_path.lstat()
                file_size = st.st_size
                file_mode = stat.S_IMODE(st.st_mode)
                sha = _sha256_file(full_path)
            except OSError:
                continue

            entry = BackupFileEntry(
                path=rel_path,
                size=file_size,
                sha256=sha,
                mode=file_mode,
            )

            cat = _categorize(rel_path)
            contents.setdefault(cat, []).append(entry)

    for cat, entries in contents.items():
        total = sum(e.size for e in entries)
        categories[cat] = BackupCategory(count=len(entries), total_size=total)

    return contents, categories


def _categorize(rel_path: str) -> str:
    if rel_path.startswith("profiles/"):
        return "profiles"
    if rel_path.startswith("proxy/"):
        return "proxy"
    if rel_path.startswith("sandbox/"):
        return "sandbox"
    if rel_path.startswith("proc/"):
        return "proc"
    if rel_path.startswith("pg/"):
        return "database"
    if rel_path.startswith(".env"):
        return "env"
    return "other"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ── PostgreSQL dump ───────────────────────────────────────────────────────────


_PG_DUMP_PREFIX = "codefreedom-pgdump"


def _find_litellm_container() -> Optional[str]:
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                "label=codefreedom.component=litellm-proxy",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        return result.stdout.strip().splitlines()[0]
    except (OSError, subprocess.TimeoutExpired):
        return None


def _dump_postgresql(pg_backup_dir: Path) -> Optional[Path]:
    container = _find_litellm_container()
    if container is None:
        eprint("[ADMIN] No running LiteLLM container found — skipping PostgreSQL dump.")
        return None

    pg_backup_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.datetime.now(datetime.timezone.utc)
    timestamp = now.strftime("%Y%m%d-%H%M%S")
    dump_filename = f"{_PG_DUMP_PREFIX}-{timestamp}.dump"
    container_dump_path = f"/var/lib/postgresql/backup/{dump_filename}"

    eprint(f"[ADMIN] Dumping PostgreSQL database from container '{container}'...")

    try:
        result = subprocess.run(
            [
                "docker",
                "exec",
                container,
                "pg_dump",
                "-U",
                "litellm",
                "-d",
                "litellm",
                "-Fc",
                "-f",
                container_dump_path,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if stderr:
                eprint(f"[ADMIN] Warning: pg_dump failed: {stderr}")
            else:
                eprint(
                    f"[ADMIN] Warning: pg_dump failed (exit code {result.returncode})."
                )
            return None

        dump_path = pg_backup_dir / dump_filename

        # Backup dir is a Docker named volume, not a bind-mount, so the
        # dump file must be copied out of the container onto the host.
        cp_result = subprocess.run(
            [
                "docker",
                "cp",
                f"{container}:{container_dump_path}",
                str(dump_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if cp_result.returncode != 0:
            stderr = cp_result.stderr.strip()
            eprint(
                f"[ADMIN] Warning: pg_dump succeeded but docker cp failed"
                f"{': ' + stderr if stderr else ''}"
            )
            return None

        if dump_path.exists():
            size = dump_path.stat().st_size
            eprint(
                f"[ADMIN] PostgreSQL dump created: {dump_filename}"
                f" ({_fmt_size_pg(size)})."
            )
            return dump_path

        eprint(
            f"[ADMIN] Warning: docker cp completed but dump file not found at {dump_path}."
        )
        return None

    except (OSError, subprocess.TimeoutExpired) as exc:
        eprint(f"[ADMIN] Warning: could not dump PostgreSQL: {exc}.")
        return None


def _fmt_size_pg(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / (1024 * 1024 * 1024):.1f} GB"


# ── Naming ────────────────────────────────────────────────────────────────────


def _sanitize(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", name)


def _backup_filename(profile: str) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    date_part = now.strftime("%Y%m%d")
    time_part = now.strftime("%H%M%S")
    host = _sanitize(platform.node() or "unknown")
    prof = _sanitize(profile) if profile else "default"
    return f"codefreedom-backup-{prof}-{date_part}-{time_part}-{host}.tar.gz"


_BACKUP_FILENAME_RE = re.compile(
    r"^codefreedom-backup-(.+)-(\d{8})-(\d{6})-(.+)\.tar\.gz$"
)


def _parse_backup_filename(filename: str) -> dict:
    m = _BACKUP_FILENAME_RE.match(filename)
    if not m:
        return {"profile": "?", "created_at": "", "hostname": "?"}
    profile = m.group(1)
    date_part = m.group(2)
    time_part = m.group(3)
    hostname = m.group(4)
    created_at = (
        f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}T"
        f"{time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}Z"
    )
    return {"profile": profile, "created_at": created_at, "hostname": hostname}


# ── Manifest building ─────────────────────────────────────────────────────────


def _build_manifest(
    contents: Dict[str, List[BackupFileEntry]],
    categories: Dict[str, BackupCategory],
    profile: str,
    secrets_redacted: bool = True,
) -> BackupManifest:
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return BackupManifest(
        schema_version=CURRENT_SCHEMA_VERSION,
        tool_version=__version__,
        created_at=now,
        hostname=platform.node() or "unknown",
        platform=sys.platform,
        profile=profile or "default",
        secrets_redacted=secrets_redacted,
        contents=contents,
        categories=categories,
    )


def _manifest_to_dict(m: BackupManifest) -> dict:
    return {
        "schema_version": m.schema_version,
        "tool_version": m.tool_version,
        "created_at": m.created_at,
        "hostname": m.hostname,
        "platform": m.platform,
        "profile": m.profile,
        "secrets_redacted": m.secrets_redacted,
        "contents": {
            cat: [
                {
                    "path": e.path,
                    "size": e.size,
                    "sha256": e.sha256,
                    "mode": e.mode,
                    "redacted": e.redacted,
                }
                for e in entries
            ]
            for cat, entries in m.contents.items()
        },
        "categories": {
            cat: {"count": c.count, "total_size": c.total_size}
            for cat, c in m.categories.items()
        },
    }


def _manifest_from_dict(d: dict) -> BackupManifest:
    return BackupManifest(
        schema_version=d["schema_version"],
        tool_version=d["tool_version"],
        created_at=d["created_at"],
        hostname=d["hostname"],
        platform=d["platform"],
        profile=d["profile"],
        secrets_redacted=d.get("secrets_redacted", d.get("secrets_excluded", False)),
        contents={
            cat: [
                BackupFileEntry(
                    path=e["path"],
                    size=e["size"],
                    sha256=e["sha256"],
                    mode=e["mode"],
                    redacted=e.get("redacted", False),
                )
                for e in entries
            ]
            for cat, entries in d["contents"].items()
        },
        categories={
            cat: BackupCategory(**c)  # type: ignore[arg-type]
            for cat, c in d["categories"].items()
        },
    )


# ── Diff ──────────────────────────────────────────────────────────────────────


def _compute_diff(manifest: BackupManifest, target_dir: Path) -> List[FileDiff]:
    diffs: List[FileDiff] = []

    for _cat, entries in manifest.contents.items():
        for entry in entries:
            current_path = target_dir / entry.path
            if not current_path.exists():
                diffs.append(
                    FileDiff(
                        status="ADD",
                        rel_path=entry.path,
                        backup_size=entry.size,
                        backup_sha256=entry.sha256,
                    )
                )
            else:
                try:
                    current_sha = _sha256_file(current_path)
                except OSError:
                    current_sha = None

                if current_sha == entry.sha256:
                    diffs.append(
                        FileDiff(
                            status="OK",
                            rel_path=entry.path,
                            backup_size=entry.size,
                            backup_sha256=entry.sha256,
                            current_sha256=current_sha,
                        )
                    )
                else:
                    diffs.append(
                        FileDiff(
                            status="MOD",
                            rel_path=entry.path,
                            backup_size=entry.size,
                            backup_sha256=entry.sha256,
                            current_sha256=current_sha,
                        )
                    )

    status_order = {"ADD": 0, "MOD": 1, "OK": 2}
    diffs.sort(key=lambda d: (status_order.get(d.status, 9), d.rel_path))
    return diffs


# ── Archive I/O ───────────────────────────────────────────────────────────────


def _write_archive(
    archive_path: Path,
    source_dir: Path,
    manifest: BackupManifest,
    passphrase: Optional[str] = None,
) -> None:
    manifest_dict = _manifest_to_dict(manifest)
    manifest_bytes = json.dumps(manifest_dict, indent=2, sort_keys=True).encode("utf-8")

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(manifest_bytes)
        info.mtime = int(time.time())
        tar.addfile(info, io.BytesIO(manifest_bytes))

        for _cat, entries in manifest.contents.items():
            for entry in entries:
                if entry.redacted and entry.redacted_content is not None:
                    t_info = tarfile.TarInfo(name=entry.path)
                    t_info.size = len(entry.redacted_content)
                    t_info.mtime = int(time.time())
                    t_info.mode = entry.mode
                    tar.addfile(t_info, io.BytesIO(entry.redacted_content))
                else:
                    full_path = source_dir / entry.path
                    try:
                        tar.add(str(full_path), arcname=entry.path)
                    except OSError:
                        continue

    archive_data = buf.getvalue()

    if passphrase:
        archive_data = _encrypt_data(archive_data, passphrase)

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_bytes(archive_data)


def _read_archive_bytes(path: Path, passphrase: Optional[str] = None) -> bytes:
    raw = path.read_bytes()
    if _is_encrypted_file(path):
        if not passphrase:
            raise ValueError(
                f"Backup is encrypted: {path.name}\n" "  Use --passphrase to decrypt."
            )
        raw = _decrypt_data(raw, passphrase)
    return raw


def _read_manifest_from_archive(
    archive_path: Path,
    passphrase: Optional[str] = None,
) -> BackupManifest:
    data_bytes = _read_archive_bytes(archive_path, passphrase=passphrase)
    with tarfile.open(fileobj=io.BytesIO(data_bytes), mode="r:gz") as tar:
        member = tar.getmember("manifest.json")
        f = tar.extractfile(member)
        if f is None:
            raise ValueError("manifest.json is empty in archive")
        data = json.loads(f.read().decode("utf-8"))
    return _manifest_from_dict(data)


# ── Prune result ──────────────────────────────────────────────────────────────


@dataclass
class PruneResult:
    deleted: List[Path]
    kept: List[Path]
    space_reclaimed: int
