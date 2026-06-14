"""Unified config command — generate configurations for all targets.

Usage:
    codefreedom setup config <target> [options]

Targets:
    claude      Generate shell exports for Claude Code
    mimo        Generate mimocode.json for MiMoCode
    vscode      Generate VS Code settings fragments

This is the single entry point for all configuration generation,
consolidating scattered config sub-actions from claude, mimo, and vscode.
"""

from __future__ import annotations

import argparse

from codefreedom.log import eprint


# ── Config Target Registry ──────────────────────────────────────────────────

# Each entry: (module_path, handler_name, description)
_CONFIG_TARGETS: dict[str, tuple[str, str, str]] = {
    "claude": (
        "codefreedom.cli.claude",
        "cmd_config",
        "Generate shell exports for Claude Code (--bash/--ps)",
    ),
    "mimo": (
        "codefreedom.cli.mimo",
        "cmd_config",
        "Generate mimocode.json for MiMoCode",
    ),
}


def list_targets() -> int:
    """List all available config targets. Returns exit code."""
    if not _CONFIG_TARGETS:
        eprint("[CONFIG] No config targets registered.")
        return 0

    eprint("[CONFIG] Available config targets:\n")
    for name, (_, _, description) in _CONFIG_TARGETS.items():
        eprint(f"  {name:12} {description}")
    eprint()
    eprint("Usage: cf setup config <target> [options]")
    return 0


def run_config(target: str, args: argparse.Namespace) -> int:
    """Run the config handler for the specified target. Returns exit code."""
    if target not in _CONFIG_TARGETS:
        eprint(f"[CONFIG] Unknown config target: {target}")
        eprint(f"   Available targets: {', '.join(_CONFIG_TARGETS.keys())}")
        return 1

    module_path, handler_name, _ = _CONFIG_TARGETS[target]

    import importlib

    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        eprint(f"[CONFIG] Failed to import config module '{module_path}': {exc}")
        return 1

    handler = getattr(mod, handler_name, None)
    if handler is None:
        eprint(
            f"[CONFIG] Config module '{module_path}' "
            f"has no '{handler_name}' function"
        )
        return 1

    return handler(args)


def build_parser(parent: argparse.ArgumentParser) -> None:
    """Build the config subcommand parser.

    Called from main.py to register the 'config' subcommand.
    """
    subparsers = parent.add_subparsers(dest="config_target", title="targets")

    # 'list' sub-action
    subparsers.add_parser(
        "list",
        help="List available config targets",
        description="List all registered configuration targets.",
    )

    # ── claude config target ─────────────────────────────────────────────
    claude_parser = subparsers.add_parser(
        "claude",
        help="Generate shell exports for Claude Code",
        description=(
            "Generate environment variable exports for standalone Claude Code use. "
            "Outputs bash export statements or PowerShell $env: assignments."
        ),
    )
    claude_parser.add_argument(
        "--profile",
        type=str,
        default="default",
        metavar="NAME",
        help="Profile to resolve (default: 'default')",
    )
    claude_parser.add_argument(
        "--out",
        type=str,
        default=None,
        metavar="FILE",
        help="Write to FILE instead of stdout (recommended to avoid leaking secrets)",
    )
    claude_format = claude_parser.add_mutually_exclusive_group()
    claude_format.add_argument(
        "--bash",
        action="store_true",
        help="Output in bash export format (default)",
    )
    claude_format.add_argument(
        "--ps",
        action="store_true",
        dest="powershell",
        help="Output in PowerShell $env: format",
    )

    # ── mimo config target ───────────────────────────────────────────────
    mimo_parser = subparsers.add_parser(
        "mimo",
        help="Generate mimocode.json for MiMoCode",
        description=(
            "Generate a complete mimocode.json config pointing at the running "
            "CodeFreedom proxy. Fetches the live model list and outputs the config."
        ),
    )
    mimo_parser.add_argument(
        "--profile",
        type=str,
        default="default",
        metavar="NAME",
        help="Profile to resolve (default: 'default')",
    )
    mimo_parser.add_argument(
        "--out",
        type=str,
        default=None,
        metavar="FILE",
        help="Write to FILE instead of stdout",
    )

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

    if target is None or target == "list":
        return list_targets()

    # Special handling for vscode (has sub-targets)
    if target == "vscode":
        vscode_action = getattr(args, "vscode_action", None)
        if vscode_action is None:
            eprint("[CONFIG] vscode requires a sub-target: 'claude' or 'proxy'")
            eprint("   Usage: cf setup config vscode claude [options]")
            eprint("          cf setup config vscode proxy [options]")
            return 1

        # Route to the correct vscode handler
        if vscode_action == "claude":
            from codefreedom.cli.vscode import cmd_vscode_claude_config

            return cmd_vscode_claude_config(args)
        elif vscode_action == "proxy":
            from codefreedom.cli.vscode import cmd_vscode_proxy_config

            return cmd_vscode_proxy_config(args)
        else:
            eprint(f"[CONFIG] Unknown vscode target: {vscode_action}")
            return 1

    return run_config(target, args)
