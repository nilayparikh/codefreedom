"""Top-level CLI entry point — parses args and dispatches to subcommands.

Entry point: codefreedom | cf
"""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    """Top-level CLI entry point: codefreedom | cf."""
    parser = argparse.ArgumentParser(
        prog="codefreedom",
        description="CodeFreedom — Claude Code launcher and LiteLLM proxy management.",
    )
    subparsers = parser.add_subparsers(dest="command", title="commands")

    # ── claude subcommand ──────────────────────────────────────────────────
    claude_parser = subparsers.add_parser(
        "claude",
        aliases=["cc"],
        help="Launch Claude Code with profile-based model routing",
        description="Run Claude Code in a persistent Docker container (default) or natively.",
    )
    claude_parser.add_argument(
        "--local",
        action="store_true",
        help="Run Claude Code natively (no Docker container)",
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
        help="Start the LiteLLM proxy via Docker Compose",
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
        "--native",
        action="store_true",
        help="Run litellm directly as Python process (not Docker)",
    )
    proxy_parser.add_argument(
        "--port",
        type=int,
        default=4000,
        help="Port for native mode (default: 4000)",
    )
    proxy_parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Bind host for native mode (default: 0.0.0.0)",
    )

    args = parser.parse_args()

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
