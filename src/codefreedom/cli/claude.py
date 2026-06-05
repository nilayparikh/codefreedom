"""Code agent subcommand — launch with profile-based routing and sandboxing.

Usage:
    codefreedom claude [--profile NAME] [--sandbox] [--stop|--status|--list-profiles] [agent-args...]
    codefreedom claude init
    cf cc [same]

VS Code integration: see `codefreedom vscode claude config`.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from codefreedom.cli.init_utils import find_bundled_examples
from codefreedom.cli.tool_init_utils import _print_non_disclaimer
from codefreedom.config import get_codefreedom_dir
from codefreedom.env_loader import eprint, load_env_chain
from codefreedom.launcher import run_docker, run_local, status, stop
from codefreedom.profiles import (
    ProfileError,
    get_profile_sandbox_images,
    get_profile_tools,
    list_profiles,
    load_profile_env,
    load_profiles,
)
from codefreedom.tool_registry import acquire_tools, generate_session_id, release_tools

# Default location for profiles — ~/.codefreedom/profiles/claude-code.json
# Can be overridden with CODEFREEDOM_PROFILES_FILE env var
import os


def _get_cf_dir() -> Path:
    """Lazy accessor for the CodeFreedom config directory (test-patchable)."""
    return get_codefreedom_dir()


def init_claude() -> int:
    """Initialize Claude Code profiles and .env.claude from bundled examples.

    Only copies files into an empty target — if any config already exists,
    directs user to docs and example configs for manual merging.
    """
    bundled = find_bundled_examples(__file__)
    claude_src = bundled / "claude"
    profiles_src = claude_src / "profiles"

    cf_dir = _get_cf_dir()
    profiles_dst_dir = cf_dir / "profiles"

    # Collect all source→destination pairs
    pairs: list[tuple[Path, Path]] = [
        (profiles_src / "claude-code.json", profiles_dst_dir / "claude-code.json"),
        (
            profiles_src / "claude-code.schema.json",
            profiles_dst_dir / "claude-code.schema.json",
        ),
        (claude_src / ".env.claude.example", cf_dir / ".env.claude"),
        (claude_src / ".env.claude.secrets.example", cf_dir / ".env.claude.secrets"),
    ]

    # All-or-nothing check: if any destination file exists, skip everything
    existing = [dst for _, dst in pairs if dst.exists()]
    if existing:
        print(
            "[claude init] Config already exists — init only bootstraps clean directories."
        )
        print(
            "              Docs:    https://nilayparikh.github.io/codefreedom/claude-code/local/"
        )
        print(
            "              Example: https://github.com/nilayparikh/codefreedom/tree/main/src/codefreedom/examples/claude/"
        )
        print("              Please merge changes manually.")
        print()
        _print_non_disclaimer()
        return 0

    # Nothing exists -- copy all, with rollback on failure
    created: list[Path] = []
    try:
        for src, dst in pairs:
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                created.append(dst)
                print(f"[claude init] [CREATE] {dst}")
            else:
                print(f"[claude init] [MISSING] Source not found: {src}")
    except OSError as exc:
        eprint(f"[claude init] [ERROR] Copy failed: {exc}. Rolling back.")
        for path in created:
            try:
                path.unlink()
            except OSError:
                pass
        return 1

    # ── Summary ─────────────────────────────────────────────────────────
    print()
    if created:
        print(f"[claude init] Done -- {len(created)} created.")
    print(
        "              Configure: https://nilayparikh.github.io/codefreedom/claude-code/local/"
    )
    _print_non_disclaimer()
    return 0


# VS Code settings generation moved to codefreedom.cli.vscode.


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
            if p.get("tools"):
                eprint(f"    tools: {', '.join(p['tools'])}")
            eprint()
        return 0

    if args.status:
        return status()

    if args.stop:
        return stop()

    # ── Load env chain ─────────────────────────────────────────────────────
    workspace_dir = Path.cwd()
    eprint("[ENV] Loading configuration...")
    base_env = load_env_chain(workspace_dir, component="claude")

    # ── GPU type from --cuda / --rocm flags ────────────────────────────────
    gpu_type: str | None = None
    if getattr(args, "gpu_cuda", False):
        gpu_type = "cuda"
    elif getattr(args, "gpu_rocm", False):
        gpu_type = "rocm"

    # ── Load profile ───────────────────────────────────────────────────────
    profile_name = args.profile or "default"
    profiles_path = _resolve_profiles_path()

    profile_env: dict = {}
    sandbox_images: dict[str, str] = {}
    tools: list[str] = []
    mode = "sandbox" if args.sandbox else "local"
    if profiles_path.exists():
        try:
            profiles_dict = load_profiles(profiles_path)
            profile_env = load_profile_env(
                profile_name, profiles_path, base_env, mode, profiles=profiles_dict
            )
            sandbox_images = get_profile_sandbox_images(
                profile_name, profiles_path, profiles=profiles_dict
            )
            tools = get_profile_tools(
                profile_name, profiles_path, profiles=profiles_dict
            )
        except ProfileError as e:
            eprint(f"[ERROR] {e}")
            return 1
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
    run_as_me = getattr(args, "run_as_me", False)

    # ── Tool lifecycle (acquire before, release after) ───────────────────
    session_id = generate_session_id(mode)
    acquired_tools: list[str] = []
    if tools:
        eprint(f"[TOOLS] Profile '{profile_name}' declares tools: {', '.join(tools)}")
        acquired_tools = acquire_tools(session_id, tools, profile_name)
        if acquired_tools:
            eprint(f"[TOOLS] Acquired: {', '.join(acquired_tools)}")

    try:
        if args.sandbox:
            # --run-as-me is only meaningful with --sandbox; silently ignore otherwise
            return run_docker(
                profile_env,
                args.claude_args,
                workspace_dir,
                profile_name,
                gpu_type=gpu_type,
                sandbox_images=sandbox_images,
                run_as_me=run_as_me,
                container_name=session_id,
                acquired_tools=acquired_tools,
            )
        else:
            if run_as_me:
                eprint("[WARN] --run-as-me is only valid with --sandbox; ignoring.")
            return run_local(profile_env, args.claude_args, dangerously_skip)
    finally:
        if acquired_tools:
            eprint(f"[TOOLS] Releasing: {', '.join(acquired_tools)}")
            release_tools(session_id, acquired_tools)


def _resolve_profiles_path() -> Path:
    """Return the profiles path (~/.codefreedom/profiles/claude-code.json)."""
    override = os.environ.get("CODEFREEDOM_PROFILES_FILE")
    if override:
        return Path(override)
    return _get_cf_dir() / "profiles" / "claude-code.json"
