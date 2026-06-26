"""Shared configuration paths for CodeFreedom.

Centralizes the CodeFreedom directory path so it's defined once
instead of being hardcoded in 7 places across 5 files.

Set ``CODEFREEDOM_HOME`` to override the default ``~/.codefreedom`` location
(for testing or custom deployments).

The five ``resolve_*_profiles_path`` helpers below were originally
per-agent near-identical copies (each honouring its own
``<AGENT>_PROFILES_FILE`` env override). They are now thin wrappers around
:func:`resolve_agent_profiles_path`, which keeps the per-agent env-var map
in one place so new agents don't need a fresh copy of the same code.
"""

from __future__ import annotations

import os
from pathlib import Path

# Agent → env-var name that overrides that agent's profiles.yaml path. The env
# var exists only for tests that want to redirect a single agent's config file.
_AGENT_PROFILES_FILE_ENV: dict[str, str] = {
    "claude-code": "CODEFREEDOM_PROFILES_FILE",
    "mimo-code": "MIMOCODE_PROFILES_FILE",
    "open-code": "OPENCODE_PROFILES_FILE",
    "pi-code": "PI_PROFILES_FILE",
    "codex-code": "CODEX_PROFILES_FILE",
}


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


def resolve_agent_profiles_path(agent: str | None = None) -> Path:
    """Return the unified ``profiles.yaml`` path.

    Args:
        agent: Optional canonical agent name (e.g. ``"claude-code"``). When
            supplied, the per-agent ``<AGENT>_PROFILES_FILE`` env var (see
            :data:`_AGENT_PROFILES_FILE_ENV`) takes precedence. When omitted,
            the generic ``CODEFREEDOM_PROFILES_FILE`` env var is consulted.

    Falls back to ``~/.codefreedom/config/profiles.yaml`` if no override is
    set. The historical 5x duplicate functions (one per agent) now delegate
    here; new agents just need an entry in the env-var map above.
    """
    if agent is None:
        override = os.environ.get(_AGENT_PROFILES_FILE_ENV["claude-code"])
    else:
        override = os.environ.get(_AGENT_PROFILES_FILE_ENV.get(agent, ""))
    if override:
        return Path(override)
    return get_config_dir() / "profiles.yaml"


# ── Backward-compatible per-agent wrappers ─────────────────────────────────
# Existing CLI modules and tests import these by name; they delegate to the
# single :func:`resolve_agent_profiles_path` resolver above. Do not duplicate
# the resolver body — fix bugs in one place.


def resolve_profiles_path() -> Path:
    """Return the Claude Code (canonical) profiles path."""
    return resolve_agent_profiles_path("claude-code")


def resolve_mimo_profiles_path() -> Path:
    """Return the MiMoCode profiles path."""
    return resolve_agent_profiles_path("mimo-code")


def resolve_opencode_profiles_path() -> Path:
    """Return the OpenCode profiles path."""
    return resolve_agent_profiles_path("open-code")


def resolve_pi_profiles_path() -> Path:
    """Return the Pi Code profiles path."""
    return resolve_agent_profiles_path("pi-code")


def resolve_codex_profiles_path() -> Path:
    """Return the Codex profiles path."""
    return resolve_agent_profiles_path("codex-code")
