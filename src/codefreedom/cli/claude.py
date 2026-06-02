"""Code agent subcommand — launch with profile-based routing and sandboxing.

Usage:
    codefreedom claude [--profile NAME] [--sandbox] [--stop|--status|--list-profiles] [agent-args...]
    cf cc [same]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from codefreedom.env_loader import eprint, load_env_chain
from codefreedom.launcher import run_docker, run_local, status, stop
from codefreedom.profiles import (
    get_profile_sandbox_image,
    list_profiles,
    load_profile_env,
    load_profiles,
)

# Default location for profiles — ~/.codefreedom/profiles/claude-code.json
# Can be overridden with CODEFREEDOM_PROFILES_FILE env var
import os as _os

_CODEFREEDOM_DIR = Path.home() / ".codefreedom"

DEFAULT_PROFILES_FILE = _os.environ.get(
    "CODEFREEDOM_PROFILES_FILE",
    str(_CODEFREEDOM_DIR / "profiles" / "claude-code.json"),
)


def run(args: argparse.Namespace) -> int:
    """Execute the claude subcommand. Returns exit code."""

    # Fast-path flags (no env loading needed)
    if args.list_profiles:
        profiles_path = _resolve_profiles_path()
        profiles = list_profiles(profiles_path)
        if not profiles:
            eprint("[PROFILES] No profiles found.")
            return 0
        eprint(f"[PROFILES] Available profiles ({profiles_path}):\n")
        for p in profiles:
            override_word = "override" if len(p["env_keys"]) == 1 else "overrides"
            inheritance = (
                "standalone"
                if p["standalone"]
                else f"inherits from 'default' — {len(p['env_keys'])} {override_word}"
            )
            eprint(f"  {p['name']}")
            eprint(f"    {p['description']}")
            eprint(f"    ({inheritance})")
            if p["env_keys"]:
                keys_summary = ", ".join(p["env_keys"][:5])
                if len(p["env_keys"]) > 5:
                    keys_summary += ", …"
                eprint(f"    sets: {keys_summary}")
            if p.get("sandbox_env_keys"):
                eprint(f"    sandbox: {', '.join(p['sandbox_env_keys'])}")
            if p.get("local_env_keys"):
                eprint(f"    local: {', '.join(p['local_env_keys'])}")
            eprint()
        return 0

    if args.status:
        return status()

    if args.stop:
        return stop()

    # ── Load env chain ─────────────────────────────────────────────────────
    workspace_dir = Path.cwd()
    eprint("[ENV] Loading configuration...")
    base_env = load_env_chain(workspace_dir)

    # ── Load profile ───────────────────────────────────────────────────────
    profile_name = args.profile or "default"
    profiles_path = _resolve_profiles_path()

    profile_env: dict = {}
    sandbox_image: str | None = None
    mode = "sandbox" if args.sandbox else "local"
    if profiles_path.exists():
        profiles = load_profiles(profiles_path)
        profile_env = load_profile_env(
            profile_name, profiles_path, base_env, mode, profiles=profiles
        )
        sandbox_image = get_profile_sandbox_image(
            profile_name, profiles_path, profiles=profiles
        )
    elif profile_name != "default":
        eprint(
            f"[ERROR] Profile '{profile_name}' requested but no profiles file found."
        )
        return 1
    else:
        eprint("[PROFILE] No profiles file found. Using defaults only.")

    # ── Route execution ────────────────────────────────────────────────────
    if args.native_models:
        # Strip proxy-auth env vars so Claude Code uses its native /login auth
        _NATIVE_STRIP_VARS = {
            "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_BASE_URL",
            "IS_SANDBOX",
        }
        for var in _NATIVE_STRIP_VARS:
            if var in profile_env:
                eprint(
                    f"[NATIVE] Stripping '{var}' — using native Anthropic /login auth"
                )
                del profile_env[var]

    dangerously_skip = getattr(args, "dangerously_skip_permissions", False)

    if args.sandbox:
        return run_docker(
            profile_env, args.claude_args, workspace_dir, profile_name, sandbox_image
        )
    else:
        return run_local(profile_env, args.claude_args, dangerously_skip)


def _resolve_profiles_path() -> Path:
    """Return the profiles path (~/.codefreedom/profiles/claude-code.json)."""
    if _os.environ.get("CODEFREEDOM_PROFILES_FILE"):
        return Path(_os.environ["CODEFREEDOM_PROFILES_FILE"])
    return _CODEFREEDOM_DIR / "profiles" / "claude-code.json"
