"""Backward-compatible re-exports from codefreedom.config.

.. deprecated::
    Import from ``codefreedom.config`` directly instead.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from codefreedom.config import (
    ConfigError,
    load_config,
)


class ProfileError(Exception):
    """Raised when a profile cannot be loaded or is invalid."""


def load_profiles(profiles_path: Path, agent: str | None = None) -> Dict[str, Any]:
    """Load profiles via new config system (backward compat wrapper).

    .. deprecated::
        Use ``load_config().for_agent(...)`` instead.
    """
    # This is a minimal compat shim — callers should migrate to
    # load_config().for_agent() directly.
    try:
        config = load_config(profiles_path.parent)
    except ConfigError as e:
        raise ProfileError(str(e)) from e

    if agent:
        try:
            agent_cfg = config.for_agent(agent)
            return {
                "default": {"env": agent_cfg.env, "tools": agent_cfg.tools},
            }
        except ConfigError:
            pass

    # Fallback: return raw profile entries
    result: Dict[str, Any] = {}
    for agent_name, agent_def in config.agents.items():
        for profile_name in agent_def.profiles:
            resolved = agent_def.resolve_profile(profile_name)
            result[profile_name] = {
                "env": resolved.env,
                "tools": resolved.tools or [],
                "description": resolved.description,
                "sandbox": {"env": resolved.sandbox.env if resolved.sandbox else {}},
                "local": {"env": resolved.local.env if resolved.local else {}},
            }
    return result


def resolve_env(env_def: Dict[str, str], context: Dict[str, str]) -> Dict[str, str]:
    """Resolve ${VAR} in env values."""
    from codefreedom.config import resolve_dict
    return resolve_dict(env_def, context)


def load_profile_env(
    profile_name: str,
    profiles_path: Path,
    base_env: Dict[str, str],
    mode: str | None = None,
    profiles: Dict[str, Any] | None = None,
) -> Dict[str, str]:
    """Load profile env (backward compat wrapper).

    .. deprecated::
        Use ``load_config().for_agent(...).env`` instead.
    """
    try:
        config = load_config(profiles_path.parent)
        agent_cfg = config.for_agent(
            _detect_agent(config, profile_name),
            profile=profile_name,
            mode=mode,
        )
        return agent_cfg.env
    except ConfigError as e:
        raise ProfileError(str(e)) from e


def _detect_agent(config, profile_name: str) -> str:
    """Find the first agent that has the given profile."""
    for agent_name, agent_def in config.agents.items():
        if profile_name in agent_def.profiles:
            return agent_name
    # Fallback to claude-code
    return "claude-code"


def get_profile_sandbox_images(
    profile_name: str,
    profiles_path: Path,
    profiles: Dict[str, Any] | None = None,
) -> Dict[str, str]:
    """Get sandbox images (backward compat wrapper)."""
    try:
        config = load_config(profiles_path.parent)
        agent_cfg = config.for_agent(
            _detect_agent(config, profile_name),
            profile=profile_name,
        )
        return agent_cfg.sandbox_images
    except ConfigError:
        return {}


def get_profile_tools(
    profile_name: str,
    profiles_path: Path,
    profiles: Dict[str, Any] | None = None,
) -> List[str]:
    """Get profile tools (backward compat wrapper)."""
    try:
        config = load_config(profiles_path.parent)
        agent_cfg = config.for_agent(
            _detect_agent(config, profile_name),
            profile=profile_name,
        )
        return agent_cfg.tools
    except ConfigError:
        return []


def list_profiles(profiles_path: Path, agent: str | None = None) -> List[Dict[str, Any]]:
    """List profiles (backward compat wrapper)."""
    try:
        config = load_config(profiles_path.parent)
    except ConfigError:
        return []

    result = []
    for agent_name, agent_def in config.agents.items():
        if agent and agent_name != agent:
            continue
        for profile_name in agent_def.profiles:
            resolved = agent_def.resolve_profile(profile_name)
            result.append({
                "name": profile_name,
                "description": resolved.description or "No description",
                "env_keys": list(resolved.env.keys()),
                "tools": resolved.tools or [],
                "standalone": profile_name in ("default", "bare"),
            })
    return result
