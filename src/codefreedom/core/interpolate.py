"""Backward-compatible re-exports from codefreedom.config.interpolation.

.. deprecated::
    Import from ``codefreedom.config`` directly instead.
"""

from __future__ import annotations

import re
from codefreedom.config.interpolation import (
    interpolate_all as interpolate_all_strings,
    resolve_dict as resolve_env_dict,
    resolve_var as resolve_env_vars,
)

# Kept for backward compatibility — recipe code still checks this.
_SECRET_VAR_RE = re.compile(r"^CF_CLI_")

__all__ = [
    "_SECRET_VAR_RE",
    "interpolate_all_strings",
    "resolve_env_dict",
    "resolve_env_vars",
]
