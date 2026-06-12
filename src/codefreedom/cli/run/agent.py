"""Agent launcher — unified entry point for all coding agents.

Usage:
    codefreedom agent <name> [options] [-- <agent-args>]
    codefreedom agent list

Supported agents: claude, mimo
Adding new agents: add to _AGENTS registry dict below.
"""

from __future__ import annotations

import argparse

from codefreedom.log import eprint


# ── Agent Registry ──────────────────────────────────────────────────────────

# Each entry: (module_path, run_function_name, description)
_AGENTS: dict[str, tuple[str, str, str]] = {
    "claude": (
        "codefreedom.cli.claude",
        "run",
        "Claude Code — Anthropic's coding agent",
    ),
    "mimo": (
        "codefreedom.cli.mimo",
        "run",
        "MiMoCode — Xiaomi's coding agent with 0-click proxy config",
    ),
    "opencode": (
        "codefreedom.cli.opencode",
        "run",
        "OpenCode — terminal-native AI coding agent with 0-click proxy config",
    ),
}


def list_agents() -> int:
    """List all available agents. Returns exit code."""
    if not _AGENTS:
        eprint("[AGENT] No agents registered.")
        return 0

    eprint("[AGENT] Available agents:\n")
    for name, (_, _, description) in _AGENTS.items():
        eprint(f"  {name:12} {description}")
    eprint()
    eprint("Usage: cf agent <name> [options] [-- <agent-args>]")
    return 0


def run_agent(agent_name: str, args: argparse.Namespace) -> int:
    """Launch the specified agent. Returns exit code."""
    if agent_name not in _AGENTS:
        eprint(f"[AGENT] Unknown agent: {agent_name}")
        eprint(f"   Available agents: {', '.join(_AGENTS.keys())}")
        return 1

    module_path, func_name, _ = _AGENTS[agent_name]

    import importlib

    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        eprint(f"[AGENT] Failed to import agent module '{module_path}': {exc}")
        return 1

    run_fn = getattr(mod, func_name, None)
    if run_fn is None:
        eprint(f"[AGENT] Agent module '{module_path}' has no '{func_name}' function")
        return 1

    return run_fn(args)


def build_parser(parent: argparse.ArgumentParser) -> None:
    """Build the agent subcommand parser.

    Called from main.py to register the 'agent' subcommand.
    """
    subparsers = parent.add_subparsers(dest="agent_name", title="agents")

    # 'list' sub-action
    subparsers.add_parser(
        "list",
        help="List available agents",
        description="List all registered coding agents.",
    )

    # Dynamically create sub-parser for each registered agent
    for name, (module_path, _, description) in _AGENTS.items():
        agent_parser = subparsers.add_parser(
            name,
            help=description,
            description=f"Launch {description}.",
        )

        # Common agent flags
        agent_parser.add_argument(
            "--profile",
            type=str,
            default="default",
            metavar="NAME",
            help="Load a named profile (default: 'default')",
        )
        agent_parser.add_argument(
            "--list-profiles",
            action="store_true",
            help="List available profiles and exit",
        )

        # Agent-specific flags — each agent module can register extra flags
        # by defining a register_args(parser) function.
        try:
            import importlib

            mod = importlib.import_module(module_path)
            register_fn = getattr(mod, "register_args", None)
            if register_fn:
                register_fn(agent_parser)
        except ImportError:
            pass


def handle_args(args: argparse.Namespace) -> int:
    """Handle parsed args and dispatch to the correct agent.

    Called from main.py after argument parsing.
    """
    agent_name = getattr(args, "agent_name", None)

    if agent_name is None or agent_name == "list":
        return list_agents()

    # Collect forwarded args (everything after --)
    forwarded = getattr(args, "agent_args", [])
    args.agent_args = forwarded

    return run_agent(agent_name, args)
