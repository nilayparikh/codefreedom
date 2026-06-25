"""Backward-compatible re-exports — env loading now lives in codefreedom.config.

.. deprecated::
    All configuration comes from YAML + machine env. No .env files are read.
    Use ``load_config()`` from ``codefreedom.config`` instead.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional



def load_dotenv(path: Path) -> Dict[str, str]:
    """No-op: .env files are no longer supported.

    .. deprecated::
        All configuration comes from YAML files + machine environment.
        Use ``codefreedom.config.load_config()`` instead.
    """
    return {}


def load_env_chain(
    workspace_dir: Path,
    *,
    component: Optional[str] = None,
    verbose: bool = True,
) -> Dict[str, str]:
    """No-op: env chain replaced by load_config() — returns machine env only.

    .. deprecated::
        Use ``codefreedom.config.load_config()`` instead.
    """
    return dict(os.environ)


def get_env(
    workspace_dir: Path,
    *,
    component: Optional[str] = None,
    verbose: bool = True,
    extra_injections: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Return machine env only — .env chain removed.

    .. deprecated::
        Use ``codefreedom.config.load_config()`` instead.
    """
    env = dict(os.environ)
    if extra_injections:
        for key, val in extra_injections.items():
            env.setdefault(key, val)
    return apply_cf_cli_overrides(env)


def apply_cf_cli_overrides(env: Dict[str, str]) -> Dict[str, str]:
    """Apply ``CF_CLI_*`` machine env vars as final overrides."""
    for key, val in os.environ.items():
        if key.startswith("CF_CLI_"):
            real_key = key[len("CF_CLI_"):]
            env[real_key] = val
    return env
