"""Centralized YAML utilities — safe_load with consistent error handling."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from codefreedom.log import eprint, tag


def safe_load(path: Path) -> dict[str, Any]:
    """Safely load a YAML file and return a dict.

    Returns an empty dict if the file is empty or contains only comments.
    Raises ``yaml.YAMLError`` if the file has syntax errors.
    Raises ``FileNotFoundError`` if the file does not exist.
    """
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def safe_load_or_warn(path: Path) -> dict[str, Any]:
    """Safely load a YAML file, warning on errors instead of raising.

    Returns an empty dict on any error (file missing, YAML error, etc.).
    """
    try:
        return safe_load(path)
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as exc:
        eprint(f"{tag('WARN')} YAML parse error in {path}: {exc}")
        return {}


def safe_load_all(path: Path) -> list[dict[str, Any]]:
    """Load a multi-document YAML file, returning a list of dicts."""
    with open(path, encoding="utf-8") as f:
        docs = list(yaml.safe_load_all(f))
    return [d if isinstance(d, dict) else {} for d in docs]


def safe_dump(data: dict[str, Any], path: Path) -> None:
    """Dump a dict to a YAML file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
