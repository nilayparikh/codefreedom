"""Top-level CLI entry point — parses args and dispatches to subcommands.

Entry point: codefreedom | cf

Lifecycle grouping (v3):
    cf setup init|config|deinit      # one-time setup & configuration
    cf run agent|proxy|tools          # daily workflows
    cf manage doctor|update|admin     # occasional maintenance

"""

from __future__ import annotations

import argparse
import sys

from codefreedom.log import eprint


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="codefreedom",
        description=(
            "CodeFreedom — Unified CLI for code agents. "
            "LLM proxy routing, Docker sandboxing, profile management. "
            "All config in ~/.codefreedom."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", title="commands")

    # ── setup — one-time setup and configuration ────────────────────────────
    setup_parser = subparsers.add_parser(
        "setup",
        help="One-time setup and configuration (init, config, deinit)",
    )
    setup_sub = setup_parser.add_subparsers(dest="setup_command", title="setup commands")

    # setup init
    init_parser = setup_sub.add_parser(
        "init",
        help="Initialize CodeFreedom config via recipes",
        description="Initialize CodeFreedom configuration via recipes. Without flags, installs the _default base recipe.",
    )
    _build_init_args(init_parser)

    # setup config
    config_parser = setup_sub.add_parser(
        "config",
        help="Generate configuration for targets (claude, mimo, vscode)",
    )
    from codefreedom.cli.setup.config import build_parser as build_config_parser
    build_config_parser(config_parser)

    # setup deinit
    deinit_parser = setup_sub.add_parser(
        "deinit",
        help="Tear down CodeFreedom: stop containers and remove config",
    )
    _build_deinit_args(deinit_parser)

    # ── run — daily workflows ──────────────────────────────────────────────
    run_parser = subparsers.add_parser(
        "run",
        help="Daily workflows (agent, proxy, tools)",
    )
    run_sub = run_parser.add_subparsers(dest="run_command", title="run commands")

    # run agent
    agent_parser = run_sub.add_parser(
        "agent",
        help="Launch coding agents (claude, mimo, ...)",
    )
    from codefreedom.cli.run.agent import build_parser as build_agent_parser
    build_agent_parser(agent_parser)

    # run proxy
    proxy_parser = run_sub.add_parser(
        "proxy",
        aliases=["px"],
        help="Manage the LLM proxy (start, stop, status, validate)",
    )
    _build_proxy_args(proxy_parser)

    # run tools
    tools_parser = run_sub.add_parser(
        "tools",
        help="Manage auxiliary tools (Chrome, web search, GitHub MCP, web bridge)",
    )
    _build_tools_args(tools_parser)

    # ── manage — occasional maintenance ────────────────────────────────────
    manage_parser = subparsers.add_parser(
        "manage",
        help="Occasional maintenance (doctor, update, admin)",
    )
    manage_sub = manage_parser.add_subparsers(dest="manage_command", title="manage commands")

    # manage doctor
    doctor_parser = manage_sub.add_parser(
        "doctor",
        help="Validate the full CodeFreedom environment",
    )
    _build_doctor_args(doctor_parser)

    # manage update
    update_parser = manage_sub.add_parser(
        "update",
        help="Check Docker images and PyPI package for updates",
    )
    _build_update_args(update_parser)

    # manage admin
    admin_parser = manage_sub.add_parser(
        "admin",
        aliases=["adm"],
        help="Backup, restore, list, inspect, and prune configuration",
    )
    from codefreedom.cli.manage.admin import build_parser as build_admin_parser
    build_admin_parser(admin_parser)

    # ══════════════════════════════════════════════════════════════════════
    # Argument parsing & dispatch
    # ══════════════════════════════════════════════════════════════════════

    args, unknown = parser.parse_known_args()

    def _dispatch(module: str, fn: str, *fn_args, **fn_kwargs) -> None:
        if unknown:
            eprint(f"[ERROR] Unrecognized arguments: {' '.join(unknown)}")
            sys.exit(2)
        import importlib
        mod = importlib.import_module(module)
        sys.exit(getattr(mod, fn)(*fn_args, **fn_kwargs))

    cmd = args.command

    # ── setup ──────────────────────────────────────────────────────────────
    if cmd == "setup":
        sc = args.setup_command
        if sc == "init":
            _dispatch_init(args)
        elif sc == "config":
            _dispatch_config(args)
        elif sc == "deinit":
            _dispatch_deinit(args)
        else:
            setup_parser.print_help()
            sys.exit(1)

    # ── run ────────────────────────────────────────────────────────────────
    elif cmd == "run":
        rc = args.run_command
        if rc == "agent":
            _dispatch_agent(args, unknown)
        elif rc in ("proxy", "px"):
            _dispatch("codefreedom.cli.run.proxy", "run", args)
        elif rc == "tools":
            _dispatch("codefreedom.cli.run.tools", "run", args)
        else:
            run_parser.print_help()
            sys.exit(1)

    # ── manage ─────────────────────────────────────────────────────────────
    elif cmd == "manage":
        mc = args.manage_command
        if mc == "doctor":
            _dispatch("codefreedom.cli.manage.doctor", "run", verbose=getattr(args, "verbose", False))
        elif mc == "update":
            _dispatch("codefreedom.cli.manage.update", "run", args)
        elif mc in ("admin", "adm"):
            _dispatch("codefreedom.cli.manage.admin", "run", args)
        else:
            manage_parser.print_help()
            sys.exit(1)

    # ── Fallback ───────────────────────────────────────────────────────────
    else:
        parser.print_help()
        sys.exit(0)


# ══════════════════════════════════════════════════════════════════════════════
# Parser builders for inline subcommands
# ══════════════════════════════════════════════════════════════════════════════


def _build_init_args(p: argparse.ArgumentParser) -> None:
    group = p.add_mutually_exclusive_group()
    group.add_argument("--plan", type=str, metavar="NAME", help="Preview a recipe: generate .patch files without applying")
    group.add_argument("--apply", type=str, metavar="PLAN_ID", help="Apply a previously generated plan by ID")
    group.add_argument("--list", action="store_true", help="List all available recipes from the repository")
    p.add_argument("--store", type=str, metavar="URL_OR_PATH", default=None, help="Custom recipe store: GitHub URL or local folder path")
    p.add_argument("--staging", action="store_true", help="Use recipes from the 'staging' branch instead of 'main'")


def _build_proxy_args(p: argparse.ArgumentParser) -> None:
    sub = p.add_subparsers(dest="action", title="actions")
    sub.required = False
    sub.add_parser("status", help="Show proxy status")
    p.set_defaults(action="status")
    start_p = sub.add_parser("start", help="Start the proxy (Docker Compose)")
    start_p.add_argument("--port", type=int, default=None, help="Port to publish on the host")
    start_p.add_argument("--host", type=str, default=None, help="Host bind address")
    sub.add_parser("stop", help="Stop the proxy")
    sub.add_parser("restart", help="Restart the proxy (Docker Compose)")
    sub.add_parser("validate", help="Validate proxy configuration")


def _build_tools_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("action", nargs="?", default="status", choices=["start", "stop", "restart", "status"])


def _build_doctor_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--verbose", action="store_true", help="Show detailed information for all checks")


def _build_update_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("services", nargs="*", metavar="SERVICE", help="Filter by service: sandbox, chrome, web, proxy, tools, all (default)")


def _build_deinit_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--force", action="store_true", help="Skip confirmation prompt before removing the CodeFreedom directory")


# ══════════════════════════════════════════════════════════════════════════════
# Dispatch helpers
# ══════════════════════════════════════════════════════════════════════════════


def _dispatch_agent(args, unknown) -> None:
    from codefreedom.cli.run.agent import handle_args
    agent_name = getattr(args, "agent_name", None)
    if agent_name and agent_name != "list":
        args.agent_args = unknown
    elif unknown:
        eprint(f"[ERROR] Unrecognized arguments: {' '.join(unknown)}")
        sys.exit(2)
    sys.exit(handle_args(args))


def _dispatch_config(args) -> None:
    from codefreedom.cli.setup.config import handle_args
    sys.exit(handle_args(args))


def _dispatch_init(args) -> None:
    store = getattr(args, "store", None)
    staging = getattr(args, "staging", False)

    if getattr(args, "list", False):
        from codefreedom.cli.setup.recipe import list_recipes
        sys.exit(list_recipes(store=store, staging=staging))
    if getattr(args, "apply", None):
        from codefreedom.cli.setup.recipe import apply_plan
        sys.exit(apply_plan(args.apply))
    if getattr(args, "plan", None):
        from codefreedom.cli.setup.recipe import plan_recipe
        sys.exit(plan_recipe(args.plan, store=store, staging=staging))

    from codefreedom.cli.setup.recipe import init_recipe
    sys.exit(init_recipe("_default", store=store, staging=staging))


def _dispatch_deinit(args) -> None:
    from codefreedom.cli.setup.deinit import run
    sys.exit(run(args))


if __name__ == "__main__":
    main()
