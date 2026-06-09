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
            " github.com/nilayparikh/codefreedom-recipes."
            " Without flags, installs the _default base recipe."
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
        help="Manage auxiliary tools (chrome browser, web search, etc.)",
        description="Manage auxiliary tools used by coding agents (headless Chrome browser, web search, etc.).",
    )
    tools_subparsers = tools_parser.add_subparsers(dest="tool", title="tools")

    # ── chrome tool ─────────────────────────────────────────────────────
    chrome_parser = tools_subparsers.add_parser(
        "chrome",
        help="Headless Chrome browser for automation (CDP at port 9222)",
        description="Start/stop/manage a headless Chrome browser container for browser automation. Coding agents connect via Chrome DevTools Protocol (CDP) at port 9222.",
    )
    chrome_parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["start", "stop", "restart", "status", "url"],
        help="Action to perform (default: status). 'restart' uses `docker restart` (preserves container state, does not pull a new image).",
    )
    chrome_parser.add_argument(
        "--port",
        type=int,
        default=9222,
        help="CDP debug port (default: 9222)",
    )

    # ── web tool ────────────────────────────────────────────────────────
    web_parser = tools_subparsers.add_parser(
        "web",
        help="Web search and scraping tool (MCP)",
        description="Start/stop/manage a web search container. The container runs an MCP server on port 8420 with web_search and web_fetch tools.",
    )
    web_parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["start", "stop", "restart", "status"],
        help="Action to perform (default: status). 'restart' uses `docker restart` (preserves container state, does not pull a new image).",
    )
    web_parser.add_argument(
        "--port",
        type=int,
        default=8420,
        help="MCP server port (default: 8420)",
    )

    # ── github tool ──────────────────────────────────────────────────────
    github_parser = tools_subparsers.add_parser(
        "github",
        help="GitHub MCP Server (ghcr.io/github/github-mcp-server)",
        description=(
            "Start/stop/manage a GitHub MCP Server container. "
            "Provides GitHub API tools (issues, PRs, repos, etc.) via MCP. "
            "Requires GITHUB_PERSONAL_ACCESS_TOKEN in the profile."
        ),
    )
    github_parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["start", "stop", "restart", "status"],
        help="Action to perform (default: status). 'restart' uses `docker restart` (preserves container state, does not pull a new image).",
    )
    github_parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="HTTP MCP server port (0 = auto-pick random free port)",
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
        default=4000,
        help="Port to publish on the host (sets LITELLM_PORT for this run only; default: 4000)",
    )
    start_parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host bind address (sets LITELLM_BIND_HOST for this run only; default: 0.0.0.0)",
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

    # ── init subcommand ────────────────────────────────────────────────────
    if args.command == "init":
        if unknown:
            eprint(f"[ERROR] Unrecognized arguments: {' '.join(unknown)}")
            sys.exit(2)

        init_action = getattr(args, "init_action", None)

        if init_action == "recipe":
            if args.list:
                from codefreedom.cli.recipe import list_recipes

                sys.exit(list_recipes())

            if args.apply:
                from codefreedom.cli.recipe import apply_plan

                sys.exit(apply_plan(args.apply))

            if args.plan:
                from codefreedom.cli.recipe import plan_recipe

                sys.exit(plan_recipe(args.plan))

            # No flags → install _default base recipe
            from codefreedom.cli.recipe import init_recipe

            sys.exit(init_recipe("_default"))

        # Plain `cf init` — redirect to recipe system
        print("[init] Use `cf init recipe` to initialize CodeFreedom configuration.")
        print()
        print("  cf init recipe              # install _default base recipe")
        print("  cf init recipe --list        # list available recipes")
        print("  cf init recipe --plan <name> # preview a recipe without applying")
        print("  cf init recipe <name>        # install a specific recipe")
        print()
        print("  Docs: https://nilayparikh.github.io/codefreedom/recipes/")
        sys.exit(0)

    if args.command in ("claude", "cc"):
        # ── Rescue known flags swallowed by parse_known_args ────────────────
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
        # ── claude sub-actions (subparser-based) ───────────────────────────
        claude_action = getattr(args, "claude_action", None)
        if claude_action == "config":
            from codefreedom.cli.claude import cmd_config

            sys.exit(cmd_config(args))

        # ── Forward everything remaining to claude CLI ─────────────────────
        args.claude_args = forwarded
        from codefreedom.cli.claude import run as claude_run

        sys.exit(claude_run(args))
    elif args.command in ("proxy", "px"):
        if unknown:
            eprint(f"[ERROR] Unrecognized arguments: {' '.join(unknown)}")
            sys.exit(2)
        from codefreedom.cli.proxy import run as proxy_run

        sys.exit(proxy_run(args))
    elif args.command in ("admin", "adm"):
        if unknown:
            eprint(f"[ERROR] Unrecognized arguments: {' '.join(unknown)}")
            sys.exit(2)
        from codefreedom.cli.admin import run as admin_run

        sys.exit(admin_run(args))
    elif args.command == "tools":
        if args.tool == "chrome":
            if unknown:
                eprint(f"[ERROR] Unrecognized arguments: {' '.join(unknown)}")
                sys.exit(2)
            from codefreedom.cli.chrome import run as chrome_run

            sys.exit(chrome_run(args))
        elif args.tool == "web":
            if unknown:
                eprint(f"[ERROR] Unrecognized arguments: {' '.join(unknown)}")
                sys.exit(2)
            from codefreedom.cli.web import run as web_run

            sys.exit(web_run(args))
        elif args.tool == "github":
            if unknown:
                eprint(f"[ERROR] Unrecognized arguments: {' '.join(unknown)}")
                sys.exit(2)
            from codefreedom.cli.github import run as github_run

            sys.exit(github_run(args))
        elif args.tool is None:
            tools_parser.print_help()
            sys.exit(0)
        else:
            eprint(f"[ERROR] Unknown tool: {args.tool}")
            eprint("   Available tools: chrome, web, github")
            sys.exit(1)
    elif args.command in ("vscode", "vsc"):
        if unknown:
            eprint(f"[ERROR] Unrecognized arguments: {' '.join(unknown)}")
            sys.exit(2)
        from codefreedom.cli.vscode import (
            cmd_vscode_claude_config,
            cmd_vscode_proxy_config,
        )

        # Two-level dispatch: `vscode_action` (claude|proxy) and the
        # `*_config_action` (always "config" for now -- future verbs like
        # `install` go alongside `config`).
        action = getattr(args, "vscode_action", None)
        if action == "claude":
            if getattr(args, "claude_config_action", None) != "config":
                vscode_parser.print_help()
                sys.exit(1)
            sys.exit(cmd_vscode_claude_config(args))
        elif action == "proxy":
            if getattr(args, "proxy_config_action", None) != "config":
                vscode_parser.print_help()
                sys.exit(1)
            sys.exit(cmd_vscode_proxy_config(args))
        else:
            vscode_parser.print_help()
            sys.exit(1)
    elif args.command in ("update", "upd", "up"):
        if unknown:
            eprint(f"[ERROR] Unrecognized arguments: {' '.join(unknown)}")
            sys.exit(2)
        from codefreedom.cli.update import run as update_run

        sys.exit(update_run(args))
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
