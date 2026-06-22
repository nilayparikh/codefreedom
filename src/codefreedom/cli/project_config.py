"""cf project config — generic .cf.yaml management.

Any module can add/update its block in .cf.yaml.
The git module adds a `git:` block via cf git init.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from codefreedom.cli.git.git_ops import get_git_root


def find_cf_yaml(start: Path | None = None) -> Path | None:
    """Find .cf.yaml by walking up from start to git root."""
    root = get_git_root(start)
    if root is None:
        return None
    path = root / ".cf.yaml"
    return path if path.exists() else None


def load_cf_yaml(path: Path) -> dict:
    """Load .cf.yaml, returning empty dict on missing/invalid file."""
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_cf_yaml(path: Path, data: dict) -> None:
    """Save .cf.yaml preserving comments via block-level formatting."""
    lines = [
        "# .cf.yaml -- CodeFreedom project config",
        "# This file is the single source of truth for project-level overrides.",
        "# Each module adds its own top-level block here.",
        "",
    ]

    for block_name, block_data in data.items():
        lines.append(f"{block_name}:")
        if isinstance(block_data, dict):
            lines.extend(_format_dict(block_data, indent=2))
        else:
            lines.append(f"  {yaml.dump(block_data, default_flow_style=False).strip()}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def _format_dict(d: dict, indent: int = 2) -> list[str]:
    """Format a dict as indented YAML lines."""
    lines: list[str] = []
    prefix = " " * indent
    for key, val in d.items():
        if isinstance(val, dict):
            lines.append(f"{prefix}{key}:")
            lines.extend(_format_dict(val, indent + 2))
        elif isinstance(val, list):
            lines.append(f"{prefix}{key}:")
            for item in val:
                lines.append(f"{prefix}  - {item}")
        elif isinstance(val, bool):
            lines.append(f"{prefix}{key}: {'true' if val else 'false'}")
        else:
            lines.append(f"{prefix}{key}: {val}")
    return lines


def update_cf_yaml(path: Path, block_name: str, block_data: dict, force: bool = False) -> int:
    """Add or update a block in .cf.yaml.

    - If .cf.yaml doesn't exist: create it with this block.
    - If .cf.yaml exists but block is missing: add it.
    - If .cf.yaml exists and block exists: skip (unless force).

    Returns: 0 = success, 1 = error, 2 = skipped (already exists, no force).
    """
    data = load_cf_yaml(path)

    if block_name in data and not force:
        return 2

    data[block_name] = block_data
    save_cf_yaml(path, data)
    return 0
