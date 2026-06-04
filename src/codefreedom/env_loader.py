"""Environment variable loading with .env and .env.secrets support.

Three tiers of env files, loaded in precedence order, then system env on top:

  Tier 1: Component-specific (loaded only for the matching subcommand)
    ~/.codefreedom/.env.claude / .env.claude.secrets   — codefreedom claude
    ~/.codefreedom/.env.proxy  / .env.proxy.secrets    — codefreedom proxy

  Tier 2: Shared config (loaded for ALL components — claude, proxy, tools)
    ~/.codefreedom/.env / .env.secrets

  Tier 3: Workspace overrides (loaded for ALL components)
    {workspace_dir}/.env / .env.secrets

  Tier 4: System environment (highest precedence, always wins)
    os.environ

Full resolution order (later sources override earlier):

  codefreedom claude:
    1. ~/.codefreedom/.env.claude           (skip if missing)
    2. ~/.codefreedom/.env.claude.secrets   (skip if missing)
    3. ~/.codefreedom/.env                  (shared — skip if missing)
    4. ~/.codefreedom/.env.secrets          (shared — skip if missing)
    5. {workspace_dir}/.env                 (skip if missing)
    6. {workspace_dir}/.env.secrets         (skip if missing)
    7. os.environ / exported vars           (always wins)

  codefreedom proxy:
    1. ~/.codefreedom/.env.proxy            (skip if missing)
    2. ~/.codefreedom/.env.proxy.secrets    (skip if missing)
    3. ~/.codefreedom/.env                  (shared — skip if missing)
    4. ~/.codefreedom/.env.secrets          (shared — skip if missing)
    5. {workspace_dir}/.env                 (skip if missing)
    6. {workspace_dir}/.env.secrets         (skip if missing)
    7. os.environ / exported vars           (always wins)

  codefreedom tools (chrome, web, etc.):
    1. ~/.codefreedom/.env                  (shared — skip if missing)
    2. ~/.codefreedom/.env.secrets          (shared — skip if missing)
    3. {workspace_dir}/.env                 (skip if missing)
    4. {workspace_dir}/.env.secrets         (skip if missing)
    5. os.environ / exported vars           (always wins)
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

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


def load_env_chain(
    workspace_dir: Path,
    *,
    component: Optional[str] = None,
) -> Dict[str, str]:
    """Load env vars in precedence order: component → shared → workspace → system env.

    Args:
        workspace_dir: Path to the project workspace (for .env overrides).
        component: Which subcommand is loading envs — "claude" loads
                   .env.claude/.env.claude.secrets, "proxy" loads
                   .env.proxy/.env.proxy.secrets.  If None, only shared
                   and workspace envs are loaded (used by tools).

    Resolution order (later sources override earlier):
      Component-specific (if component is set):
        1. ~/.codefreedom/.env.<component>           (skip if missing)
        2. ~/.codefreedom/.env.<component>.secrets   (skip if missing)
      Shared (always loaded):
        3. ~/.codefreedom/.env                        (skip if missing)
        4. ~/.codefreedom/.env.secrets                (skip if missing)
      Workspace (always loaded):
        5. workspace_dir/.env                         (skip if missing)
        6. workspace_dir/.env.secrets                 (skip if missing)
      System (always wins):
        7. process environment                        (highest precedence)

    Returns a merged dict. Later sources override earlier ones.
    """
    from codefreedom.config import get_codefreedom_dir

    codefreedom_dir = get_codefreedom_dir()
    merged: Dict[str, str] = {}

    env_sources: list[tuple[Path, str, bool]] = []

    # Tier 1: Component-specific (only for the matching subcommand)
    if component:
        env_sources.extend(
            [
                (codefreedom_dir / f".env.{component}", f"{component} config", True),
                (
                    codefreedom_dir / f".env.{component}.secrets",
                    f"{component} secrets",
                    True,
                ),
            ]
        )

    # Tier 2: Shared config (loaded for ALL components)
    env_sources.extend(
        [
            (codefreedom_dir / ".env", "shared config", True),
            (codefreedom_dir / ".env.secrets", "shared secrets", True),
        ]
    )

    # Tier 3: Workspace overrides
    env_sources.extend(
        [
            (workspace_dir / ".env", "workspace config", True),
            (workspace_dir / ".env.secrets", "workspace secrets", True),
        ]
    )

    for path, label, optional in env_sources:
        if path.exists():
            merged.update(load_dotenv(path))
            eprint(f"  [ENV] Loaded {label} from {path}")

    # Process environment (highest precedence — machine-level overrides)
    for key, val in os.environ.items():
        merged[key] = val

    return merged
