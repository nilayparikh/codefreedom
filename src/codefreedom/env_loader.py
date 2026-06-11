"""Environment variable loading with .env, .env.secrets, and .env.user support.

Five tiers of env files, loaded in precedence order, then system env on top.
Within the loading order, ALL config files (.env.*) are loaded first, then ALL
secrets files (.env.*.secrets), then the user override file (.env.user),
then system env. This ensures secrets always override config, and user
overrides always win short of the host OS environment.

  Tier 1: Component-specific (loaded only for the matching subcommand)
    ~/.codefreedom/.env.claude              — codefreedom claude
    ~/.codefreedom/.env.proxy               — codefreedom proxy

  Tier 2: Shared config (loaded for ALL components — claude, proxy, tools)
    ~/.codefreedom/.env

  Tier 3: Workspace config (loaded for ALL components)
    {workspace_dir}/.env

  Tier 4: Component-specific secrets
    ~/.codefreedom/.env.claude.secrets      — codefreedom claude
    ~/.codefreedom/.env.proxy.secrets       — codefreedom proxy

  Tier 5: Shared secrets
    ~/.codefreedom/.env.secrets

  Tier 6: Workspace secrets
    {workspace_dir}/.env.secrets

  Tier 7: User overrides (highest config-file priority)
    {codefreedom_dir}/.env.user             — created once by recipe, never
                                               touched by recipes again.
                                               Manually edited by the user to
                                               override any parameter.

  Tier 8: System environment (always wins)
    os.environ

Full resolution order (later sources override earlier):

  codefreedom claude:
    1. ~/.codefreedom/.env.claude           (component config, skip if missing)
    2. ~/.codefreedom/.env                  (shared config, skip if missing)
    3. {workspace_dir}/.env                 (workspace config, skip if missing)
    4. ~/.codefreedom/.env.claude.secrets   (component secrets, skip if missing)
    5. ~/.codefreedom/.env.secrets          (shared secrets, skip if missing)
    6. {workspace_dir}/.env.secrets         (workspace secrets, skip if missing)
    7. {codefreedom_dir}/.env.user          (user overrides, skip if missing)
    8. os.environ / exported vars           (always wins)

  codefreedom proxy:
    1. ~/.codefreedom/.env.proxy            (component config, skip if missing)
    2. ~/.codefreedom/.env                  (shared config, skip if missing)
    3. {workspace_dir}/.env                 (workspace config, skip if missing)
    4. ~/.codefreedom/.env.proxy.secrets    (component secrets, skip if missing)
    5. ~/.codefreedom/.env.secrets          (shared secrets, skip if missing)
    6. {workspace_dir}/.env.secrets         (workspace secrets, skip if missing)
    7. {codefreedom_dir}/.env.user          (user overrides, skip if missing)
    8. os.environ / exported vars           (always wins)

  codefreedom tools (chrome, web, etc.):
    1. ~/.codefreedom/.env                  (shared config, skip if missing)
    2. {workspace_dir}/.env                 (workspace config, skip if missing)
    3. ~/.codefreedom/.env.secrets          (shared secrets, skip if missing)
    4. {workspace_dir}/.env.secrets         (workspace secrets, skip if missing)
    5. {codefreedom_dir}/.env.user          (user overrides, skip if missing)
    6. os.environ / exported vars           (always wins)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from codefreedom.interpolate import resolve_env_vars


def eprint(*args: Any, **kwargs: Any) -> None:
    """Print to stderr. The canonical definition — all modules import from here."""
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
            raw_val = resolve_env_vars(raw_val, {**os.environ, **env})
            env[key] = raw_val
    return env


def load_env_chain(
    workspace_dir: Path,
    *,
    component: Optional[str] = None,
    verbose: bool = True,
) -> Dict[str, str]:
    """Load env vars in precedence order: component → shared → workspace → system env.

    Args:
        workspace_dir: Path to the project workspace (for .env overrides).
        component: Which subcommand is loading envs — "claude" loads
                   .env.claude/.env.claude.secrets, "proxy" loads
                   .env.proxy/.env.proxy.secrets.  If None, only shared
                   and workspace envs are loaded (used by tools).
        verbose: Print ``[ENV]`` log lines for each loaded file.

    Resolution order (later sources override earlier):
      Config files (lowest priority):
        1. ~/.codefreedom/.env.<component>           (component config, skip if missing)
        2. ~/.codefreedom/.env                        (shared config, skip if missing)
        3. workspace_dir/.env                         (workspace config, skip if missing)
      Secrets files (override configs):
        4. ~/.codefreedom/.env.<component>.secrets    (component secrets, skip if missing)
        5. ~/.codefreedom/.env.secrets                (shared secrets, skip if missing)
        6. workspace_dir/.env.secrets                 (workspace secrets, skip if missing)
      User overrides (override everything except system env):
        7. {codefreedom_dir}/.env.user                (user overrides, skip if missing)
      System (always wins):
        8. process environment                        (highest precedence)

    Returns a merged dict. Later sources override earlier ones.

    Note: Most call sites should use :func:`get_env` instead — it wraps this
    function with support for extra injections (e.g. proxy POSTGRES_* paths)
    and is the single canonical env-resolution entry point.
    """
    from codefreedom.config import get_codefreedom_dir

    codefreedom_dir = get_codefreedom_dir()
    merged: Dict[str, str] = {}

    env_sources: list[tuple[Path, str, bool]] = []

    # ── Tier 1: ALL config files first (lowest priority) ───────────────────

    # Component-specific config
    if component:
        env_sources.append(
            (codefreedom_dir / f".env.{component}", f"{component} config", True),
        )

    # Shared config
    env_sources.append((codefreedom_dir / ".env", "shared config", True))

    # Workspace config
    env_sources.append((workspace_dir / ".env", "workspace config", True))

    # ── Tier 2: ALL secrets files (override configs) ───────────────────────

    # Component-specific secrets
    if component:
        env_sources.append(
            (
                codefreedom_dir / f".env.{component}.secrets",
                f"{component} secrets",
                True,
            ),
        )

    # Shared secrets
    env_sources.append((codefreedom_dir / ".env.secrets", "shared secrets", True))

    # Workspace secrets
    env_sources.append((workspace_dir / ".env.secrets", "workspace secrets", True))

    # ── Tier 3: User overrides (just below system env — highest config priority)
    env_sources.append(
        (codefreedom_dir / ".env.user", "user overrides", True),
    )

    for path, label, _optional in env_sources:
        if path.exists():
            merged.update(load_dotenv(path))
            if verbose:
                eprint(f"  [ENV] Loaded {label} from {path}")

    # Process environment (highest precedence — machine-level overrides)
    for key, val in os.environ.items():
        merged[key] = val

    # CF_CLI_* overrides from machine env — highest priority of all.
    # Users can export CF_CLI_LITELLM_MASTER_KEY=sk-... in their shell
    # to force-set configuration values without touching .env files.
    merged = apply_cf_cli_overrides(merged)

    return merged


def get_env(
    workspace_dir: Path,
    *,
    component: Optional[str] = None,
    verbose: bool = True,
    extra_injections: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """THE single canonical env resolver for all CodeFreedom components.

    Loads the full env precedence chain via :func:`load_env_chain`, applies
    ``CF_CLI_*`` overrides, and injects any *extra_injections* with
    ``setdefault`` semantics (they won't override an existing value).

    Every subcommand (claude, proxy, tools, vscode, doctor, deinit) should
    use this function — and ONLY this function — to resolve environment
    variables.  No more custom env loading in individual call sites.

    Args:
        workspace_dir: Path to the project workspace (for .env overrides).
        component: Which subcommand is loading envs — ``"claude"`` loads
                   ``.env.claude`` / ``.env.claude.secrets``, ``"proxy"``
                   loads ``.env.proxy`` / ``.env.proxy.secrets``.  If
                   ``None``, only shared and workspace envs are loaded
                   (used by tools).
        verbose: Print ``[ENV]`` log lines for each loaded file.
        extra_injections: Additional vars to inject with ``setdefault``
            (e.g. ``{"POSTGRES_HOST_DATA_DIR": "/path/to/pg/data"}``).
            These won't override existing values from env files or
            ``os.environ``.

    Returns:
        A merged ``Dict[str, str]`` with the full resolved environment.
    """
    merged = load_env_chain(workspace_dir, component=component, verbose=verbose)

    if extra_injections:
        for key, val in extra_injections.items():
            merged.setdefault(key, val)

    return merged


def apply_cf_cli_overrides(env: Dict[str, str]) -> Dict[str, str]:
    """Apply ``CF_CLI_*`` machine env vars as final overrides.

    Any environment variable starting with ``CF_CLI_`` is stripped of its
    prefix and written into *env*, overriding any existing value.  This
    gives users a guaranteed way to control CodeFreedom configuration
    from their shell or dotfiles without editing ``.env`` files.

    Example:
        ``export CF_CLI_LITELLM_MASTER_KEY=sk-xxx``
        → sets ``env["LITELLM_MASTER_KEY"] = "sk-xxx"``
    """
    for key, val in os.environ.items():
        if key.startswith("CF_CLI_"):
            real_key = key[len("CF_CLI_") :]
            env[real_key] = val
    return env
