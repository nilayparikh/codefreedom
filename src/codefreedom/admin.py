"""Backup and restore engine for CodeFreedom configuration.

Usage (via CLI):
    codefreedom admin backup                          # default path
    codefreedom admin backup --out /path/to/file.tar.gz
    codefreedom admin restore --in /path/to/file.tar.gz
    codefreedom admin restore --in /path/to/file.tar.gz --dry-run
    codefreedom admin list-backups
    codefreedom admin inspect /path/to/file.tar.gz
    codefreedom admin prune --keep 5
    codefreedom admin prune --older-than 30d

Secrets (*.secrets files) are backed up with VALUES REDACTED.
The key names and structure are preserved; values show only the
first 2 and last 1 character (e.g., ``sk-secret-abc`` → ``sk***bc``).
This lets you identify which secrets need replacement after restore.

Use ``--passphrase`` to encrypt the archive. When encrypted, secrets are
stored with full values (not redacted) and the entire archive is
encrypted with AES-256-GCM via PBKDF2 key derivation.

Backup scope is limited to user-managed files:
  - ``profiles/`` directory
  - ``proxy/`` directory
  - ``.env.claude``, ``.env.claude.secrets``
  - ``.env.proxy``, ``.env.proxy.secrets``
"""

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
from codefreedom.config import get_backup_dir, get_codefreedom_dir
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

_ENC_MAGIC = b"CFe\x01"  # 4 bytes: magic + version byte
_ENC_SALT_LEN = 16
_ENC_NONCE_LEN = 12
_ENC_PBKDF_ITERATIONS = 600000
_ENC_HEADER_LEN = len(_ENC_MAGIC) + _ENC_SALT_LEN


# ── Encryption helpers ────────────────────────────────────────────────────────


def _is_encrypted_file(path: Path) -> bool:
    """Return True if *path* starts with the CodeFreedom encryption magic."""
    try:
        head = path.open("rb").read(len(_ENC_MAGIC))
        return head == _ENC_MAGIC
    except OSError:
        return False


def _encrypt_data(data: bytes, passphrase: str) -> bytes:
    """Encrypt *data* with *passphrase* using AES-256-GCM + PBKDF2.

    Returns: [magic: 4B][salt: 16B][ciphertext + tag: variable]
    """
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
    """Decrypt *encrypted* bytes (produced by ``_encrypt_data``)."""
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
    """Derive a 32-byte AES-256 key from *passphrase* via PBKDF2HMAC."""
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
    """A single file tracked in the backup manifest."""

    path: str  # relative to CodeFreedom home
    size: int
    sha256: str
    mode: int
    redacted: bool = False
    # In-memory redacted content (only populated during backup for secrets files)
    redacted_content: Optional[bytes] = None


@dataclass
class BackupCategory:
    """Aggregate stats for a category of files."""

    count: int
    total_size: int


@dataclass
class BackupManifest:
    """Full manifest metadata embedded in the backup archive."""

    schema_version: int
    tool_version: str
    created_at: str  # ISO 8601 UTC
    hostname: str
    platform: str
    profile: str
    secrets_redacted: bool
    contents: Dict[str, List[BackupFileEntry]]
    categories: Dict[str, BackupCategory]


@dataclass
class BackupSummary:
    """Summary of a single backup for listing."""

    path: Path
    filename: str
    profile: str
    created_at: str  # ISO 8601
    hostname: str
    total_files: int
    total_size: int
    secrets_redacted: bool


# ── Diff / restore ────────────────────────────────────────────────────────────


@dataclass
class FileDiff:
    """Result of comparing a backup file against current state."""

    status: str  # ADD | MOD | OK | SKIP
    rel_path: str
    backup_size: int
    backup_sha256: str
    current_sha256: Optional[str] = None


# ── Managed file whitelist ────────────────────────────────────────────────────
# Only these files/directories under the CodeFreedom home are backed up.

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
    """Return True if *rel_path* is within the managed backup scope."""
    for prefix in _MANAGED_PATHS:
        if rel_path == prefix or rel_path.startswith(prefix + "/"):
            return True
    return False


def _could_contain_managed(rel_path: str) -> bool:
    """Return True if *rel_path* could be a parent directory of a managed path.

    This is used during directory traversal to decide whether to descend
    into a directory. A directory ``pg`` could contain the managed child
    ``pg/backup``, so we need to enter it even though ``pg`` itself is not
    a managed path.
    """
    if _is_managed(rel_path):
        return True
    for prefix in _MANAGED_PATHS:
        if prefix.startswith(rel_path + "/"):
            return True
    return False


# ── Secrets detection and redaction ────────────────────────────────────────────


def _is_secrets_file(rel_path: str) -> bool:
    """Return True if *rel_path* appears to contain secrets data."""
    for pattern in _SECRET_PATTERNS:
        if pattern in rel_path:
            return True
    return False


def _redact_value(value: str) -> str:
    """Redact a secret value, keeping first 2 and last 1 character visible.

    Examples:
        ``sk-secret-abc`` → ``sk***bc``
        ``supersecret`` → ``su***t``
        ``ab`` → ``****``  (too short)
    """
    stripped = value.strip().strip("\"'")
    if len(stripped) < 4:
        return "****"
    return stripped[:2] + "***" + stripped[-1:]


def _redact_secrets_content(content: bytes) -> bytes:
    """Redact values in a ``.env``-style secrets file.

    Preserves keys, comments, and blank lines. Only ``KEY=VALUE`` lines
    have their values redacted. Lines without ``=`` are left as-is.
    """
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
    """Walk *source_dir* and collect managed files for backup.

    Only backs up the whitelisted paths in ``_MANAGED_PATHS``.
    When *redact_secrets* is True (default), secrets files have
    values redacted. When False, full values are preserved.

    Args:
        source_dir: The CodeFreedom home directory to back up.
        redact_secrets: If True, redact secret values (default).

    Returns:
        Tuple of (contents_by_category, categories).
    """
    contents: Dict[str, List[BackupFileEntry]] = {}
    categories: Dict[str, BackupCategory] = {}

    for root, dirs, files in os.walk(source_dir):
        root_rel = Path(root).relative_to(source_dir)

        # Prune: only descend into directories that could contain managed files
        dirs[:] = [d for d in dirs if _could_contain_managed(str(root_rel / d))]

        for filename in sorted(files):
            full_path = Path(root) / filename
            rel_path = str(root_rel / filename) if str(root_rel) != "." else filename

            # Skip files not in the managed whitelist
            if not _is_managed(rel_path):
                continue

            # ── Redact secrets only when not encrypting ────────────────
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

            # ── Compute file metadata for normal files ─────────────────
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

            # ── Categorize ──────────────────────────────────────────────
            cat = _categorize(rel_path)
            contents.setdefault(cat, []).append(entry)

    # Compute category aggregates
    for cat, entries in contents.items():
        total = sum(e.size for e in entries)
        categories[cat] = BackupCategory(count=len(entries), total_size=total)

    return contents, categories


def _categorize(rel_path: str) -> str:
    """Assign a file to a category based on its path."""
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
    """Compute SHA-256 hex digest of *path*."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ── PostgreSQL dump ───────────────────────────────────────────────────────────


_PG_DUMP_PREFIX = "codefreedom-pgdump"


def _find_litellm_container() -> Optional[str]:
    """Find the running LiteLLM proxy container name.

    Uses ``docker ps`` filtered by the ``codefreedom.component=litellm-proxy``
    label set in docker-compose.yaml. Returns ``None`` if no container is
    running (non-fatal — the backup continues without a PG dump).

    Returns:
        The container name string, or None.
    """
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
        # Take the first running container
        return result.stdout.strip().splitlines()[0]
    except (OSError, subprocess.TimeoutExpired):
        return None


def _dump_postgresql(pg_backup_dir: Path) -> Optional[Path]:
    """Dump the embedded PostgreSQL database from the running LiteLLM container.

    Runs ``pg_dump`` (custom format, compressed) inside the container and
    writes the dump to the bind-mounted backup directory (``pg/backup/``).
    The dump is named ``codefreedom-pgdump-<timestamp>.dump``.

    This is a best-effort operation — if the container isn't running or
    ``pg_dump`` fails, a warning is printed and the backup continues.

    Args:
        pg_backup_dir: The host directory where PG dumps are written
            (``~/.codefreedom/pg/backup/``, bind-mounted into the container).

    Returns:
        The path to the created dump file, or None on failure.
    """
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
                "-Fc",  # custom format (compressed, parallel-restore capable)
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
        if dump_path.exists():
            size = dump_path.stat().st_size
            eprint(
                f"[ADMIN] PostgreSQL dump created: {dump_filename}"
                f" ({_fmt_size_pg(size)})."
            )
            return dump_path

        eprint(
            f"[ADMIN] Warning: pg_dump completed but dump file not found at {dump_path}."
        )
        return None

    except (OSError, subprocess.TimeoutExpired) as exc:
        eprint(f"[ADMIN] Warning: could not dump PostgreSQL: {exc}.")
        return None


def _fmt_size_pg(size: int) -> str:
    """Format a byte count as a human-readable string (local helper)."""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / (1024 * 1024 * 1024):.1f} GB"


# ── Naming ────────────────────────────────────────────────────────────────────


def _sanitize(name: str) -> str:
    """Remove any characters that are not alphanumeric, hyphen, underscore, or dot."""
    return re.sub(r"[^a-zA-Z0-9._-]", "_", name)


def _backup_filename(profile: str) -> str:
    """Generate a backup filename in standard format.

    Example: codefreedom-backup-default-20260604-143022-my-workstation.tar.gz
    """
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
    """Parse a backup filename into its components.

    Returns a dict with keys: profile, created_at, hostname.
    Returns empty/unknown values if parsing fails.
    """
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
    """Build a BackupManifest from collected file entries."""
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
    """Serialize a BackupManifest to a JSON-serializable dict."""
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
    """Deserialize a dict back to a BackupManifest."""
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


# ── Backup ────────────────────────────────────────────────────────────────────


def backup(
    output_path: Optional[Path] = None,
    profile: str = "default",
    passphrase: Optional[str] = None,
    redact_secrets: Optional[bool] = None,
    skip_pg_dump: bool = False,
) -> Tuple[Path, BackupManifest]:
    """Backup the CodeFreedom home directory to a ``.tar.gz`` archive.

    Only backs up managed files (``profiles/``, ``proxy/``, ``pg/``, ``.env.*``).
    If the LiteLLM proxy is running, the embedded PostgreSQL database is
    automatically dumped (``pg_dump -Fc``) into ``pg/backup/`` before the
    archive is created. Use ``skip_pg_dump=True`` to disable this.

    When *passphrase* is provided, secrets are stored with full values
    and the archive is encrypted with AES-256-GCM. Without a passphrase,
    secrets are redacted and the archive is unencrypted.

    To create an unencrypted backup with full secret values (e.g. for
    pre-apply rollback snapshots), set ``redact_secrets=False``.

    Args:
        output_path: Target file path.
        profile: Profile label stored in manifest and filename.
        passphrase: If set, encrypt the archive and skip secret redaction.
        redact_secrets: Explicit override.  Defaults to ``True`` when
            *passphrase* is unset, ``False`` when set.
        skip_pg_dump: If True, skip the PostgreSQL dump even if the
            LiteLLM container is running.

    Returns:
        Tuple of (output_path, manifest).

    Raises:
        FileNotFoundError: If the CodeFreedom home directory does not exist.
        RuntimeError: If *passphrase* is set but cryptography is not installed.
    """
    if passphrase and not _HAS_CRYPTOGRAPHY:
        raise RuntimeError(
            "Encryption requires the 'cryptography' package.\n"
            "  Install: pip install codefreedom[encrypt]"
        )

    encrypting = bool(passphrase)
    source_dir = get_codefreedom_dir()
    if not source_dir.exists():
        raise FileNotFoundError(f"CodeFreedom home directory not found: {source_dir}")

    # Determine redaction: explicit override wins, else default
    should_redact = redact_secrets if redact_secrets is not None else not encrypting

    # Dump PostgreSQL before collecting files (best-effort, non-fatal)
    if not skip_pg_dump:
        pg_backup_dir = get_codefreedom_dir() / "pg" / "backup"
        _dump_postgresql(pg_backup_dir)

    # Collect files
    contents, categories = _collect_files(source_dir, redact_secrets=should_redact)

    # Build manifest
    manifest = _build_manifest(
        contents, categories, profile, secrets_redacted=should_redact
    )

    # Resolve output path
    if output_path is None:
        backup_dir = get_backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)
        output_path = backup_dir / _backup_filename(profile)

    # Write archive
    _write_archive(output_path, source_dir, manifest, passphrase=passphrase)

    return output_path, manifest


def _write_archive(
    archive_path: Path,
    source_dir: Path,
    manifest: BackupManifest,
    passphrase: Optional[str] = None,
) -> None:
    """Write the tar.gz archive, optionally encrypting with *passphrase*."""
    manifest_dict = _manifest_to_dict(manifest)
    manifest_bytes = json.dumps(manifest_dict, indent=2, sort_keys=True).encode("utf-8")

    # Use a BytesIO buffer so we can write tar entries in memory
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        # Write manifest first (fast extraction with tar tzf)
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(manifest_bytes)
        info.mtime = int(time.time())
        tar.addfile(info, io.BytesIO(manifest_bytes))

        # Write all collected files
        for _cat, entries in manifest.contents.items():
            for entry in entries:
                # Redacted files: write the in-memory redacted content
                if entry.redacted and entry.redacted_content is not None:
                    t_info = tarfile.TarInfo(name=entry.path)
                    t_info.size = len(entry.redacted_content)
                    t_info.mtime = int(time.time())
                    t_info.mode = entry.mode
                    tar.addfile(t_info, io.BytesIO(entry.redacted_content))
                else:
                    # Normal files: read from disk
                    full_path = source_dir / entry.path
                    try:
                        tar.add(str(full_path), arcname=entry.path)
                    except OSError:
                        continue

    archive_data = buf.getvalue()

    # Encrypt if passphrase provided
    if passphrase:
        archive_data = _encrypt_data(archive_data, passphrase)

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_bytes(archive_data)


# ── List backups ──────────────────────────────────────────────────────────────


def list_backups(backup_dir: Optional[Path] = None) -> List[BackupSummary]:
    """List all backups found in *backup_dir*.

    Args:
        backup_dir: Directory to scan. Defaults to ``~/.codefreedom/backup/``.

    Returns:
        List of BackupSummary sorted by creation date (newest first).
    """
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
            # Encrypted backup — parse what we can from the filename
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

    # Sort newest first
    summaries.sort(key=lambda s: s.created_at, reverse=True)
    return summaries


def _read_archive_bytes(path: Path, passphrase: Optional[str] = None) -> bytes:
    """Read *path*, decrypting if it starts with the encryption magic."""
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
    """Read and parse the manifest from an existing backup archive.

    Handles both encrypted and unencrypted archives.
    """
    data_bytes = _read_archive_bytes(archive_path, passphrase=passphrase)
    with tarfile.open(fileobj=io.BytesIO(data_bytes), mode="r:gz") as tar:
        member = tar.getmember("manifest.json")
        f = tar.extractfile(member)
        if f is None:
            raise ValueError("manifest.json is empty in archive")
        data = json.loads(f.read().decode("utf-8"))
    return _manifest_from_dict(data)


# ── Inspect ───────────────────────────────────────────────────────────────────


def inspect_backup(
    archive_path: Path,
    passphrase: Optional[str] = None,
) -> BackupManifest:
    """Read and return the manifest from *archive_path*.

    Args:
        archive_path: Path to the backup archive.
        passphrase: Passphrase for encrypted backups.

    Raises:
        FileNotFoundError: If *archive_path* does not exist.
        ValueError: If the archive is invalid or requires a passphrase.
    """
    if not archive_path.exists():
        raise FileNotFoundError(f"Backup file not found: {archive_path}")
    return _read_manifest_from_archive(archive_path, passphrase=passphrase)


# ── Prune ─────────────────────────────────────────────────────────────────────


@dataclass
class PruneResult:
    """Result of a prune operation."""

    deleted: List[Path]
    kept: List[Path]
    space_reclaimed: int


def prune_backups(
    keep: Optional[int] = None,
    older_than: Optional[datetime.timedelta] = None,
    backup_dir: Optional[Path] = None,
) -> PruneResult:
    """Prune old backups from *backup_dir*.

    Args:
        keep: Keep this many most recent backups, delete the rest.
        older_than: Delete backups older than this duration.
        backup_dir: Directory to scan. Defaults to ``~/.codefreedom/backup/``.

    Returns:
        PruneResult describing what was done.
    """
    if backup_dir is None:
        backup_dir = get_backup_dir()

    if not backup_dir.exists():
        return PruneResult(deleted=[], kept=[], space_reclaimed=0)

    all_backups = sorted(backup_dir.glob("*.tar.gz"))
    to_delete: set[Path] = set()
    now = datetime.datetime.now(datetime.timezone.utc)

    # Apply --older-than
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
                # Can't parse? skip from older_than deletion
                if isinstance(exc, ValueError) and "passphrase" in str(exc).lower():
                    eprint(
                        f"[ADMIN] Warning: cannot evaluate encrypted backup: {p.name}."
                    )
                continue

    # Apply --keep (after older_than, so --keep always wins)
    if keep is not None and keep > 0:
        remaining = [p for p in all_backups if p not in to_delete]
        # Keep the N most recent (by filename sort = chronological)
        remaining_sorted = sorted(remaining)
        to_delete.update(
            remaining_sorted[:-keep] if len(remaining_sorted) > keep else []
        )

    # Safety: never delete the only remaining backup
    after_delete = [p for p in all_backups if p not in to_delete]
    if not after_delete and len(all_backups) > 0 and len(to_delete) == len(all_backups):
        # Keep the most recent
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


# ── Restore ───────────────────────────────────────────────────────────────────


def _compute_diff(manifest: BackupManifest, target_dir: Path) -> List[FileDiff]:
    """Compare manifest file entries against current state on disk.

    Returns a list of FileDiff entries sorted by status then path.
    """
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

    # Sort: ADD, then MOD, then OK
    status_order = {"ADD": 0, "MOD": 1, "OK": 2}
    diffs.sort(key=lambda d: (status_order.get(d.status, 9), d.rel_path))
    return diffs


def restore(
    archive_path: Path,
    target_dir: Optional[Path] = None,
    dry_run: bool = False,
    passphrase: Optional[str] = None,
) -> Tuple[List[FileDiff], BackupManifest]:
    """Restore files from *archive_path* to *target_dir*.

    Args:
        archive_path: Path to the backup archive (may be encrypted).
        target_dir: Directory to restore into. Defaults to
            ``get_codefreedom_dir()``.
        dry_run: If True, compute diff but do not write files.
        passphrase: Passphrase for encrypted backups.

    Returns:
        Tuple of (list of FileDiff, manifest).

    Raises:
        FileNotFoundError: If *archive_path* does not exist.
        ValueError: If the archive has an incompatible schema version
            or requires a passphrase.
    """
    if not archive_path.exists():
        raise FileNotFoundError(f"Backup file not found: {archive_path}")

    if target_dir is None:
        target_dir = get_codefreedom_dir()

    manifest = _read_manifest_from_archive(archive_path, passphrase=passphrase)

    # Schema version check
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
