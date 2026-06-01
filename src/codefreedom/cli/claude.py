"""Claude Code subcommand — launch Claude Code with profile-based routing.

Usage:
    codefreedom claude [--profile NAME] [--local] [--stop|--status|--list-profiles] [claude-args...]
    cf cc [same]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from codefreedom.env_loader import eprint, load_env_chain
from codefreedom.launcher import run_docker, run_local, status, stop
from codefreedom.profiles import list_profiles, load_profile_env

# Default locations for profiles file — searched in order:
#   1. profiles/claude-code-profiles.json (project profiles dir)
#   2. claude-code-profiles.json (workspace root — legacy)
# Can be overridden with CODEFREEDOM_PROFILES_FILE env var
import os as _os

DEFAULT_PROFILES_FILE = _os.environ.get(
    "CODEFREEDOM_PROFILES_FILE",
    "profiles/claude-code-profiles.json",
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
    if profiles_path.exists():
        profile_env = load_profile_env(profile_name, profiles_path, base_env)
    elif profile_name != "default":
        eprint(
            f"[ERROR] Profile '{profile_name}' requested but no profiles file found."
        )
        return 1
    else:
        eprint("[PROFILE] No profiles file found. Using defaults only.")

    # ── Route execution ────────────────────────────────────────────────────
    if args.local:
        return run_local(profile_env, args.claude_args)
    else:
        return run_docker(profile_env, args.claude_args, workspace_dir)


def _resolve_profiles_path() -> Path:
    """Find the profiles file, trying multiple locations."""
    candidates = [
        Path(DEFAULT_PROFILES_FILE),  # primary (profiles/ dir)
        Path("claude-code-profiles.json"),  # legacy (cwd root)
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    # Return primary so error messages show the preferred path
    return Path(DEFAULT_PROFILES_FILE)
