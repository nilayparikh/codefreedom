"""Top-level CLI entry point -- parses args and dispatches to subcommands.

Entry point: codefreedom | cf
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from codefreedom.env_loader import eprint

_CODEFREEDOM_DIR = Path.home() / ".codefreedom"


def _find_bundled_examples() -> Path:
    """Find the bundled examples directory inside the installed package."""
    return Path(__file__).resolve().parent.parent / "examples"


def _init_codefreedom(
    force: bool = False,
    cf_dir: Path | None = None,
) -> int:
    """Initialize ~/.codefreedom/ with default profiles and proxy configs.

    Copies from the bundled package examples into ~/.codefreedom/.
    """

    if cf_dir is None:
        cf_dir = _CODEFREEDOM_DIR

    bundled = _find_bundled_examples()

    profiles_src = bundled / "profiles"
    proxy_src = bundled / "proxy"

    profiles_dst_dir = cf_dir / "profiles"
    profiles_dst = profiles_dst_dir / "claude-code.json"
    schema_dst = profiles_dst_dir / "claude-code-profiles.schema.json"
    proxy_dst = cf_dir / "proxy"

    created_any = False
    skipped_any = False

    # ── Profiles ───────────────────────────────────────────────────────────
    if not force and profiles_dst.exists():
        print(f"[init] Profiles already exist: {profiles_dst}")
        print("       Use --init --force to overwrite.")
        skipped_any = True
    elif (profiles_src / "claude-code-profiles.json").exists():
        profiles_dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(profiles_src / "claude-code-profiles.json", profiles_dst)
        print(f"[init] [OK] Created {profiles_dst}")
        created_any = True
    else:
        print("[init] [FAIL] Bundled profiles example not found")
        print("       Reinstall the package or file a bug report.")

    # ── Schema ─────────────────────────────────────────────────────────────
    if not force and schema_dst.exists():
        print(f"[init] Schema already exists: {schema_dst}")
        skipped_any = True
    elif (profiles_src / "claude-code-profiles.schema.json").exists():
        profiles_dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(profiles_src / "claude-code-profiles.schema.json", schema_dst)
        print(f"[init] [OK] Created {schema_dst}")
        created_any = True
    else:
        print("[init] [FAIL] Bundled schema example not found")
        print("       Reinstall the package or file a bug report.")

    # ── Proxy configs ──────────────────────────────────────────────────────
    if not force and proxy_dst.exists():
        print(f"[init] Proxy configs already exist: {proxy_dst}")
        print("       Use --init --force to overwrite.")
        skipped_any = True
    elif proxy_src.exists():
        if proxy_dst.exists() and force:
            shutil.rmtree(proxy_dst)

        proxy_config_dir = proxy_dst / "config"
        proxy_config_dir.mkdir(parents=True, exist_ok=True)

        # Copy config.yaml into config/ subdirectory
        src_config = proxy_src / "config.yaml"
        if src_config.exists():
            shutil.copy2(src_config, proxy_config_dir / "config.yaml")

        # Copy docker-compose.yaml to proxy root
        src_compose = proxy_src / "docker-compose.yaml"
        if src_compose.exists():
            shutil.copy2(src_compose, proxy_dst / "docker-compose.yaml")

        # Copy providers into config/providers/
        src_providers = proxy_src / "providers"
        if src_providers.exists():
            dst_providers = proxy_config_dir / "providers"
            if dst_providers.exists() and force:
                shutil.rmtree(dst_providers)
            shutil.copytree(src_providers, dst_providers, dirs_exist_ok=True)

        print(f"[init] [OK] Created {proxy_dst}")
        created_any = True
    else:
        print("[init] [FAIL] Bundled proxy examples not found")
        print("       Reinstall the package or file a bug report.")

    # ── Environment files (.env / .env.secrets) ────────────────────────────
    env_src = bundled / ".env.example"
    secrets_src = bundled / ".env.secrets.example"

    env_dst = cf_dir / ".env"
    secrets_dst = cf_dir / ".env.secrets"

    if env_dst.exists():
        print(f"[init] .env already exists: {env_dst} (skipping -- edit it manually)")
        skipped_any = True
    elif env_src.exists():
        cf_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(env_src, env_dst)
        print(
            f"[init] [OK] Created {env_dst} (fully commented -- uncomment variables you need)"
        )
        created_any = True
    else:
        print("[init] [FAIL] Bundled .env.example not found")
        print("       Reinstall the package or file a bug report.")

    # .env.secrets is optional
    if secrets_dst.exists():
        print(f"[init] .env.secrets already exists: {secrets_dst} (skipping)")
    elif secrets_src.exists():
        cf_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(secrets_src, secrets_dst)
        print(
            f"[init] [OK] Created {secrets_dst} (fully commented -- add your API keys)"
        )
        created_any = True

    if created_any:
        print()
        print("[init] CodeFreedom is initialized!")
        print(f"       Profiles: {profiles_dst_dir}")
        print("         - claude-code.json")
        print("         - claude-code-profiles.schema.json")
        print(f"       Proxy:    {proxy_dst}")
        print(f"       Env:      {cf_dir}")
        print("         - .env (fully commented)")
        print("         - .env.secrets (fully commented)")
        print("       Edit these files to customize your setup.")
    elif skipped_any:
        print()
        print("[init] Nothing to do -- all files already exist.")
    else:
        print()
        print(
            "[init] No source files found to copy. Reinstall the package or file a bug report."
        )

    return 0


def main() -> None:
    """Top-level CLI entry point: codefreedom | cf."""
    parser = argparse.ArgumentParser(
        prog="codefreedom",
        description="CodeFreedom -- Single wrapper for all code agents. Simple LLM routing, sandboxing, profile management, and isolation. All config in ~/.codefreedom.",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Initialize ~/.codefreedom/ with default profiles and proxy configs",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite existing configs (use with --init)",
    )
    subparsers = parser.add_subparsers(dest="command", title="commands")

    # ── claude subcommand ──────────────────────────────────────────────────
    claude_parser = subparsers.add_parser(
        "claude",
        aliases=["cc"],
        help="Launch code agent with profile-based model routing",
        description="Run a code agent natively (default) or in a sandboxed Docker container.",
    )
    claude_parser.add_argument(
        "--sandbox",
        action="store_true",
        help="Run inside a sandboxed Docker container (default: native)",
    )
    claude_parser.add_argument(
        "--native-models",
        action="store_true",
        help="Use native Anthropic models/auth (/login) -- strips ANTHROPIC_BASE_URL and ANTHROPIC_AUTH_TOKEN",
    )
    claude_parser.add_argument(
        "--profile",
        type=str,
        default="default",
        metavar="NAME",
        help="Load a named profile (default: 'default')",
    )
    claude_parser.add_argument(
        "--stop",
        action="store_true",
        help="Stop and remove the persistent Docker container",
    )
    claude_parser.add_argument(
        "--status",
        action="store_true",
        help="Show persistent container status and exit",
    )
    claude_parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="List available profiles and exit",
    )
    claude_parser.add_argument(
        "--dangerously-skip-permissions",
        action="store_true",
        help="Skip Claude Code permission prompts (use in CI/non-interactive environments)",
    )
    claude_parser.add_argument(
        "claude_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to the 'claude' CLI",
    )

    # ── proxy subcommand ───────────────────────────────────────────────────
    proxy_parser = subparsers.add_parser(
        "proxy",
        aliases=["px"],
        help="Manage the LLM proxy (start, stop, validate, status)",
        description="Manage the LLM proxy lifecycle (Docker or native).",
    )
    proxy_parser.add_argument(
        "--up",
        action="store_true",
        help="Start the proxy (native by default; use --docker for Compose)",
    )
    proxy_parser.add_argument(
        "--down",
        action="store_true",
        help="Stop the proxy",
    )
    proxy_parser.add_argument(
        "--status",
        action="store_true",
        help="Show proxy status",
    )
    proxy_parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate the proxy configuration",
    )
    proxy_parser.add_argument(
        "--docker",
        action="store_true",
        help="Run via Docker Compose instead of native Python",
    )
    proxy_parser.add_argument(
        "--port",
        type=int,
        default=4000,
        help="Port for proxy (default: 4000)",
    )
    proxy_parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Bind host for proxy (default: 0.0.0.0)",
    )

    args, unknown = parser.parse_known_args()

    # ── --init: bootstrap ~/.codefreedom/ ───────────────────────────────────
    if args.init:
        sys.exit(_init_codefreedom(force=args.force))

    if args.command in ("claude", "cc"):
        # ── Rescue known flags swallowed by parse_known_args ────────────────
        # When an unknown flag appears before a known flag (e.g.,
        # `--resume session --sandbox`), parse_known_args puts ALL remaining
        # args (including `--sandbox`) into the unknown list. Scan unknown for
        # CodeFreedom flags that REMAINDER would have dropped.
        _CLAUDE_BOOL_FLAGS = {
            "--sandbox": "sandbox",
            "--native-models": "native_models",
            "--stop": "stop",
            "--status": "status",
            "--list-profiles": "list_profiles",
            "--dangerously-skip-permissions": "dangerously_skip_permissions",
        }
        forwarded: list[str] = []
        _unknown_iter = iter(unknown)
        for arg in _unknown_iter:
            if arg in _CLAUDE_BOOL_FLAGS:
                setattr(args, _CLAUDE_BOOL_FLAGS[arg], True)
            elif arg == "--profile":
                try:
                    args.profile = next(_unknown_iter)
                except StopIteration:
                    forwarded.append(arg)
            else:
                forwarded.append(arg)
        # Prepend forwarded unknown args so they appear before positional
        # claude_args in the final command line.
        if args.claude_args is None:
            args.claude_args = []
        args.claude_args = forwarded + args.claude_args
        # Lazy import to keep CLI startup fast
        from codefreedom.cli.claude import run as claude_run

        sys.exit(claude_run(args))
    elif args.command in ("proxy", "px"):
        if unknown:
            eprint(f"[ERROR] Unrecognized arguments: {' '.join(unknown)}")
            sys.exit(2)
        from codefreedom.cli.proxy import run as proxy_run

        sys.exit(proxy_run(args))
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
