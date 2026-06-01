"""Profile management for Claude Code model selection and routing.

Profiles are defined in claude-code-profiles.json. Each profile sets
environment variables that control model selection, API endpoint, and auth.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


def eprint(*args: Any, **kwargs: Any) -> None:
    """Print to stderr."""
    print(*args, file=sys.stderr, **kwargs)


def load_profiles(profiles_path: Path) -> Dict[str, Any]:
    """Load and validate the profiles JSON file."""
    if not profiles_path.exists():
        eprint(f"[ERROR] Profiles file not found: {profiles_path}")
        sys.exit(1)

    try:
        with open(profiles_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        eprint(f"[ERROR] Invalid JSON in {profiles_path}: {e}")
        sys.exit(1)

    profiles = data.get("profiles", {})
    if not profiles:
        eprint("[ERROR] No profiles defined in profiles file.")
        sys.exit(1)

    return profiles


def resolve_env(env_def: Dict[str, str], context: Dict[str, str]) -> Dict[str, str]:
    """Resolve ${VAR} references in env values using a context dict."""
    result: Dict[str, str] = {}
    for key, raw_val in env_def.items():

        def _sub(m: re.Match) -> str:
            varname = m.group(1)
            default = m.group(2)
            resolved = context.get(varname) or os.environ.get(varname)
            if resolved is not None:
                return resolved
            if default is not None:
                return default
            eprint(f"[WARN] env var ${{{varname}}} referenced but not set (empty)")
            return ""

        result[key] = re.sub(r"\$\{(\w+)(?::-(.*?))?\}", _sub, raw_val)
    return result


def load_profile_env(
    profile_name: str,
    profiles_path: Path,
    base_env: Dict[str, str],
) -> Dict[str, str]:
    """Load a named profile's env vars, resolving ${VAR} references from base_env.

    Returns the merged env dict for the profile.
    """
    profiles = load_profiles(profiles_path)

    if profile_name not in profiles:
        eprint(f"[ERROR] Profile '{profile_name}' not found in {profiles_path}.")
        eprint("   Available profiles:")
        for name, info in profiles.items():
            desc = info.get("description", "No description")
            eprint(f"     - {name}: {desc}")
        sys.exit(1)

    profile_def = profiles[profile_name]
    env_def = profile_def.get("env", {})

    # Inheritance: bare and default are standalone; everything else inherits from default
    if profile_name in ("default", "bare"):
        eprint(f"[PROFILE] Loading '{profile_name}' (standalone)...")
        merged = resolve_env(env_def, base_env)
    else:
        eprint(f"[PROFILE] Loading '{profile_name}' (inherits from 'default')...")
        default_def = profiles.get("default", {}).get("env", {})
        merged = resolve_env(default_def, base_env)
        overrides = resolve_env(env_def, {**base_env, **merged})
        merged.update(overrides)

    # Log what was loaded (masking sensitive values)
    for key in sorted(merged.keys()):
        val = merged[key]
        display = val
        if any(
            s in key.upper() for s in ("TOKEN", "KEY", "SECRET", "AUTH", "PASSWORD")
        ):
            if len(val) > 4:
                display = val[:1] + "*" * min(len(val) - 3, 64) + val[-2:]
            elif val:
                display = "****"
        eprint(f"     {key}={display}")

    return merged


def list_profiles(profiles_path: Path) -> List[Dict[str, Any]]:
    """Return a list of profile metadata for display."""
    if not profiles_path.exists():
        eprint(f"[PROFILES] No profiles file at {profiles_path}")
        return []

    profiles = load_profiles(profiles_path)
    result = []
    for name in sorted(profiles.keys()):
        info = profiles[name]
        env_keys = list(info.get("env", {}).keys())
        result.append(
            {
                "name": name,
                "description": info.get("description", "No description"),
                "env_keys": env_keys,
                "standalone": name in ("default", "bare"),
            }
        )
    return result
