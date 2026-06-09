"""Admin subcommand -- backup, restore, list, inspect, and prune CodeFreedom config.

Usage:
    codefreedom admin backup                        Default backup location
    codefreedom admin backup --out PATH             Explicit output path
    codefreedom admin restore --in PATH             Interactive restore with diff preview
    codefreedom admin restore --in PATH --dry-run   Diff preview only
    codefreedom admin restore --in PATH --force     Skip confirmation
    codefreedom admin list-backups                  List all backups
    codefreedom admin inspect PATH                  Inspect a backup archive
    codefreedom admin prune --keep N                Keep N most recent
    codefreedom admin prune --older-than 30d        Delete older than duration
"""

from __future__ import annotations

import argparse
import datetime
import re
from pathlib import Path
from typing import List, Optional

from codefreedom.admin import (
    BackupSummary,
    FileDiff,
    backup as engine_backup,
    inspect_backup,
    list_backups as engine_list_backups,
    prune_backups as engine_prune,
    restore as engine_restore,
)
from codefreedom.env_loader import eprint

# ── Arg parser ────────────────────────────────────────────────────────────────


def build_parser(parser: argparse.ArgumentParser) -> None:
    """Add admin sub-subcommands (backup, restore, ...) to *parser*."""
    admin_sub = parser.add_subparsers(dest="action", title="actions", required=True)

    # ── backup ──────────────────────────────────────────────────────────
    bak = admin_sub.add_parser(
        "backup",
        help="Create a backup archive of managed config files",
        description=(
            "Archive managed CodeFreedom config files (profiles, proxy, pg, .env). "
            "If the LiteLLM proxy is running, the embedded PostgreSQL database is "
            "automatically dumped before archiving. Secrets are redacted by default. "
            "Use --passphrase to encrypt the archive with full secret values "
            "(requires codefreedom[encrypt])."
        ),
    )
    bak.add_argument(
        "--out",
        type=str,
        default=None,
        metavar="PATH",
        help="Output path for the backup archive (default: ~/.codefreedom/backup/)",
    )
    bak.add_argument(
        "--profile",
        type=str,
        default="default",
        metavar="NAME",
        help="Profile label stored in manifest and filename (default: 'default')",
    )
    bak.add_argument(
        "--passphrase",
        type=str,
        default=None,
        metavar="PASSPHRASE",
        help="Encrypt the archive with this passphrase. Secrets are stored with full values.",
    )
    bak.add_argument(
        "--skip-pg-dump",
        action="store_true",
        default=False,
        help="Skip the automatic PostgreSQL dump from the running LiteLLM proxy",
    )

    # ── restore ─────────────────────────────────────────────────────────
    rst = admin_sub.add_parser(
        "restore",
        help="Restore configuration from a backup archive",
        description=(
            "Restore files from a backup archive. Shows a diff preview before "
            "making changes, then prompts for confirmation (skip with --force or "
            "--dry-run). Use --passphrase to decrypt encrypted backups."
        ),
    )
    rst.add_argument(
        "backup_file",
        type=str,
        metavar="BACKUP_FILE",
        help="Path to the backup archive (.tar.gz)",
    )
    rst.add_argument(
        "--dry-run",
        action="store_true",
        help="Show diff preview without making changes",
    )
    rst.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt",
    )
    rst.add_argument(
        "--passphrase",
        type=str,
        default=None,
        metavar="PASSPHRASE",
        help="Passphrase to decrypt the backup archive",
    )

    # ── list-backups ────────────────────────────────────────────────────
    admin_sub.add_parser(
        "list-backups",
        aliases=["ls"],
        help="List all available backups (alias: ls)",
        description="List all backups in the default backup directory (~/.codefreedom/backup/).",
    )

    # ── inspect ─────────────────────────────────────────────────────────
    ins = admin_sub.add_parser(
        "inspect",
        help="Show manifest of a backup archive",
        description=(
            "Display the full manifest of a backup archive without extracting. "
            "Use --passphrase to inspect encrypted backups."
        ),
    )
    ins.add_argument(
        "path",
        type=str,
        help="Path to the backup archive (.tar.gz)",
    )
    ins.add_argument(
        "--passphrase",
        type=str,
        default=None,
        metavar="PASSPHRASE",
        help="Passphrase for encrypted backups",
    )

    # ── prune ───────────────────────────────────────────────────────────
    prn = admin_sub.add_parser(
        "prune",
        help="Remove old backups (never deletes the last backup)",
        description=(
            "Remove old backups by count (--keep N) or age (--older-than DURATION). "
            "Both filters can be combined. Safety: never deletes the last remaining backup."
        ),
    )
    prn.add_argument(
        "--keep",
        type=int,
        default=None,
        metavar="N",
        help="Keep the N most recent backups, delete the rest",
    )
    prn.add_argument(
        "--older-than",
        type=str,
        default=None,
        metavar="DURATION",
        help='Delete backups older than this duration (e.g. "30d", "6m", "12h", "2w"). Suffixes: s, m, h, d, w.',
    )


# ── Duration parsing ──────────────────────────────────────────────────────────


def _parse_duration(text: str) -> datetime.timedelta:
    """Parse a human-readable duration string.

    Supported suffixes: s (seconds), m (minutes), h (hours), d (days), w (weeks).
    """
    match = re.match(r"^(\d+)\s*([smhdw])$", text.strip())
    if not match:
        raise ValueError(
            f"Invalid duration: {text!r}. Use a number followed by a unit: s (seconds), m (minutes), h (hours), d (days), w (weeks)."
        )
    value = int(match.group(1))
    unit = match.group(2)
    mapping = {
        "s": "seconds",
        "m": "minutes",
        "h": "hours",
        "d": "days",
        "w": "weeks",
    }
    return datetime.timedelta(**{mapping[unit]: value})


# ── Output formatting ────────────────────────────────────────────────────────


def _fmt_size(size: int) -> str:
    """Format a byte count as a human-readable string."""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / (1024 * 1024 * 1024):.1f} GB"


def _print_backup_result(path: Path, manifest) -> None:
    """Print a summary after a successful backup."""
    total_files = sum(len(e) for e in manifest.contents.values())
    total_size = sum(c.total_size for c in manifest.categories.values())

    print(f"[backup] Created: {path}")
    print(f"[backup] Total files: {total_files} ({_fmt_size(total_size)})")
    print(f"[backup] Created at: {manifest.created_at}")
    if manifest.secrets_redacted:
        print("[backup] Secrets: redacted (keys preserved, values masked)")
    else:
        print("[backup] Secrets: included (full values, archive is encrypted)")
    print()
    print(f"  {'Category':<14} {'Files':>6} {'Size':>10}")
    print(f"  {'-'*14} {'-'*6} {'-'*10}")
    for cat in sorted(manifest.categories.keys()):
        c = manifest.categories[cat]
        print(f"  {cat:<14} {c.count:>6} {_fmt_size(c.total_size):>10}")
    print()


def _print_diff_table(diffs: List[FileDiff]) -> None:
    """Print a formatted diff table."""
    if not diffs:
        print("  No files to restore.")
        return

    # Compute column widths
    max_path = max(len(d.rel_path) for d in diffs)
    path_width = max(max_path, 30)
    path_width = min(path_width, 80)

    sep = "-" * (8 + path_width + 12 + 12)
    print(f"  {'Status':<8} {'Path':<{path_width}} {'Size':>10} {'Action':<12}")
    print(f"  {'-'*8} {'-'*path_width} {'-'*10} {'-'*12}")

    add_count = 0
    mod_count = 0
    ok_count = 0

    for d in diffs:
        action = ""
        if d.status == "ADD":
            action = "New file"
            add_count += 1
        elif d.status == "MOD":
            action = "SHA256 differs"
            mod_count += 1
        elif d.status == "OK":
            action = "Unchanged"
            ok_count += 1
        elif d.status == "SKIP":
            action = "Excluded"

        print(
            f"  [{d.status:<4}] {d.rel_path:<{path_width}}"
            f" {_fmt_size(d.backup_size):>10}  {action:<12}"
        )

    print(f"  {sep}")
    print(f"  Summary: {add_count} to add, {mod_count} to modify, {ok_count} unchanged")


def _print_list_backups(summaries: List[BackupSummary]) -> None:
    """Print a table of backup summaries."""
    if not summaries:
        print("  No backups found.")
        return

    print(
        f"  {'Date':<22} {'Profile':<14} {'Hostname':<20} {'Files':>6} {'Size':>10} {'Secrets':<8}"
    )
    print(f"  {'-'*22} {'-'*14} {'-'*20} {'-'*6} {'-'*10} {'-'*8}")

    for s in summaries:
        if s.secrets_redacted:
            secrets_str = "redacted"
        elif s.total_files == 0:
            secrets_str = "encrypted"
        else:
            secrets_str = "included"
        print(
            f"  {s.created_at:<22} {s.profile:<14} {s.hostname:<20}"
            f" {s.total_files:>6} {_fmt_size(s.total_size):>10} {secrets_str:<8}"
        )


def _print_inspect(manifest) -> None:
    """Print full manifest details."""
    total_files = sum(len(e) for e in manifest.contents.values())
    total_size = sum(c.total_size for c in manifest.categories.values())

    print(f"  Schema version: {manifest.schema_version}")
    print(f"  Tool version:   {manifest.tool_version}")
    print(f"  Created at:     {manifest.created_at}")
    print(f"  Hostname:       {manifest.hostname}")
    print(f"  Platform:       {manifest.platform}")
    print(f"  Profile:        {manifest.profile}")
    print(
        f"  Secrets:        {'redacted' if manifest.secrets_redacted else 'included'}"
    )
    print(f"  Total files:    {total_files} ({_fmt_size(total_size)})")
    print()

    for cat in sorted(manifest.categories.keys()):
        c = manifest.categories[cat]
        entries = manifest.contents.get(cat, [])
        print(f"  [{cat}] ({c.count} files, {_fmt_size(c.total_size)})")
        for e in entries:
            print(f"    {e.path}  ({_fmt_size(e.size)}, sha256:{e.sha256[:12]}...)")
        print()


def _print_prune_result(result) -> None:
    """Print the result of a prune operation."""
    if not result.deleted:
        print("[prune] Nothing to delete.")
    else:
        print(
            f"[prune] Deleted {len(result.deleted)} backup(s) ({_fmt_size(result.space_reclaimed)})"
        )
        for p in result.deleted:
            print(f"  [DELETE] {p.name}")

    if result.kept:
        print(f"[prune] Kept {len(result.kept)} backup(s)")
        for p in result.kept:
            print(f"  [KEEP] {p.name}")


# ── Entry point ───────────────────────────────────────────────────────────────


def run(args: argparse.Namespace) -> int:
    """Execute the admin subcommand. Returns exit code."""
    action = args.action

    try:
        if action == "backup":
            return _cmd_backup(args)
        elif action == "restore":
            return _cmd_restore(args)
        elif action in ("list-backups", "ls"):
            return _cmd_list_backups()
        elif action == "inspect":
            return _cmd_inspect(args)
        elif action == "prune":
            return _cmd_prune(args)
        else:
            eprint(f"[admin] Unknown action: {action}")
            return 1
    except (FileNotFoundError, ValueError) as exc:
        eprint(f"[ERROR] {exc}")
        return 1


# ── Command implementations ───────────────────────────────────────────────────


def _cmd_backup(args: argparse.Namespace) -> int:
    """Execute 'admin backup'."""
    out_path = Path(args.out) if args.out else None
    result_path, manifest = engine_backup(
        output_path=out_path,
        profile=args.profile,
        passphrase=args.passphrase,
        skip_pg_dump=args.skip_pg_dump,
    )
    _print_backup_result(result_path, manifest)
    return 0


def _cmd_restore(args: argparse.Namespace) -> int:
    """Execute 'admin restore'."""
    archive_path = Path(args.backup_file)

    if not archive_path.exists():
        eprint(f"[ERROR] Backup file not found: {archive_path}")
        return 1

    diffs, manifest = engine_restore(
        archive_path=archive_path,
        dry_run=True,  # Always diff first
        passphrase=args.passphrase,
    )

    # Print header
    print(f"[restore] Backup: {archive_path.name}")
    print(f"[restore] Created: {manifest.created_at} on {manifest.hostname}")
    if manifest.platform != __import__("sys").platform:
        print(
            f"[restore] Warning: backup platform ({manifest.platform}) differs"
            f" from current platform ({__import__('sys').platform})"
        )
    if manifest.secrets_redacted:
        print("[restore] Note: Secrets were backed up with redacted values.")
    print()

    _print_diff_table(diffs)

    if args.dry_run:
        print()
        print("[restore] Dry-run complete. No files were changed.")
        return 0

    # Count actionable diffs
    actionable = [d for d in diffs if d.status in ("ADD", "MOD")]
    if not actionable:
        print()
        print("[restore] Nothing to restore. All files are already current.")
        return 0

    if args.force:
        do_restore = True
    else:
        try:
            response = input(f"\nRestore {len(actionable)} file(s)? [y/N] ")
            do_restore = response.strip().lower() in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            do_restore = False

    if not do_restore:
        print("[restore] Cancelled.")
        return 0

    # Perform actual restore
    diffs, _manifest = engine_restore(
        archive_path=archive_path,
        dry_run=False,
        passphrase=args.passphrase,
    )
    add_count = sum(1 for d in diffs if d.status == "ADD")
    mod_count = sum(1 for d in diffs if d.status == "MOD")
    print(f"[restore] Done. {add_count} added, {mod_count} modified.")
    return 0


def _cmd_list_backups() -> int:
    """Execute 'admin list-backups'."""
    summaries = engine_list_backups()
    _print_list_backups(summaries)
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    """Execute 'admin inspect'."""
    path = Path(args.path)
    manifest = inspect_backup(path, passphrase=args.passphrase)
    _print_inspect(manifest)
    return 0


def _cmd_prune(args: argparse.Namespace) -> int:
    """Execute 'admin prune'."""
    keep = args.keep
    older_than_str = args.older_than

    if keep is None and older_than_str is None:
        eprint(
            "[ERROR] Specify --keep N or --older-than DURATION" " (or both) for prune."
        )
        return 1

    older_than: Optional[datetime.timedelta] = None
    if older_than_str:
        try:
            older_than = _parse_duration(older_than_str)
        except ValueError as exc:
            eprint(f"[ERROR] {exc}")
            return 1

    result = engine_prune(keep=keep, older_than=older_than)
    _print_prune_result(result)
    return 0
