"""Top-level CLI entry point -- parses args and dispatches to subcommands.

Entry point: codefreedom | cf

New CLI structure (v2):
    cf agent <name> [options] [-- <agent-args>]   # Launch agent
    cf agent list                                  # List agents
    cf config <target> [options]                   # Unified config
    cf proxy start|stop|restart|status|validate    # Manage proxy
    cf tools start|stop|restart|status             # Manage tools
    cf init [--plan/--apply/--list]                # Initialize recipes
    cf admin backup|restore|list|inspect|prune     # Config management
    cf doctor [--verbose]                          # Validate environment
    cf update [--services...]                      # Check for updates
    cf deinit [--force]                            # Tear down

Aliases:
    cf px     -> cf proxy
    cf adm    -> cf admin
"""

from __future__ import annotations

import argparse
import sys

from codefreedom.log import eprint


def main() -> None:
    """Top-level CLI entry point: codefreedom | cf."""
    parser = argparse.ArgumentParser(
        prog="codefreedom",
        description=(
            "CodeFreedom — Unified CLI for code agents. "
            "LLM proxy routing, Docker sandboxing, profile management. "
            "All config in ~/.codefreedom."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", title="commands")

    # ── agent subcommand ─────────────────────────────────────────────────
    agent_parser = subparsers.add_parser(
        "agent",
        help="Launch coding agents (claude, mimo, ...)",
        description="Launch and manage coding agents with profile-based routing.",
    )
    from codefreedom.cli.agent import build_parser as build_agent_parser

    build_agent_parser(agent_parser)

    # ── config subcommand ────────────────────────────────────────────────
    config_parser = subparsers.add_parser(
        "config",
        help="Generate configuration for targets (claude, mimo, vscode)",
        description="Unified configuration generation for all targets.",
    )
    from codefreedom.cli.config import build_parser as build_config_parser

    build_config_parser(config_parser)

    # ── init subcommand (flattened) ──────────────────────────────────────
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize CodeFreedom config via recipes",
        description=(
            "Initialize CodeFreedom configuration via recipes. "
            "Without flags, installs the _default base recipe."
        ),
    )
    init_group = init_parser.add_mutually_exclusive_group()
    init_group.add_argument(
        "--plan",
        type=str,
        metavar="NAME",
        help="Preview a recipe: generate .patch files without applying",
    )
    init_group.add_argument(
        "--apply",
        type=str,
        metavar="PLAN_ID",
        help="Apply a previously generated plan by ID",
    )
    init_group.add_argument(
        "--list",
        action="store_true",
        help="List all available recipes from the repository",
    )
    init_parser.add_argument(
        "--store",
        type=str,
        metavar="URL_OR_PATH",
        default=None,
        help="Custom recipe store: GitHub URL or local folder path",
    )
    init_parser.add_argument(
        "--staging",
        action="store_true",
        help="Use recipes from the 'staging' branch instead of 'main'",
    )

    # ── proxy subcommand ─────────────────────────────────────────────────
    proxy_parser = subparsers.add_parser(
        "proxy",
        aliases=["px"],
        help="Manage the LLM proxy (start, stop, status, validate)",
        description=(
            "Manage the LLM proxy lifecycle. The proxy always runs via "
            "`docker compose` against ~/.codefreedom/proxy/docker-compose.yaml."
        ),
    )
    proxy_sub = proxy_parser.add_subparsers(dest="action", title="actions")
    proxy_sub.required = False
    proxy_sub.add_parser(
        "status",
        help="Show proxy status",
        description="Show whether the proxy is running and on which port.",
    )
    proxy_parser.set_defaults(action="status")

    start_parser = proxy_sub.add_parser(
        "start",
        help="Start the proxy (Docker Compose)",
        description=(
            "Start the proxy via `docker compose up -d`. The proxy runs "
            "inside the `codefreedom:litellm-latest` image."
        ),
    )
    start_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to publish on the host (sets LITELLM_PORT for this run only)",
    )
    start_parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Host bind address (sets LITELLM_BIND_HOST for this run only)",
    )

    proxy_sub.add_parser(
        "stop",
        help="Stop the proxy",
        description="Stop the running proxy Docker Compose stack.",
    )
    proxy_sub.add_parser(
        "restart",
        help="Restart the proxy (Docker Compose)",
        description="Restart the proxy via `docker compose restart`.",
    )
    proxy_sub.add_parser(
        "validate",
        help="Validate proxy configuration",
        description="Validate the proxy configuration file (config.yaml).",
    )

    # ── tools subcommand ─────────────────────────────────────────────────
    tools_parser = subparsers.add_parser(
        "tools",
        help="Manage auxiliary tools (Chrome, web search, GitHub MCP, web bridge)",
        description=(
            "Manage all auxiliary tools as a group. "
            "Tools are auto-started by 'cf proxy start' when needed."
        ),
    )
    tools_parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["start", "stop", "restart", "status"],
        help="Action to perform on all tools (default: status)",
    )

    # ── admin subcommand ─────────────────────────────────────────────────
    admin_parser = subparsers.add_parser(
        "admin",
        aliases=["adm"],
        help="Backup, restore, list, inspect, and prune configuration",
    )
    from codefreedom.cli.admin import build_parser as build_admin_parser

    build_admin_parser(admin_parser)

    # ── doctor subcommand ────────────────────────────────────────────────
    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Validate the full CodeFreedom environment",
        description=(
            "Run comprehensive diagnostics on your CodeFreedom setup. "
            "Checks config files, Docker availability, profiles, and proxy status."
        ),
    )
    doctor_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed information for all checks (not just failures)",
    )

    # ── update subcommand ────────────────────────────────────────────────
    update_parser = subparsers.add_parser(
        "update",
        help="Check Docker images and PyPI package for updates",
        description=(
            "Check CodeFreedom-managed Docker images and the installed PyPI "
            "package for available updates."
        ),
    )
    update_parser.add_argument(
        "services",
        nargs="*",
        metavar="SERVICE",
        help="Filter by service: sandbox, chrome, web, proxy, tools, all (default)",
    )

    # ── deinit subcommand ────────────────────────────────────────────────
    deinit_parser = subparsers.add_parser(
        "deinit",
        help="Tear down CodeFreedom: stop containers and remove config",
        description=(
            "Fully tear down CodeFreedom configuration. Stops all managed "
            "Docker containers, then prompts for confirmation before deleting "
            "the entire CodeFreedom home directory (~/.codefreedom/)."
        ),
    )
    deinit_parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt before removing the CodeFreedom directory",
    )

    # ══════════════════════════════════════════════════════════════════════
    # Argument parsing & dispatch
    # ══════════════════════════════════════════════════════════════════════

    args, unknown = parser.parse_known_args()

    # ── Helper: lazy-import-and-run pattern ──────────────────────────────
    def _dispatch(module: str, fn: str, *fn_args, **fn_kwargs) -> None:
        if unknown:
            eprint(f"[ERROR] Unrecognized arguments: {' '.join(unknown)}")
            sys.exit(2)
        import importlib

        mod = importlib.import_module(module)
        sys.exit(getattr(mod, fn)(*fn_args, **fn_kwargs))

    # ── agent subcommand ─────────────────────────────────────────────────
    if args.command == "agent":
        from codefreedom.cli.agent import handle_args

        # Forward unknown args as agent_args
        agent_name = getattr(args, "agent_name", None)
        if agent_name and agent_name != "list":
            args.agent_args = unknown
        elif unknown:
            eprint(f"[ERROR] Unrecognized arguments: {' '.join(unknown)}")
            sys.exit(2)
        sys.exit(handle_args(args))

    # ── config subcommand ────────────────────────────────────────────────
    if args.command == "config":
        from codefreedom.cli.config import handle_args

        sys.exit(handle_args(args))

    # ── init subcommand (flattened) ──────────────────────────────────────
    if args.command == "init":
        if unknown:
            eprint(f"[ERROR] Unrecognized arguments: {' '.join(unknown)}")
            sys.exit(2)

        store = getattr(args, "store", None)
        staging = getattr(args, "staging", False)

        if args.list:
            from codefreedom.cli.recipe import list_recipes

            sys.exit(list_recipes(store=store, staging=staging))
        if args.apply:
            from codefreedom.cli.recipe import apply_plan

            sys.exit(apply_plan(args.apply))
        if args.plan:
            from codefreedom.cli.recipe import plan_recipe

            sys.exit(plan_recipe(args.plan, store=store, staging=staging))

        # No flags → install _default base recipe
        from codefreedom.cli.recipe import init_recipe

        sys.exit(init_recipe("_default", store=store, staging=staging))

    # ── proxy subcommand ─────────────────────────────────────────────────
    if args.command in ("proxy", "px"):
        _dispatch("codefreedom.cli.proxy", "run", args)

    # ── tools subcommand ─────────────────────────────────────────────────
    if args.command == "tools":
        _dispatch("codefreedom.cli.tools", "run", args)

    # ── admin subcommand ─────────────────────────────────────────────────
    if args.command in ("admin", "adm"):
        _dispatch("codefreedom.cli.admin", "run", args)

    # ── doctor subcommand ────────────────────────────────────────────────
    if args.command == "doctor":
        _dispatch("codefreedom.cli.doctor", "run", verbose=args.verbose)

    # ── update subcommand ────────────────────────────────────────────────
    if args.command == "update":
        _dispatch("codefreedom.cli.update", "run", args)

    # ── deinit subcommand ────────────────────────────────────────────────
    if args.command == "deinit":
        _dispatch("codefreedom.cli.deinit", "run", args)

    # ── Fallback ─────────────────────────────────────────────────────────
    parser.print_help()
    sys.exit(0)


if __name__ == "__main__":
    main()
