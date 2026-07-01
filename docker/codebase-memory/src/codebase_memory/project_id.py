"""Project ID derivation and collision handling.

The project ID is the sanitized basename of the git toplevel directory.
We lowercase and replace non-alphanumeric characters with ``-`` so the ID
is safe to use in container names, file paths, and DNS labels.

Two different git repos can have the same basename (e.g. ``~/code/proj``
and ``~/work/proj`` both have basename ``proj``). The disambiguator
appends ``-1``, ``-2``, … to the container name and cache directory for
later occurrences while keeping the manifest's ``id`` field at the bare
sanitized name. The user can also set a custom alias in the manifest.
"""
from __future__ import annotations

import re
from pathlib import Path


_SANITIZE_RE = re.compile(r"[^a-z0-9-]+")
_DUPLICATE_DASHES_RE = re.compile(r"-+")
_EDGE_DASHES_RE = re.compile(r"^-+|-+$")


def sanitize_basename(path: str | Path) -> str:
    """Return a safe ID derived from the basename of ``path``.

    Examples:

        >>> sanitize_basename("/home/user/proj-A")
        'proj-a'
        >>> sanitize_basename("/home/u/client.name")
        'client-name'
        >>> sanitize_basename("/srv/v2.api")
        'v2-api'
        >>> sanitize_basename("/")
        'root'
    """
    name = Path(path).name
    if not name:
        return "root"
    lowered = name.lower()
    replaced = _SANITIZE_RE.sub("-", lowered)
    deduped = _DUPLICATE_DASHES_RE.sub("-", replaced)
    trimmed = _EDGE_DASHES_RE.sub("", deduped)
    return trimmed or "root"


def container_name_for(project_id: str, used: set[str] | None = None) -> str:
    """Return a unique container name for ``project_id``.

    The base name is ``codefreedom-tools-codebase-memory-<id>``. If that
    name is already in ``used``, ``-1``, ``-2``, … are appended until a
    free name is found. The chosen name is added to ``used`` in-place
    so callers can keep a running set across multiple calls.
    """
    if used is None:
        used = set()
    base = f"codefreedom-tools-codebase-memory-{project_id}"
    candidate = base
    suffix = 1
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def container_subpath_for(host_path: str | Path, used: set[str] | None = None) -> str:
    """Return a non-colliding ``/workspace/<basename>`` path.

    Used for both the main project mount and each related path. The
    main project is always mounted at ``/workspace/<id>`` where ``id``
    is the sanitized basename; related paths use the path's basename
    with ``-1``, ``-2`` suffixes on collision.
    """
    if used is None:
        used = set()
    base = Path(host_path).name or "root"
    candidate = f"/workspace/{base}"
    suffix = 1
    while candidate in used:
        candidate = f"/workspace/{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate
