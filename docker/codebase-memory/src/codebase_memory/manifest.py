"""Per-workspace manifest: load, save, init, defaults.

The manifest is a user-editable YAML file at
``<project_root>/.codefreedom/codebase-memory.yaml``. We deliberately
do not use a Pydantic schema: the user owns this file, the loader is
permissive (missing fields get defaults, unknown fields are preserved on
round-trip), and we never refuse to start a container because the YAML
has an extra comment or section.

The manifest is the only state. There is no central registry, no
filesystem scanning, and no migration from a prior format.
"""
from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path
from typing import Any

import yaml

from codebase_memory import project_id


_MANIFEST_VERSION = 1
_MANIFEST_DIRNAME = ".codefreedom"
_MANIFEST_FILENAME = "codebase-memory.yaml"


# ── Defaults ───────────────────────────────────────────────────────────────

DEFAULTS: dict[str, Any] = {
    "version": _MANIFEST_VERSION,
    "image": "docker.io/nilayparikh/codefreedom:codebase-memory-v1.0.0",
    "remote_url": "",
    "env": {},
    "related_paths": [],
    "memory_mb": 1024,
    "shm_size_mb": 512,
    "auto_start": True,
    "auto_open_ui": True,
    "created_at": "",
    "last_used_at": "",
    "id": "",
    "path": "",
    "container_name": "",
    "mcp_port": 0,
    "ui_port": 0,
}


# ── Public surface ────────────────────────────────────────────────────────


def manifest_path(project_root: Path) -> Path:
    """Return the absolute manifest path for a project root."""
    return project_root / _MANIFEST_DIRNAME / _MANIFEST_FILENAME


def exists(project_root: Path) -> bool:
    """True if a manifest already exists for this project."""
    return manifest_path(project_root).is_file()


def init_defaults(project_root: Path) -> dict[str, Any]:
    """Build an in-memory manifest for a project that has no file yet.

    The returned dict can be passed straight to :func:`save` to create
    the on-disk file. Field values reflect the project (id derived from
    the basename, timestamps set to now, no ports yet — ports are
    allocated by the manager on first start).
    """
    pid = project_id.sanitize_basename(project_root)
    now = _now_iso()
    data: dict[str, Any] = {
        "version": _MANIFEST_VERSION,
        "id": pid,
        "path": "",
        "container_name": "",
        "image": DEFAULTS["image"],
        "created_at": now,
        "last_used_at": now,
        "remote_url": DEFAULTS["remote_url"],
        "env": dict(DEFAULTS["env"]),
        "related_paths": list(DEFAULTS["related_paths"]),
        "memory_mb": DEFAULTS["memory_mb"],
        "shm_size_mb": DEFAULTS["shm_size_mb"],
        "auto_start": DEFAULTS["auto_start"],
        "auto_open_ui": DEFAULTS["auto_open_ui"],
        "mcp_port": 0,
        "ui_port": 0,
    }
    return data


def load(project_root: Path) -> dict[str, Any]:
    """Load the manifest, filling missing fields with defaults.

    Unknown fields are preserved as-is. The returned dict is a fresh
    copy; mutating it does not touch the on-disk file.
    """
    path = manifest_path(project_root)
    if not path.is_file():
        return init_defaults(project_root)
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except yaml.YAMLError:
        # Corrupt file: fall back to defaults. The user can fix it
        # by editing or by ``cf r tl cbmem reset``.
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    return _merge_with_defaults(raw)


def save(project_root: Path, data: dict[str, Any]) -> None:
    """Persist ``data`` to the manifest, creating parent dirs.

    Existing user fields that are not in ``data`` are preserved; only
    keys present in ``data`` overwrite. This keeps the on-disk file
    stable across partial updates (e.g. recording ``last_used_at``).
    """
    path = manifest_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = {}
    if path.is_file():
        with open(path, encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        if isinstance(loaded, dict):
            existing = loaded

    merged = {**existing, **data}
    text = yaml.safe_dump(merged, sort_keys=False, default_flow_style=False)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

    _ensure_gitignore(project_root)


def update_last_used(project_root: Path) -> None:
    """Stamp ``last_used_at`` to now. Silently no-ops if no manifest."""
    if not exists(project_root):
        return
    save(project_root, {"last_used_at": _now_iso()})


# ── Internal helpers ──────────────────────────────────────────────────────


def _merge_with_defaults(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(DEFAULTS)
    for key, value in raw.items():
        out[key] = value
    out["id"] = project_id.sanitize_basename(raw.get("id") or raw.get("path_basename") or "root")
    return out


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_gitignore(project_root: Path) -> None:
    """Append ``.codefreedom/`` to ``.gitignore`` if not present.

    Idempotent. We don't create the file or add other entries. A leading
    newline is inserted before the entry if the file doesn't end with
    one, so the appended line is on its own line.
    """
    gitignore = project_root / ".gitignore"
    entry = f"{_MANIFEST_DIRNAME}/"

    existing = ""
    if gitignore.is_file():
        with open(gitignore, encoding="utf-8") as f:
            existing = f.read()

    if _gitignore_has_entry(existing, entry):
        return

    new_text = existing
    if existing and not existing.endswith("\n"):
        new_text += "\n"
    new_text += f"\n# Codebase Memory manifest (auto-added)\n{entry}\n"
    with open(gitignore, "w", encoding="utf-8") as f:
        f.write(new_text)


def _gitignore_has_entry(content: str, entry: str) -> bool:
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == entry or stripped == entry.rstrip("/"):
            return True
    return False


# Re-export for tests that need a stable path string.
del os  # silence unused
