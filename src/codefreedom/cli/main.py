"""Top-level CLI entry point -- parses args and dispatches to subcommands.

Entry point: codefreedom | cf
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

_CODEFREEDOM_DIR = Path.home() / ".codefreedom"


def _find_project_root() -> Path:
    """Find the project root directory (where profiles.examples/ and litellm.examples/ live)."""
    return Path(__file__).resolve().parent.parent.parent.parent


def _find_bundled_examples() -> Path:
    """Find the bundled examples directory inside the installed package."""
    return Path(__file__).resolve().parent.parent / "examples"


def _init_codefreedom(
    force: bool = False,
    project_root: Path | None = None,
    cf_dir: Path | None = None,
) -> int:
    """Initialize ~/.codefreedom/ with default profiles and proxy configs.

    Copies from the project's examples directories (profiles.examples/
    and litellm.examples/) or from the bundled package examples into
    ~/.codefreedom/.

    Args:
        force: Overwrite existing files.
        project_root: Override the project root (for testing).
        cf_dir: Override the ~/.codefreedom directory (for testing).
    """
    if project_root is None:
        project_root = _find_project_root()
    if cf_dir is None:
        cf_dir = _CODEFREEDOM_DIR

    bundled = _find_bundled_examples()

    profiles_src = project_root / "profiles.examples" / "claude-code-profiles.json"
    schema_src = project_root / "profiles.examples" / "claude-code-profiles.schema.json"
    proxy_src = project_root / "litellm.examples"

    # Fall back to bundled examples if project-root sources don't exist
    if not profiles_src.exists():
        profiles_src = bundled / "profiles" / "claude-code-profiles.json"
    if not schema_src.exists():
        schema_src = bundled / "profiles" / "claude-code-profiles.schema.json"
    if not proxy_src.exists():
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
    elif profiles_src.exists():
        profiles_dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(profiles_src, profiles_dst)
        print(f"[init] [OK] Created {profiles_dst}")
        created_any = True
    else:
        print(f"[init] [FAIL] Profiles example not found: {profiles_src}")
        print("       Make sure profiles.examples/claude-code-profiles.json exists.")

    # ── Schema ─────────────────────────────────────────────────────────────
    if not force and schema_dst.exists():
        print(f"[init] Schema already exists: {schema_dst}")
        skipped_any = True
    elif schema_src.exists():
        profiles_dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(schema_src, schema_dst)
        print(f"[init] [OK] Created {schema_dst}")
        created_any = True
    else:
        print(f"[init] [FAIL] Schema example not found: {schema_src}")
        print(
            "       Make sure profiles.examples/claude-code-profiles.schema.json exists."
        )

    # ── Proxy configs (litellm) ─────────────────────────────────────────────
    if not force and proxy_dst.exists():
        print(f"[init] Proxy configs already exist: {proxy_dst}")
        print("       Use --init --force to overwrite.")
        skipped_any = True
    elif proxy_src.exists():
        if proxy_dst.exists() and force:
            shutil.rmtree(proxy_dst)

        # Source layout (litellm.examples/ or bundled proxy/):
        #   config.yaml          → proxy/config/config.yaml
        #   docker-compose.yml   → proxy/docker-compose.yml
        #   providers/           → proxy/config/providers/
        proxy_config_dir = proxy_dst / "config"
        proxy_config_dir.mkdir(parents=True, exist_ok=True)

        # Copy config.yaml into config/ subdirectory
        src_config = proxy_src / "config.yaml"
        if src_config.exists():
            shutil.copy2(src_config, proxy_config_dir / "config.yaml")

        # Copy docker-compose.yml to proxy root
        src_compose = proxy_src / "docker-compose.yml"
        if src_compose.exists():
            shutil.copy2(src_compose, proxy_dst / "docker-compose.yml")

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
        print(f"[init] [FAIL] Proxy examples not found: {proxy_src}")
        print("       Make sure litellm.examples/ exists.")

    # ── Environment files (.env / .env.secrets) ────────────────────────────
    # Copy fully-commented templates from project root or bundled examples.
    # These are only created if the destination file doesn't already exist
    # (never overwritten -- user edits them manually).
    env_src = project_root / ".env.example"
    secrets_src = project_root / ".env.secrets.example"

    if not env_src.exists():
        env_src = bundled / ".env.example"
    if not secrets_src.exists():
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
        print(f"[init] [FAIL] .env.example not found: {env_src}")

    # .env.secrets is optional -- only copy if source exists and dest doesn't
    if secrets_dst.exists():
        print(f"[init] .env.secrets already exists: {secrets_dst} (skipping)")
    elif secrets_src.exists():
        cf_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(secrets_src, secrets_dst)
        print(f"[init] [OK] Created {secrets_dst} (fully commented -- add your API keys)")
        created_any = True

    if created_any:
        print()
        print("[init] CodeFreedom is initialized!")
        print(f"       Profiles: {profiles_dst_dir}")
        print(f"         - claude-code.json")
        print(f"         - claude-code-profiles.schema.json")
        print(f"       Proxy:    {proxy_dst}")
        print(f"       Env:      {cf_dir}")
        print(f"         - .env (fully commented)")
        print(f"         - .env.secrets (fully commented)")
        print("       Edit these files to customize your setup.")
    elif skipped_any:
        print()
        print("[init] Nothing to do -- all files already exist.")
    else:
        print()
        print("[init] No source files found to copy.")

    return 0


def main() -> None:
    """Top-level CLI entry point: codefreedom | cf."""
    parser = argparse.ArgumentParser(
        prog="codefreedom",
        description="CodeFreedom -- Claude Code launcher and LiteLLM proxy management.",
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
        help="Launch Claude Code with profile-based model routing",
        description="Run Claude Code natively (default) or in a sandboxed Docker container.",
    )
    claude_parser.add_argument(
        "--sandbox",
        action="store_true",
        help="Run Claude Code inside a sandboxed Docker container (default: native)",
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
        "claude_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to the 'claude' CLI",
    )

    # ── proxy subcommand ───────────────────────────────────────────────────
    proxy_parser = subparsers.add_parser(
        "proxy",
        aliases=["px"],
        help="Manage the LiteLLM proxy (start, stop, validate, status)",
        description="Manage the LiteLLM proxy lifecycle.",
    )
    proxy_parser.add_argument(
        "--up",
        action="store_true",
        help="Start the LiteLLM proxy (native by default; use --docker for Compose)",
    )
    proxy_parser.add_argument(
        "--down",
        action="store_true",
        help="Stop the LiteLLM proxy",
    )
    proxy_parser.add_argument(
        "--status",
        action="store_true",
        help="Show LiteLLM proxy status",
    )
    proxy_parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate the LiteLLM configuration",
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

    args = parser.parse_args()

    # ── --init: bootstrap ~/.codefreedom/ ───────────────────────────────────
    if args.init:
        sys.exit(_init_codefreedom(force=args.force))

    if args.command in ("claude", "cc"):
        # Lazy import to keep CLI startup fast
        from codefreedom.cli.claude import run as claude_run

        sys.exit(claude_run(args))
    elif args.command in ("proxy", "px"):
        from codefreedom.cli.proxy import run as proxy_run

        sys.exit(proxy_run(args))
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
