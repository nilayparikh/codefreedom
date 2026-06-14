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
    vscode_parser = subparsers.add_parser(
        "vscode",
        help="Generate chatLanguageModels.json for VS Code Copilot Chat",
        description=(
            "Generate entry for VS Code's built-in "
            "Copilot Chat custom-provider system."
        ),
    )
    vscode_parser.add_argument(
        "--host",
        type=str,
        required=True,
        metavar="HOST",
        help="Proxy host that VS Code should use to reach the proxy",
    )
    vscode_parser.add_argument(
        "--port",
        type=int,
        default=None,
        metavar="PORT",
        help="Proxy port (default: from profile)",
    )
    vscode_parser.add_argument(
        "--name",
        type=str,
        default=None,
        metavar="NAME",
        help="Custom provider name (default: CodeFreedom)",
    )
    vscode_parser.add_argument(
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

    from codefreedom.cli.vscode import cmd_vscode_proxy_config

    return cmd_vscode_proxy_config(args)
