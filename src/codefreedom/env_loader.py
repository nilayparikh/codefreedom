"""Environment variable loading with .env and .env.secrets support.

Two locations, each with the same 3-step cascade, then system env on top:

  Location 1: ~/.codefreedom/      (primary — created by ``codefreedom --init``)
  Location 2: {workspace_dir}/     (per-project overrides — optional)

Within each location the 3-step cascade is:

    {location}/.env          → defaults, model aliases, proxy settings
    {location}/.env.secrets  → API keys, passwords (skips if missing, overrides .env)
    system environment       → machine-level overrides (highest precedence)

Full resolution order (later sources override earlier):
  1. ~/.codefreedom/.env
  2. ~/.codefreedom/.env.secrets          (skips if missing)
  3. {workspace_dir}/.env                 (skips if missing)
  4. {workspace_dir}/.env.secrets         (skips if missing)
  5. os.environ / exported vars           (always wins)
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Dict

# Pre-compiled regex for ${VAR} and ${VAR:-default} patterns in .env files.
# Uses greedy .* to correctly capture defaults containing '}' characters
# (e.g., ${JSON:-{"key":"val"}}).
_VAR_REF_RE = re.compile(r"\$\{(\w+)(?::-(.*))?\}")


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
                # Use `in` check rather than `or` — an empty-string env var
                # (e.g., export FOO="") is a valid override and must not
                # fall through to a lower-precedence value.
                if varname in os.environ:
                    resolved = os.environ[varname]
                elif varname in env:
                    resolved = env[varname]
                else:
                    resolved = None
                if resolved is not None:
                    return resolved
                return default if default is not None else ""

            raw_val = _VAR_REF_RE.sub(_replace_var, raw_val)
            env[key] = raw_val
    return env


def load_env_chain(workspace_dir: Path) -> Dict[str, str]:
    """Load env vars in precedence order: home → workspace → system env.

    Resolution order (later sources override earlier):
      1. ~/.codefreedom/.env              (home config — primary location)
      2. ~/.codefreedom/.env.secrets      (home secrets — skips if missing)
      3. workspace_dir/.env               (project-local overrides — skips if missing)
      4. workspace_dir/.env.secrets       (project-local secrets — skips if missing)
      5. process environment              (highest precedence — machine-level overrides)

    Returns a merged dict. Later sources override earlier ones.
    """
    codefreedom_dir = Path.home() / ".codefreedom"
    merged: Dict[str, str] = {}

    env_sources = [
        (codefreedom_dir / ".env", "config", False),
        (codefreedom_dir / ".env.secrets", "secrets", True),
        (workspace_dir / ".env", "workspace config", True),
        (workspace_dir / ".env.secrets", "workspace secrets", True),
    ]
    for path, label, optional in env_sources:
        if path.exists():
            merged.update(load_dotenv(path))
            eprint(f"  [ENV] Loaded {label} from {path}")
        elif not optional:
            eprint(f"  [ENV] {path} not found — using workspace/system env only")

    # Process environment (highest precedence — machine-level overrides)
    for key, val in os.environ.items():
        merged[key] = val

    return merged
