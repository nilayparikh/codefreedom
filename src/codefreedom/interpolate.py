"""Unified ${VAR} and ${VAR:-default} environment variable interpolation.

All CodeFreedom config loaders use this single resolver for consistency.
Supports empty-string overrides (export FOO="" does NOT fall through).
"""

from __future__ import annotations

import os
import re
from typing import Dict

_VAR_REF_RE = re.compile(r"\$\{(\w+)(?::-(.*))?\}")


def resolve_env_vars(value: str, context: dict[str, str] | None = None) -> str:
    """Resolve ${VAR} and ${VAR:-default} in a single string value.

    Resolution order: context dict → os.environ → default → empty string.
    Empty-string values in context or os.environ are valid overrides.
    """

    def _sub(m: re.Match) -> str:
        varname = m.group(1)
        default = m.group(2)
        if context is not None and varname in context:
            resolved = context[varname]
        elif varname in os.environ:
            resolved = os.environ[varname]
        else:
            resolved = None
        if resolved is not None:
            return resolved
        return default if default is not None else ""

    return _VAR_REF_RE.sub(_sub, value)


def resolve_env_dict(
    env: dict[str, str], context: dict[str, str] | None = None
) -> dict[str, str]:
    """Resolve ${VAR} references in all string values of an env dict."""
    return {k: resolve_env_vars(v, context) for k, v in env.items()}


def interpolate_all_strings(
    data: dict,
    context: dict[str, str] | None = None,
) -> None:
    """Recursively interpolate ${VAR} in all string values in a nested dict.

    Mutates the dict in-place. Only processes string values
    (skips lists, nested dicts — those are handled by recursion).
    """
    for key, val in list(data.items()):
        if isinstance(val, str):
            data[key] = resolve_env_vars(val, context)
        elif isinstance(val, dict):
            interpolate_all_strings(val, context)
        elif isinstance(val, list):
            for i, item in enumerate(val):
                if isinstance(item, str):
                    val[i] = resolve_env_vars(item, context)
                elif isinstance(item, dict):
                    interpolate_all_strings(item, context)
