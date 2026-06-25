"""Shared configuration paths for CodeFreedom.

Centralizes the CodeFreedom directory path so it's defined once
instead of being hardcoded in 7 places across 5 files.

Set ``CODEFREEDOM_HOME`` to override the default ``~/.codefreedom`` location
(for testing or custom deployments).

Config responsibility map (0.1.9 audit):

    config.py        — CODEFREEDOM_HOME path, profile path resolution, canonical config seam
    env_loader.py    — .env chain loading (9 tiers), dotenv parsing
    interpolate.py   — ${VAR} and ${VAR:-default} resolution
    profiles.py      — Profile YAML loading, validation, inheritance, env resolution

Overlaps:
- profiles.py calls interpolate.py for ${VAR} resolution
- claude.py/mimo.py/opencode.py each call env_loader + profiles independently
- config.py provides paths that env_loader and profiles both need
"""

from __future__ import annotations

import os
from pathlib import Path


def get_codefreedom_dir() -> Path:
    """Return the CodeFreedom home directory.

    Precedence:
    1. ``CODEFREEDOM_HOME`` environment variable (if set and non-empty)
    2. ``~/.codefreedom`` (default)
    """
    env_override = os.environ.get("CODEFREEDOM_HOME", "")
    if env_override:
        return Path(env_override)
    return Path.home() / ".codefreedom"


def get_config_dir() -> Path:
    """Return the managed config directory under CodeFreedom home.

    This is the single folder managed by CLI. Contains:
    - profiles.yaml (agent & tool YAML configs)
    - override.yaml (user-managed overrides)
    - proxy/ (LiteLLM config, docker-compose)
    - scripts/ (setup helper scripts)
    - .env.* (env files)

    Agent home dirs (claude-code/, mimo-code/, etc.) are NOT managed by CLI.
    """
    return get_codefreedom_dir() / "config"


def get_backup_dir() -> Path:
    """Return the default backup directory under CodeFreedom home."""
    return get_codefreedom_dir() / "backup"


def resolve_profiles_path() -> Path:
    """Return the unified profiles path (test-patchable).

    Checks ``CODEFREEDOM_PROFILES_FILE`` env var, falls back to
    ``~/.codefreedom/config/profiles.yaml``.
    """
    override = os.environ.get("CODEFREEDOM_PROFILES_FILE")
    if override:
        return Path(override)
    return get_config_dir() / "profiles.yaml"


def resolve_mimo_profiles_path() -> Path:
    """Return the MiMoCode profiles path (test-patchable).

    Checks ``MIMOCODE_PROFILES_FILE`` env var, falls back to
    ``~/.codefreedom/config/profiles.yaml``.
    """
    override = os.environ.get("MIMOCODE_PROFILES_FILE")
    if override:
        return Path(override)
    return get_config_dir() / "profiles.yaml"


def resolve_opencode_profiles_path() -> Path:
    """Return the OpenCode profiles path (test-patchable).

    Checks ``OPENCODE_PROFILES_FILE`` env var, falls back to
    ``~/.codefreedom/config/profiles.yaml``.
    """
    override = os.environ.get("OPENCODE_PROFILES_FILE")
    if override:
        return Path(override)
    return get_config_dir() / "profiles.yaml"


def resolve_pi_profiles_path() -> Path:
    """Return the Pi Code profiles path (test-patchable).

    Checks ``PI_PROFILES_FILE`` env var, falls back to
    ``~/.codefreedom/config/profiles.yaml``.
    """
    override = os.environ.get("PI_PROFILES_FILE")
    if override:
        return Path(override)
    return get_config_dir() / "profiles.yaml"


def resolve_codex_profiles_path() -> Path:
    """Return the Codex profiles path (test-patchable).

    Checks ``CODEX_PROFILES_FILE`` env var, falls back to
    ``~/.codefreedom/config/profiles.yaml``.
    """
    override = os.environ.get("CODEX_PROFILES_FILE")
    if override:
        return Path(override)
    return get_config_dir() / "profiles.yaml"


def resolve_agent_config(
    agent: str,
    profile_name: str = "default",
    workspace_dir: Path | None = None,
) -> dict:
    """Resolve complete configuration for an agent launch.

    Returns a dict with:
        - env: merged environment variables
        - profiles_path: path to the profiles YAML
        - profile: loaded profile data
        - tools: list of tools from the profile
        - sandbox_images: sandbox image configuration

    This is the canonical config seam for agent entrypoints.
    """
    from codefreedom.core.settings import resolve_agent_runtime

    runtime = resolve_agent_runtime(
        agent,
        workspace_dir=workspace_dir or Path.cwd(),
        profile_name=profile_name,
        mode="local",
    )

    return {
        "env": runtime.profile_env,
        "profiles_path": runtime.profiles_path,
        "profile": {},
        "tools": runtime.tools,
        "sandbox_images": runtime.sandbox_images,
    }
