"""Profile management for model selection and routing across code agents.

Profiles are defined in claude-code-profiles.json. Each profile sets
environment variables that control model selection, API endpoint, and auth.
All profiles live in ~/.codefreedom/profiles/.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

# Pre-compiled regex — mirrors env_loader._VAR_REF_RE
_VAR_REF_RE = re.compile(r"\$\{(\w+)(?::-(.*))?\}")


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
            # Use `in` check — empty-string values are valid overrides
            if varname in context:
                resolved = context[varname]
            elif varname in os.environ:
                resolved = os.environ[varname]
            else:
                resolved = None
            if resolved is not None:
                return resolved
            if default is not None:
                return default
            eprint(f"[WARN] env var ${{{varname}}} referenced but not set (empty)")
            return ""

        result[key] = _VAR_REF_RE.sub(_sub, raw_val)
    return result


def load_profile_env(
    profile_name: str,
    profiles_path: Path,
    base_env: Dict[str, str],
    mode: str | None = None,
    profiles: Dict[str, Any] | None = None,
) -> Dict[str, str]:
    """Load a named profile's env vars, resolving ${VAR} references from base_env.

    If *mode* is provided ("sandbox" | "local"), mode-specific env overrides
    (profile.{mode}.env) are merged on top of the base env with inheritance.

    If *profiles* is provided, it is used directly — avoids re-reading the
    profiles file when the caller has already loaded it.

    Returns the merged env dict for the profile.
    """
    if profiles is None:
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

    # Apply mode-specific overrides (sandbox or local)
    if mode is not None:
        _merge_mode_env(merged, profile_def, profiles, profile_name, mode, base_env)

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


def _merge_mode_env(
    merged: Dict[str, str],
    profile_def: dict,
    profiles: dict,
    profile_name: str,
    mode: str,
    base_env: Dict[str, str],
) -> None:
    """Merge {mode}.env overrides on top of *merged* with inheritance."""
    mode_env_def = profile_def.get(mode, {}).get("env", {})

    if profile_name in ("default", "bare"):
        # Standalone: only this profile's mode env
        if mode_env_def:
            eprint(f"[PROFILE] Applying '{mode}' overrides for '{profile_name}'...")
            merged.update(resolve_env(mode_env_def, {**base_env, **merged}))
    else:
        # Inherited: default's mode env first, then profile's overrides
        default_mode_env = profiles.get("default", {}).get(mode, {}).get("env", {})
        if default_mode_env:
            eprint(f"[PROFILE] Applying '{mode}' overrides from 'default'...")
            merged.update(resolve_env(default_mode_env, {**base_env, **merged}))
        if mode_env_def:
            eprint(f"[PROFILE] Applying '{mode}' overrides for '{profile_name}'...")
            merged.update(resolve_env(mode_env_def, {**base_env, **merged}))


def get_profile_sandbox_images(
    profile_name: str,
    profiles_path: Path,
    profiles: Dict[str, Any] | None = None,
) -> Dict[str, str]:
    """Get the sandbox_images mapping for a profile, respecting inheritance.

    Returns a dict mapping image type (\"default\", \"cuda\", \"rocm\") to image
    references.  Child profiles inherit from 'default' and can override
    individual entries. Returns an empty dict if nothing is configured.
    """
    if profiles is None:
        profiles = load_profiles(profiles_path)

    if profile_name not in profiles:
        return {}

    profile_def = profiles[profile_name]
    images = profile_def.get("sandbox_images", {})

    # Inheritance: merge default's sandbox_images, then profile overrides
    if profile_name not in ("default", "bare"):
        default_def = profiles.get("default", {})
        default_images = default_def.get("sandbox_images", {})
        merged = dict(default_images)
        merged.update(images)
        return merged

    return dict(images)


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
        sandbox_keys = list(info.get("sandbox", {}).get("env", {}).keys())
        local_keys = list(info.get("local", {}).get("env", {}).keys())
        result.append(
            {
                "name": name,
                "description": info.get("description", "No description"),
                "env_keys": env_keys,
                "sandbox_env_keys": sandbox_keys,
                "local_env_keys": local_keys,
                "standalone": name in ("default", "bare"),
            }
        )
    return result
