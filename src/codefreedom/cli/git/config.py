"""Configuration loading for cf git — global git.yaml + project .cf.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from codefreedom.cli.git.git_ops import get_git_root
from codefreedom.core.config import get_codefreedom_dir
from codefreedom.log import eprint, tag

_DEFAULTS: dict[str, Any] = {
    "model": "gpt-4o-mini",
    "conventional_commit": True,
    "signed_commit": True,
    "templates": {
        "commit_message": "${type}(${scope}): ${description}",
        "pr_title": "${type}(${scope}): ${description}",
        "pr_description": "## Summary\n${summary}\n\n## Changes\n${changes}\n\n## Testing\n${testing}",
    },
    "modules": [],
}


def load_global_git_config() -> dict[str, Any]:
    """Load git config from ~/.codefreedom/profiles/git.yaml."""
    path = get_codefreedom_dir() / "profiles" / "git.yaml"
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            return data.get("git", {})
    except Exception as e:
        eprint(f"{tag('WARN')} Failed to load {path}: {e}")
    return {}


def load_project_git_config(work_dir: Path | None = None) -> dict[str, Any]:
    """Load git config from {git-root}/.cf.yaml."""
    root = get_git_root(work_dir)
    if root is None:
        return {}
    path = root / ".cf.yaml"
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            return data.get("git", {})
    except Exception as e:
        eprint(f"{tag('WARN')} Failed to load {path}: {e}")
    return {}


def load_git_config(work_dir: Path | None = None) -> dict[str, Any]:
    """Load merged git config: defaults → global → project."""
    config = dict(_DEFAULTS)
    global_cfg = load_global_git_config()
    _deep_merge(config, global_cfg)
    project_cfg = load_project_git_config(work_dir)
    _deep_merge(config, project_cfg)
    return config


def _deep_merge(base: dict, override: dict) -> None:
    """Merge override into base in-place."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def get_template(config: dict[str, Any], template_name: str) -> str:
    """Get a template string from config."""
    templates = config.get("templates", {})
    return templates.get(template_name, "")


def get_modules(config: dict[str, Any]) -> list[str]:
    """Get the modules list from config."""
    return config.get("modules", []) or []


def is_conventional_commit(config: dict[str, Any]) -> bool:
    """Check if conventional commit is enabled."""
    return config.get("conventional_commit", True)


def is_signed_commit(config: dict[str, Any]) -> bool:
    """Check if signed commit is enabled."""
    return config.get("signed_commit", True)


def get_model(config: dict[str, Any]) -> str:
    """Get the LLM model name."""
    return config.get("model", "gpt-4o-mini")
