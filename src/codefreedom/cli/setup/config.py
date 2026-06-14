"""Config command — generate VS Code settings fragments.

Usage:
    codefreedom setup config vscode [options]
"""

from __future__ import annotations

import argparse

from codefreedom.log import eprint


def build_parser(parent: argparse.ArgumentParser) -> None:
    """Build the config subcommand parser.

    Called from main.py to register the 'config' subcommand.
    """
    subparsers = parent.add_subparsers(dest="config_target", title="targets")

    # ── vscode config target ─────────────────────────────────────────────
    # VS Code has two sub-targets: claude and proxy
    vscode_sub = subparsers.add_parser(
        "vscode",
        help="Generate VS Code settings fragments",
        description=(
            "Generate VS Code configuration fragments "
            "from CodeFreedom profiles."
        ),
    )
    vscode_action = vscode_sub.add_subparsers(
        dest="vscode_action", title="vscode targets"
    )

    # vscode claude config
    vscode_claude = vscode_action.add_parser(
        "claude",
        help="Generate claudeCode.* settings for VS Code",
        description=(
            "Generate settings.json fragment for the "
            "Claude Code VS Code extension."
        ),
    )
    vscode_claude.add_argument(
        "--profile",
        type=str,
        default="default",
        metavar="NAME",
        help="Profile to resolve (default: 'default')",
    )
    vscode_claude.add_argument(
        "--host",
        type=str,
        default=None,
        metavar="HOST",
        help="Proxy host (default: localhost)",
    )
    vscode_claude.add_argument(
        "--port",
        type=int,
        default=None,
        metavar="PORT",
        help="Proxy port (default: from profile)",
    )
    vscode_claude.add_argument(
        "--out",
        type=str,
        default=None,
        metavar="FILE",
        help="Write to FILE instead of stdout",
    )

    # vscode proxy config
    vscode_proxy = vscode_action.add_parser(
        "proxy",
        help="Generate chatLanguageModels.json for VS Code Copilot Chat",
        description=(
            "Generate entry for VS Code's built-in "
            "Copilot Chat custom-provider system."
        ),
    )
    vscode_proxy.add_argument(
        "--host",
        type=str,
        required=True,
        metavar="HOST",
        help="Proxy host that VS Code should use to reach the proxy",
    )
    vscode_proxy.add_argument(
        "--port",
        type=int,
        default=None,
        metavar="PORT",
        help="Proxy port (default: from profile)",
    )
    vscode_proxy.add_argument(
        "--name",
        type=str,
        default=None,
        metavar="NAME",
        help="Custom provider name (default: CodeFreedom)",
    )
    vscode_proxy.add_argument(
        "--out",
        type=str,
        default=None,
        metavar="FILE",
        help="Write to FILE instead of stdout",
    )


def handle_args(args: argparse.Namespace) -> int:
    """Handle parsed args and dispatch to the correct config target.

    Called from main.py after argument parsing.
    """
    target = getattr(args, "config_target", None)

    if target is None:
        eprint("[CONFIG] No target specified. Run 'cf setup config -h' for available targets.")
        return 1

    # VS Code has sub-targets: claude and proxy
    vscode_action = getattr(args, "vscode_action", None)
    if vscode_action is None:
        eprint("[CONFIG] vscode requires a sub-target: 'claude' or 'proxy'")
        eprint("   Usage: cf setup config vscode claude [options]")
        eprint("          cf setup config vscode proxy [options]")
        return 1

    if vscode_action == "claude":
        from codefreedom.cli.vscode import cmd_vscode_claude_config

        return cmd_vscode_claude_config(args)
    elif vscode_action == "proxy":
        from codefreedom.cli.vscode import cmd_vscode_proxy_config

        return cmd_vscode_proxy_config(args)
    else:
        eprint(f"[CONFIG] Unknown vscode target: {vscode_action}")
        return 1
