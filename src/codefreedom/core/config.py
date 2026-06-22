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


def resolve_pi_profiles_path() -> Path:
    """Return the Pi Code profiles path (test-patchable).

    Checks ``PI_PROFILES_FILE`` env var, falls back to
    ``~/.codefreedom/profiles/pi-code.yaml``.
    """
    override = os.environ.get("PI_PROFILES_FILE")
    if override:
        return Path(override)
    return get_codefreedom_dir() / "profiles" / "pi-code.yaml"


def resolve_codex_profiles_path() -> Path:
    """Return the Codex profiles path (test-patchable).

    Checks ``CODEX_PROFILES_FILE`` env var, falls back to
    ``~/.codefreedom/profiles/codex-code.yaml``.
    """
    override = os.environ.get("CODEX_PROFILES_FILE")
    if override:
        return Path(override)
    return get_codefreedom_dir() / "profiles" / "codex-code.yaml"


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
    from codefreedom.core.profiles import load_profiles, load_profile_env
    from codefreedom.env_loader import load_env_chain

    # Resolve profiles path
    if agent == "claude-code":
        profiles_path = resolve_profiles_path()
    elif agent == "mimo-code":
        profiles_path = resolve_mimo_profiles_path()
    elif agent == "open-code":
        profiles_path = resolve_opencode_profiles_path()
    elif agent == "pi-code":
        profiles_path = resolve_pi_profiles_path()
    elif agent == "codex-code":
        profiles_path = resolve_codex_profiles_path()
    else:
        raise ValueError(f"Unknown agent: {agent}")

    # Load profiles
    profiles = load_profiles(profiles_path)

    # Load env chain
    component = agent.split("-")[0]  # "claude", "mimo", "open", "codex"
    env = load_env_chain(workspace_dir or Path.cwd(), component=component)

    # Resolve profile
    profile_env = load_profile_env(
        profile_name, profiles_path, env, profiles=profiles
    )

    # Extract tools and sandbox images from profile
    profile_def = profiles.get(profile_name, {})
    tools = profile_def.get("tools", [])
    sandbox_images = profile_def.get("sandbox_images", {})

    return {
        "env": profile_env,
        "profiles_path": profiles_path,
        "profile": profile_def,
        "tools": tools,
        "sandbox_images": sandbox_images,
    }
