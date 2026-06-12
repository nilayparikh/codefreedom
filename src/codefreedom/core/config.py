"""Shared configuration paths for CodeFreedom.

Centralizes the CodeFreedom directory path so it's defined once
instead of being hardcoded in 7 places across 5 files.

Set ``CODEFREEDOM_HOME`` to override the default ``~/.codefreedom`` location
(for testing or custom deployments).
"""

from __future__ import annotations

import os
from pathlib import Path


def get_codefreedom_dir() -> Path:
    """Return the CodeFreedom config directory.

    Precedence:
    1. ``CODEFREEDOM_HOME`` environment variable (if set and non-empty)
    2. ``~/.codefreedom`` (default)
    """
    env_override = os.environ.get("CODEFREEDOM_HOME", "")
    if env_override:
        return Path(env_override)
    return Path.home() / ".codefreedom"


def get_backup_dir() -> Path:
    """Return the default backup directory under CodeFreedom home."""
    return get_codefreedom_dir() / "backup"


def resolve_profiles_path() -> Path:
    """Return the Claude Code profiles path (test-patchable).

    Checks ``CODEFREEDOM_PROFILES_FILE`` env var, falls back to
    ``~/.codefreedom/profiles/claude-code.yaml``.
    """
    override = os.environ.get("CODEFREEDOM_PROFILES_FILE")
    if override:
        return Path(override)
    return get_codefreedom_dir() / "profiles" / "claude-code.yaml"


def resolve_mimo_profiles_path() -> Path:
    """Return the MiMoCode profiles path (test-patchable).

    Checks ``MIMOCODE_PROFILES_FILE`` env var, falls back to
    ``~/.codefreedom/profiles/mimo-code.yaml``.
    """
    override = os.environ.get("MIMOCODE_PROFILES_FILE")
    if override:
        return Path(override)
    return get_codefreedom_dir() / "profiles" / "mimo-code.yaml"


def resolve_opencode_profiles_path() -> Path:
    """Return the OpenCode profiles path (test-patchable).

    Checks ``OPENCODE_PROFILES_FILE`` env var, falls back to
    ``~/.codefreedom/profiles/opencode.yaml``.
    """
    override = os.environ.get("OPENCODE_PROFILES_FILE")
    if override:
        return Path(override)
    return get_codefreedom_dir() / "profiles" / "opencode.yaml"
