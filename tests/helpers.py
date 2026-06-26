"""Shared test helpers — reusable utilities for test files.

These are regular functions (not fixtures) that can be imported
directly from test files.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml


def tool_home() -> Path:
    """Return the tool home directory (set by conftest.py or default)."""
    from codefreedom.core.config import get_codefreedom_dir

    override = os.environ.get("CODEFREEDOM_TOOL_HOME")
    if override:
        return Path(override)
    return get_codefreedom_dir()


def write_tool_profile(tool: str, data: dict) -> None:
    """Write tool profile to unified profiles.yaml in config directory."""
    from codefreedom.core.config import get_config_dir

    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)

    profiles_path = config_dir / "profiles.yaml"
    if profiles_path.exists():
        with open(profiles_path, encoding="utf-8") as f:
            existing = yaml.safe_load(f) or {}
    else:
        existing = {}

    if "tools" not in existing:
        existing["tools"] = {}
    existing["tools"].update(data)

    with open(profiles_path, "w", encoding="utf-8") as f:
        yaml.dump(existing, f, default_flow_style=False, sort_keys=False)


def clean_profiles() -> None:
    """Remove unified profiles.yaml to ensure clean defaults."""
    from codefreedom.core.config import get_config_dir

    config_dir = get_config_dir()
    profiles_path = config_dir / "profiles.yaml"
    if profiles_path.exists():
        profiles_path.unlink()
