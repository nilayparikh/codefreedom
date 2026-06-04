"""Shared initialization utilities for CLI modules.

Extracts the all-or-nothing copy pattern and _find_bundled_examples()
that were duplicated across claude.py, proxy.py, chrome.py, and web.py.
"""

from __future__ import annotations

import shutil
from pathlib import Path


def find_bundled_examples(caller_file: str) -> Path:
    """Find the bundled examples directory inside the installed package.

    Args:
        caller_file: Pass ``__file__`` from the calling module so the
            path resolves relative to the caller's location.
    """
    return Path(caller_file).resolve().parent.parent / "examples"


def copy_bundled_files(
    src_dir: Path,
    dst_dir: Path,
    *,
    label: str = "init",
    docs_url: str = "",
    examples_url: str = "",
) -> list[str]:
    """Copy all files from src_dir to dst_dir — all-or-nothing.

    If any target file already exists, the entire operation is skipped
    and the user is directed to docs / example configs for manual merging.

    Returns a list of created file paths (as strings), or empty if skipped.
    """
    # Collect all source→destination pairs
    pairs: list[tuple[Path, Path]] = []
    for src in sorted(src_dir.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(src_dir)
        dst = dst_dir / rel
        pairs.append((src, dst))

    # All-or-nothing check: if any destination file exists, skip everything
    existing = [dst for _, dst in pairs if dst.exists()]
    if existing:
        print(
            f"[{label}] Config already exists -- init only bootstraps clean directories."
        )
        if docs_url:
            print(f"          Docs:    {docs_url}")
        if examples_url:
            print(f"          Example: {examples_url}")
        print("          Please merge changes manually.")
        return []

    # Nothing exists -- copy all, with rollback on failure
    created: list[Path] = []
    try:
        for src, dst in pairs:
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                created.append(dst)
                print(f"[{label}] [CREATE] {dst}")
            else:
                print(f"[{label}] [MISSING] Source not found: {src}")
    except OSError as exc:
        import sys
        print(f"[{label}] [ERROR] Copy failed: {exc}. Rolling back.", file=sys.stderr)
        for path in created:
            try:
                path.unlink()
            except OSError:
                pass
        raise
    return [str(p) for p in created]
