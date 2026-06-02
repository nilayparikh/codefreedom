"""Environment variable loading with .env and .env.secrets support.

Load order (later sources override earlier):
  1. workspace/.env      (project configuration -- database, model aliases, URLs)
  2. workspace/.env.secrets  (API keys, passwords -- skips if file is missing)
  3. process environment (highest precedence -- machine-level overrides)

This means:
  - .env.secrets values override .env values
  - System env vars (export FOO=bar) override everything
  - If .env.secrets doesn't exist, secrets must come from system env
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Dict


def eprint(*args: Any, **kwargs: Any) -> None:
    """Print to stderr."""
    print(*args, file=sys.stderr, **kwargs)


def load_dotenv(path: Path) -> Dict[str, str]:
    """Parse a .env-style file and return a dict of key=value pairs.

    Handles:
      - Comment lines (# …)
      - Quoted values ("foo", 'foo')
      - Variable references like ${VAR_NAME} (substituted from current env)
    """
    env: Dict[str, str] = {}
    if not path.exists():
        return env

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, raw_val = line.partition("=")
            key = key.strip()
            raw_val = raw_val.strip()

            # Strip surrounding quotes
            if (
                len(raw_val) >= 2
                and raw_val[0] in ('"', "'")
                and raw_val[0] == raw_val[-1]
            ):
                raw_val = raw_val[1:-1]

            # Resolve ${VAR} references from current env + already-parsed vars
            def _replace_var(m: re.Match) -> str:
                varname = m.group(1)
                default = m.group(2)
                resolved = os.environ.get(varname) or env.get(varname)
                if resolved is not None:
                    return resolved
                return default if default is not None else ""

            raw_val = re.sub(r"\$\{(\w+)(?::-(.*?))?\}", _replace_var, raw_val)
            env[key] = raw_val
    return env


def load_env_chain(workspace_dir: Path) -> Dict[str, str]:
    """Load env vars in precedence order: .env → .env.secrets → system env.

    .env.secrets is searched in two locations:
      - workspace_dir/.env.secrets  (project-local, preferred)
      - ~/.env.secrets              (user-global, fallback)

    Returns a merged dict. Later sources override earlier ones.
    """
    env_file = workspace_dir / ".env"
    secrets_workspace = workspace_dir / ".env.secrets"
    merged: Dict[str, str] = {}

    # 1. workspace/.env -- project configuration (lowest precedence)
    if env_file.exists():
        merged.update(load_dotenv(env_file))
        eprint(f"  [ENV] Loaded config from {env_file}")

    # 2. workspace/.env.secrets -- API keys, passwords (overrides .env)
    if secrets_workspace.exists():
        merged.update(load_dotenv(secrets_workspace))
        eprint(f"  [ENV] Loaded secrets from {secrets_workspace}")
    # No fallback to ~/.env.secrets -- if missing, assume keys are in system env.

    # 3. Process environment (highest precedence -- machine-level overrides)
    for key, val in os.environ.items():
        merged[key] = val

    return merged
