"""Related git paths: validation, parsing, container subpath assignment.

The main project and any number of related git repos are mounted into
the same container. Each related path becomes a sub-project in the
container's cache, queryable via the MCP ``search_graph(project=...)``
parameter.

Validation rules
----------------

- The path must exist on disk.
- The path must be a git repository (``git rev-parse --show-toplevel``
  returns the same path or a parent of it).
- The path must not be a subdirectory of the main project (use git
  submodules for that, or include the relevant files in the main index).
- Paths whose basename collides with the main project's basename are
  mounted at ``/workspace/<basename>-1`` etc.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from codebase_memory import project_id


class RelatedPathError(ValueError):
    """Raised when a related path is invalid (missing, non-git, subdir)."""


def validate_related_paths(main_root: Path, paths: Iterable[dict]) -> list[dict]:
    """Validate a list of related-path entries against the main project.

    Each entry must have at least a ``path`` key. Optional ``alias``.
    Returns a normalized list of dicts with ``path`` (absolute) and
    optional ``alias`` (str). Raises :class:`RelatedPathError` on any
    validation failure.
    """
    main_resolved = main_root.resolve()
    out: list[dict] = []
    seen: set[str] = set()

    for entry in paths:
        if not isinstance(entry, dict):
            raise RelatedPathError(f"related_paths entry must be a mapping, got {type(entry).__name__}")
        raw_path = entry.get("path")
        if not raw_path or not isinstance(raw_path, str):
            raise RelatedPathError(f"related_paths entry missing 'path': {entry!r}")
        resolved = Path(raw_path).expanduser().resolve()

        if not resolved.exists():
            raise RelatedPathError(f"related path does not exist: {resolved}")
        if not resolved.is_dir():
            raise RelatedPathError(f"related path is not a directory: {resolved}")
        if _is_subdir(resolved, main_resolved):
            raise RelatedPathError(
                f"related path is a subdirectory of the main project: {resolved}"
            )
        if not _is_git_repo(resolved):
            raise RelatedPathError(f"related path is not a git repository: {resolved}")

        key = str(resolved)
        if key in seen:
            raise RelatedPathError(f"duplicate related path: {resolved}")
        seen.add(key)

        normalized: dict = {"path": str(resolved)}
        alias = entry.get("alias") or ""
        if alias is not None:
            normalized["alias"] = str(alias).strip()
        out.append(normalized)

    return out


def container_subpaths(main_root: Path, related: list[dict]) -> list[tuple[str, str]]:
    """Return ``[(host_path, container_subpath), ...]`` for related paths.

    The container subpath is ``/workspace/<basename>`` for each related
    path, with ``-1``, ``-2`` suffixes on basename collisions. The main
    project is mounted at ``/workspace/<id>`` separately and is not
    returned here.
    """
    used: set[str] = {f"/workspace/{main_root.name}"}
    out: list[tuple[str, str]] = []
    for entry in related:
        host = entry["path"]
        sub = project_id.container_subpath_for(host, used)
        out.append((host, sub))
    return out


# ── Internal helpers ──────────────────────────────────────────────────────


def _is_subdir(child: Path, parent: Path) -> bool:
    """True if ``child`` is the same as or inside ``parent``."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _is_git_repo(directory: Path) -> bool:
    """True if ``directory`` (or any parent) is a git toplevel."""
    if shutil.which("git") is None:
        # Without git we can't tell; be permissive so a missing git
        # binary doesn't break validation when the user clearly intends
        # to add the path. The container won't be able to index it
        # without git, but the mount itself will succeed.
        return (directory / ".git").exists()
    try:
        result = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    if result.returncode != 0:
        return False
    toplevel = result.stdout.strip()
    if not toplevel:
        return False
    try:
        Path(toplevel).resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        # Not the toplevel but inside one — that's also fine.
        return bool((directory / ".git").exists() or any((p / ".git").exists() for p in directory.resolve().parents))
