"""Profile management for model selection and routing across code agents.

Profiles are defined in claude-code-profiles.yaml. Each profile sets
environment variables that control model selection, API endpoint, and auth.
All profiles live in ~/.codefreedom/profiles/.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml
from pydantic import ValidationError

from codefreedom.log import eprint
from codefreedom.core.interpolate import resolve_env_vars
from codefreedom.schemas.profiles import ClaudeCodeProfiles


class ProfileError(Exception):
    """Raised when a profile cannot be loaded or is invalid."""


def load_profiles(profiles_path: Path) -> Dict[str, Any]:
    """Load and validate the profiles YAML file."""
    if not profiles_path.exists():
        eprint(f"[ERROR] Profiles file not found: {profiles_path}")
        raise ProfileError(f"Profiles file not found: {profiles_path}")

    try:
        with open(profiles_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        eprint(f"[ERROR] Invalid YAML in {profiles_path}: {e}")
        raise ProfileError(f"Invalid YAML in {profiles_path}: {e}") from e

    if not isinstance(data, dict):
        eprint(
            f"[ERROR] Expected a mapping in {profiles_path}, got {type(data).__name__}"
        )
        raise ProfileError(f"Expected a mapping in {profiles_path}")

    # NOTE: Do NOT interpolate ${VAR} references here.  load_profiles() runs
    # BEFORE the env chain (load_env_chain) has resolved CF_CLI_* overrides,
    # so variables like ${LITELLM_MASTER_KEY} would resolve to empty because
    # only CF_CLI_LITELLM_MASTER_KEY is in os.environ.  Interpolation is
    # handled downstream by load_profile_env's resolve_env() which receives
    # the fully-resolved base_env context.

    # Validate with Pydantic (non-fatal — warn on failure, allow extra fields)
    try:
        ClaudeCodeProfiles.model_validate(data, strict=False)
    except ValidationError as exc:
        eprint(f"[WARN] Profiles validation issue in {profiles_path}: {exc}")

    profiles = data.get("profiles", {})
    if not profiles:
        eprint("[ERROR] No profiles defined in profiles file.")
        raise ProfileError("No profiles defined in profiles file.")

    return profiles


def resolve_env(env_def: Dict[str, str], context: Dict[str, str]) -> Dict[str, str]:
    """Resolve ${VAR} references in env values using a context dict."""
    return {key: resolve_env_vars(val, context) for key, val in env_def.items()}


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
        raise ProfileError(f"Profile '{profile_name}' not found.")

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


def get_profile_tools(
    profile_name: str,
    profiles_path: Path,
    profiles: Dict[str, Any] | None = None,
) -> List[str]:
    """Get the tools list for a profile, respecting inheritance.

    Merges default's tools with the child profile's tools (deduplicated,
    order-preserving).  'bare' is standalone — does not inherit from default.
    Returns an empty list if no tools are declared.
    """
    if profiles is None:
        profiles = load_profiles(profiles_path)

    if profile_name not in profiles:
        return []

    profile_def = profiles[profile_name]
    tools: List[str] = list(profile_def.get("tools", []))

    if profile_name in ("default", "bare"):
        return tools

    # Inherit default's tools, then append profile's own (deduplicated)
    default_def = profiles.get("default", {})
    default_tools: List[str] = list(default_def.get("tools", []))
    merged = list(default_tools)
    for t in tools:
        if t not in merged:
            merged.append(t)
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
        sandbox_keys = list(info.get("sandbox", {}).get("env", {}).keys())
        local_keys = list(info.get("local", {}).get("env", {}).keys())
        result.append(
            {
                "name": name,
                "description": info.get("description", "No description"),
                "env_keys": env_keys,
                "sandbox_env_keys": sandbox_keys,
                "local_env_keys": local_keys,
                "tools": info.get("tools", []),
                "standalone": name in ("default", "bare"),
            }
        )
    return result
