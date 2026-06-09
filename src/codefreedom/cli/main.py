"""Top-level CLI entry point -- parses args and dispatches to subcommands.

Entry point: codefreedom | cf
"""

from __future__ import annotations

import argparse
import sys

from codefreedom.env_loader import eprint


def main() -> None:
    """Top-level CLI entry point: codefreedom | cf."""
    parser = argparse.ArgumentParser(
        prog="codefreedom",
        description="CodeFreedom -- Single wrapper for all code agents. Simple LLM routing, sandboxing, profile management, and isolation. All config in ~/.codefreedom.",
    )
    subparsers = parser.add_subparsers(dest="command", title="commands")

    # ── init subcommand ─────────────────────────────────────────────────────
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize CodeFreedom config via recipes",
        description=(
            "Initialize CodeFreedom configuration via recipes. "
            "Use `cf init recipe` to list, plan, or apply configuration recipes."
        ),
    )
    init_sub = init_parser.add_subparsers(dest="init_action", title="init actions")

    # ── init recipe subcommand ──────────────────────────────────────────────
    recipe_parser = init_sub.add_parser(
        "recipe",
        help="Manage configuration recipes",
        description=(
            "Plan, apply, or list configuration recipes from"
            " github.com/nilayparikh/codefreedom-recipes or a custom store."
            " Without flags, installs the _default base recipe."
            " Use --store to specify a GitHub URL or local folder."
        ),
    )
    recipe_group = recipe_parser.add_mutually_exclusive_group()
    recipe_group.add_argument(
        "--plan",
        type=str,
        metavar="NAME",
        help="Preview a recipe: generate .patch files without applying (e.g. opencode-free)",
    )
    recipe_group.add_argument(
        "--apply",
        type=str,
        metavar="PLAN_ID",
        help="Apply a previously generated plan by ID (e.g. aB3xK9mZ2q)",
    )
    recipe_group.add_argument(
        "--list",
        action="store_true",
        help="List all available recipes from the repository",
    )
    recipe_parser.add_argument(
        "--store",
        type=str,
        metavar="URL_OR_PATH",
        default=None,
        help="Custom recipe store: GitHub URL (e.g. https://github.com/owner/repo.git) or local folder path",
    )

    # ── claude subcommand ──────────────────────────────────────────────────
    claude_parser = subparsers.add_parser(
        "claude",
        aliases=["cc"],
        help="Launch code agent with profile-based model routing",
        description="Run a code agent natively (default) or in a sandboxed Docker container.",
    )
    # GPU image flags (mutually exclusive, only meaningful with --sandbox)
    claude_gpu = claude_parser.add_mutually_exclusive_group()
    claude_gpu.add_argument(
        "--cuda",
        action="store_true",
        dest="gpu_cuda",
        help="Use CUDA sandbox image for NVIDIA GPUs (only with --sandbox)",
    )
    claude_gpu.add_argument(
        "--rocm",
        action="store_true",
        dest="gpu_rocm",
        help="Use ROCm sandbox image for AMD GPUs (only with --sandbox)",
    )
    claude_parser.add_argument(
        "--sandbox",
        action="store_true",
        help="Run inside a sandboxed Docker container (default: native)",
    )
    claude_parser.add_argument(
        "--run-as-me",
        action="store_true",
        help="Run sandbox container as host user (uid/gid match). Only valid with --sandbox.",
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
        "--list-profiles",
        action="store_true",
        help="List available profiles and exit",
    )
    claude_parser.add_argument(
        "--dangerously-skip-permissions",
        action="store_true",
        help="Skip Claude Code permission prompts (use in CI/non-interactive environments)",
    )

    # ── claude sub-actions ───────────────────────────────────────────────
    # (VS Code config generation was moved to the top-level `vscode`
    # subcommand -- use `codefreedom vscode claude config` instead.)
    claude_subparsers = claude_parser.add_subparsers(
        dest="claude_action", title="actions"
    )

    config_parser = claude_subparsers.add_parser(
        "config",
        help="Resolve profile env vars for standalone Claude Code use",
        description=(
            "Resolve your CodeFreedom profile's environment variables so you can"
            " run Claude Code directly (without cf cc). Writes export-format"
            " statements for bash or $env: format for PowerShell. The output"
            " may contain secrets; use --out to write to a file."
        ),
    )
    config_parser.add_argument(
        "--profile",
        type=str,
        default="default",
        metavar="NAME",
        help="Profile to resolve (default: 'default')",
    )
    config_parser.add_argument(
        "--out",
        type=str,
        default=None,
        metavar="FILE",
        help="Write to FILE instead of stdout (recommended to avoid leaking secrets)",
    )
    config_format = config_parser.add_mutually_exclusive_group()
    config_format.add_argument(
        "--bash",
        action="store_true",
        help="Output in bash export format (default)",
    )
    config_format.add_argument(
        "--ps",
        action="store_true",
        dest="powershell",
        help="Output in PowerShell $env: format",
    )

    # ── admin subcommand ───────────────────────────────────────────────────
    admin_parser = subparsers.add_parser(
        "admin",
        aliases=["adm"],
        help="Backup, restore, list, inspect, and prune CodeFreedom configuration",
    )
    # Populate admin sub-subcommands (lazy import to keep startup fast)
    from codefreedom.cli.admin import build_parser as build_admin_parser

    build_admin_parser(admin_parser)

    # ── tools subcommand ──────────────────────────────────────────────────
    tools_parser = subparsers.add_parser(
        "tools",
        help="Manage all auxiliary tools (start/stop/restart/status)",
        description=(
            "Manage all auxiliary tools (Chrome, web search, GitHub MCP, web bridge). "
            "All tools are managed as a group — use 'start', 'stop', 'restart', or 'status'. "
            "Tools are auto-started by 'cf px start' and 'cf cc' when needed."
        ),
    )
    tools_parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["start", "stop", "restart", "status"],
        help="Action to perform on all tools (default: status). 'restart' uses `docker restart`.",
    )

    # ── proxy subcommand ───────────────────────────────────────────────────
    proxy_parser = subparsers.add_parser(
        "proxy",
        aliases=["px"],
        help="Manage the LLM proxy (start, stop, status, validate, init)",
        description="Manage the LLM proxy lifecycle. The proxy always runs via `docker compose` against ~/.codefreedom/proxy/docker-compose.yaml.",
    )
    proxy_sub = proxy_parser.add_subparsers(
        dest="action",
        title="actions",
    )
    proxy_sub.required = False  # default via set_defaults below
    proxy_sub.add_parser(
        "status",
        help="Show proxy status",
        description="Show whether the proxy is running and on which port.",
    )
    proxy_parser.set_defaults(action="status")

    # start
    start_parser = proxy_sub.add_parser(
        "start",
        help="Start the proxy (Docker Compose)",
        description=(
            "Start the proxy via `docker compose up -d`. The proxy runs"
            " inside the `codefreedom:litellm-latest` image which bakes in"
            " the WebSearch count display patch."
        ),
    )
    start_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to publish on the host (sets LITELLM_PORT for this run only; default: from .env.proxy or 4000)",
    )
    start_parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Host bind address (sets LITELLM_BIND_HOST for this run only; default: from .env.proxy or 0.0.0.0)",
    )

    # stop
    proxy_sub.add_parser(
        "stop",
        help="Stop the proxy",
        description="Stop the running proxy Docker Compose stack.",
    )

    # restart
    proxy_sub.add_parser(
        "restart",
        help="Restart the proxy (Docker Compose)",
        description=(
            "Restart the proxy via `docker compose restart` (preserves state,"
            " does not pull a new image)."
        ),
    )

    # validate
    proxy_sub.add_parser(
        "validate",
        help="Validate proxy configuration",
        description="Validate the proxy configuration file (config.yaml).",
    )

    # (VS Code config generation was moved to the top-level `vscode`
    # subcommand -- use `codefreedom vscode proxy config` instead.)

    # ── vscode subcommand ──────────────────────────────────────────────────
    vscode_parser = subparsers.add_parser(
        "vscode",
        aliases=["vsc"],
        help="Generate VS Code configuration fragments (Claude Code, proxy)",
        description=(
            "Generate VS Code configuration fragments from CodeFreedom profiles"
            " and the running proxy. Currently supports:\n"
            "  * `vscode claude config` -- a `claudeCode.*` settings fragment"
            " for the Claude Code VS Code extension.\n"
            "  * `vscode proxy config`  -- a `chatLanguageModels.json` entry"
            " for VS Code's built-in Copilot Chat custom-provider system."
        ),
    )
    # Populate vscode sub-subcommands (lazy import to keep startup fast)
    from codefreedom.cli.vscode import build_parser as build_vscode_parser

    build_vscode_parser(vscode_parser)

    # ── doctor subcommand ────────────────────────────────────────────────────
    doctor_parser = subparsers.add_parser(
        "doctor",
        aliases=["doc", "dr"],
        help="Validate the full CodeFreedom environment",
        description=(
            "Run comprehensive diagnostics on your CodeFreedom setup."
            " Checks config files, Docker availability, PostgreSQL data"
            " directory permissions, Docker images, profiles, env vars,"
            " and proxy status. Detects issues like PostgreSQL initdb"
            " permission errors before they happen."
        ),
    )
    doctor_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed information for all checks (not just failures)",
    )

    # ── deinit subcommand ───────────────────────────────────────────────────
    deinit_parser = subparsers.add_parser(
        "deinit",
        help="Tear down CodeFreedom: stop containers and remove config",
        description=(
            "Fully tear down CodeFreedom configuration. Stops all managed"
            " Docker containers (proxy, tools, sandbox sessions), then"
            " prompts for confirmation before deleting the entire"
            " CodeFreedom home directory (~/.codefreedom/)."
            " Use --force to skip the confirmation prompt."
        ),
    )
    deinit_parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt before removing the CodeFreedom directory",
    )

    # -- update subcommand -----------------------------------------------------------
    update_parser = subparsers.add_parser(
        "update",
        aliases=["upd", "up"],
        help="Check Docker images and PyPI package for updates",
        description=(
            "Check CodeFreedom-managed Docker images and the installed PyPI"
            " package for available updates. Scans profile configs and local"
            " Docker cache to discover images, then compares local digests"
            " against the Docker Hub registry. No auto-pull or container"
            " lifecycle changes -- read-only status check."
        ),
    )
    update_parser.add_argument(
        "services",
        nargs="*",
        metavar="SERVICE",
        help="Filter by service: sandbox, chrome, web, proxy, tools, all (default)",
    )

    args, unknown = parser.parse_known_args()

    # ── Helper: lazy-import-and-run pattern used by most subcommands ───────
    def _dispatch(module: str, fn: str, *fn_args, **fn_kwargs) -> None:
        if unknown:
            eprint(f"[ERROR] Unrecognized arguments: {' '.join(unknown)}")
            sys.exit(2)
        import importlib

        mod = importlib.import_module(module)
        sys.exit(getattr(mod, fn)(*fn_args, **fn_kwargs))

    # ── init subcommand ────────────────────────────────────────────────────
    if args.command == "init":
        if unknown:
            eprint(f"[ERROR] Unrecognized arguments: {' '.join(unknown)}")
            sys.exit(2)

        init_action = getattr(args, "init_action", None)

        if init_action == "recipe":
            store = getattr(args, "store", None)

            if args.list:
                from codefreedom.cli.recipe import list_recipes

                sys.exit(list_recipes(store=store))
            if args.apply:
                from codefreedom.cli.recipe import apply_plan

                sys.exit(apply_plan(args.apply, store=store))
            if args.plan:
                from codefreedom.cli.recipe import plan_recipe

                sys.exit(plan_recipe(args.plan, store=store))

            # No flags → install _default base recipe
            from codefreedom.cli.recipe import init_recipe

            sys.exit(init_recipe("_default", store=store))

        # Plain `cf init` — redirect to recipe system
        from codefreedom.cli.tool_init_utils import print_help_section

        print_help_section(
            "init",
            [
                "Use:  cf init recipe                    # install _default base recipe",
                "      cf init recipe --list              # list available recipes",
                "      cf init recipe --plan <name>       # preview a recipe without applying",
                "      cf init recipe --store <path|url>  # use a custom recipe store",
                "      cf init recipe <name>              # install a specific recipe",
            ],
            docs_url="https://nilayparikh.github.io/codefreedom/recipes/",
            include_disclaimer=False,
        )
        sys.exit(0)

    # ── claude subcommand (needs parse_known_args rescue) ─────────────────
    if args.command in ("claude", "cc"):
        _CLAUDE_BOOL_FLAGS = {
            "--cuda": "gpu_cuda",
            "--rocm": "gpu_rocm",
            "--sandbox": "sandbox",
            "--run-as-me": "run_as_me",
            "--native-models": "native_models",
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

        claude_action = getattr(args, "claude_action", None)
        if claude_action == "config":
            from codefreedom.cli.claude import cmd_config

            sys.exit(cmd_config(args))

        args.claude_args = forwarded
        from codefreedom.cli.claude import run as claude_run

        sys.exit(claude_run(args))

    # ── vscode subcommand (two-level dispatch) ────────────────────────────
    if args.command in ("vscode", "vsc"):
        if unknown:
            eprint(f"[ERROR] Unrecognized arguments: {' '.join(unknown)}")
            sys.exit(2)
        from codefreedom.cli.vscode import (
            cmd_vscode_claude_config,
            cmd_vscode_proxy_config,
        )

        action_map = {
            "claude": cmd_vscode_claude_config,
            "proxy": cmd_vscode_proxy_config,
        }
        action = getattr(args, "vscode_action", None)
        handler = action_map.get(action)
        if handler is None:
            vscode_parser.print_help()
            sys.exit(1)
        sys.exit(handler(args))

    # ── doctor (needs extra verbose arg) ──────────────────────────────────
    if args.command in ("doctor", "doc", "dr"):
        _dispatch("codefreedom.cli.doctor", "run", verbose=args.verbose)

    # ── Simple subcommands (dispatch table) ───────────────────────────────
    _SIMPLE_DISPATCH: dict[str, tuple[str, str]] = {
        "proxy": ("codefreedom.cli.proxy", "run"),
        "px": ("codefreedom.cli.proxy", "run"),
        "admin": ("codefreedom.cli.admin", "run"),
        "adm": ("codefreedom.cli.admin", "run"),
        "tools": ("codefreedom.cli.tools", "run"),
        "update": ("codefreedom.cli.update", "run"),
        "upd": ("codefreedom.cli.update", "run"),
        "up": ("codefreedom.cli.update", "run"),
        "deinit": ("codefreedom.cli.deinit", "run"),
    }
    dispatch = _SIMPLE_DISPATCH.get(args.command)
    if dispatch is not None:
        _dispatch(dispatch[0], dispatch[1], args)

    # ── Fallback ──────────────────────────────────────────────────────────
    parser.print_help()
    sys.exit(0)


if __name__ == "__main__":
    main()
