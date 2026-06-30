"""Configuration loading for cf git — global config + project .cf.yaml.

Resolution order (later wins):

  1. ``_DEFAULTS`` (built-in)
  2. ``tools.git`` from ``profiles.yaml`` (recipe defaults)
  3. ``tools.git`` from ``override.yaml`` (user overrides)
  4. ``tools.git`` from ``.cf.yaml`` (per-folder override — explicit
     ``CF_CLI_CF_YAML`` env var or auto-discovered by
     :func:`codefreedom.config.load_config`)
  5. ``CF_CLI_*`` machine env (highest priority)
  6. Legacy ``git:`` block from ``.cf.yaml`` (deprecated; merged in last
     so the new ``tools.git`` schema always wins when both are present)

The new ``tools.git`` schema matches the unified config loader and is the
recommended path. The legacy ``git:`` block is preserved for backward
compatibility with pre-0.3 configs and remains the fallback for users
who haven't migrated.

All .cf.yaml discovery is centralized in :mod:`codefreedom.config.loader`
— this module just consumes the unified config.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from codefreedom.cli.git.git_ops import get_git_root
from codefreedom.core.config import get_config_dir
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
    """Load ``tools.git`` from the unified config (all 4 layers)."""
    return _load_tools_git_via_load_config()


def load_project_git_config(work_dir: Path | None = None) -> dict[str, Any]:
    """Load the legacy ``git:`` block from ``{git-root}/.cf.yaml``.

    Deprecated — use :func:`load_global_git_config` (or set
    ``CF_CLI_CF_YAML``) so the new ``tools.git`` schema takes effect.
    Retained for backward compatibility with pre-0.3 configs.
    """
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


def _load_tools_git_via_load_config() -> dict[str, Any]:
    """Read ``tools.git`` from the resolved config, falling back to empty.

    Catches :class:`ConfigError` so a missing/invalid config never
    breaks ``cf g cmt`` / ``cf g pr`` — the git module degrades to
    ``_DEFAULTS`` instead.

    The unified config loader handles ``.cf.yaml`` discovery centrally
    (env var, walk-up from cwd) so this function does not duplicate
    any path resolution.
    """
    try:
        from codefreedom.config import load_config as _load_config
        from codefreedom.config.errors import ConfigError

        config = _load_config(config_dir=get_config_dir())
        tools = config.tools
        if isinstance(tools, dict):
            git_cfg = tools.get("git", {})
            if isinstance(git_cfg, dict):
                return dict(git_cfg)
    except ConfigError as exc:
        eprint(f"{tag('WARN')} Failed to load git config: {exc}")
    except Exception as exc:
        eprint(f"{tag('WARN')} Unexpected error loading git config: {exc}")
    return {}


def load_git_config(work_dir: Path | None = None) -> dict[str, Any]:
    """Load merged git config: defaults → legacy ``git:`` block → new schema.

    Merge order (later wins):
      1. ``_DEFAULTS`` (built-in)
      2. Legacy ``git:`` block from ``{git-root}/.cf.yaml`` (deprecated)
      3. ``tools.git`` from the unified config (all 4 layers — wins on
         any key the legacy block also set, so the new schema always
         takes precedence on conflicts).
    """
    config = dict(_DEFAULTS)
    project_cfg = load_project_git_config(work_dir)
    _deep_merge(config, project_cfg)
    global_cfg = _load_tools_git_via_load_config()
    _deep_merge(config, global_cfg)
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
