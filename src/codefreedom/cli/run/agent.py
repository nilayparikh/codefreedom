"""Agent launcher — unified entry point for all coding agents.

Usage:
    codefreedom run agent <name> [options] [-- <agent-args>]
    cf r ag <name> ...
    cf r ag list

Supported agents: claude-code (cc), mimo-code (mc), open-code (oc), pi-code (pc)
Adding new agents: add to _AGENTS registry dict below.
"""

from __future__ import annotations

import argparse

from codefreedom.log import eprint, tag


# ── Agent Registry ──────────────────────────────────────────────────────────
#
# Each agent entry contains:
#   module_path:  Python module to import for the agent's run() function
#   run_function: Name of the function to call (usually "run")
#   description:  Human-readable description for help text
#   aliases:      Short names that also resolve to this agent
#
# To add a new agent: add an entry to _AGENTS below.

_AGENTS: dict[str, tuple[str, str, str, list[str]]] = {
    "claude-code": (
        "codefreedom.cli.claude",
        "run",
        "Claude Code — Anthropic's coding agent",
        ["cc"],
    ),
    "mimo-code": (
        "codefreedom.cli.mimo",
        "run",
        "MiMoCode — Xiaomi's coding agent with 0-click proxy config",
        ["mc"],
    ),
    "open-code": (
        "codefreedom.cli.opencode",
        "run",
        "OpenCode — terminal-native AI coding agent with 0-click proxy config",
        ["oc"],
    ),
    "pi-code": (
        "codefreedom.cli.pi",
        "run",
        "Pi Code — Earendil's AI coding agent with 0-click proxy config",
        ["pc"],
    ),
}

# Build reverse alias map: alias → canonical name
_AGENT_ALIASES: dict[str, str] = {}
for _name, (_, _, _, _aliases) in _AGENTS.items():
    for _alias in _aliases:
        _AGENT_ALIASES[_alias] = _name


def get_agent_names() -> list[str]:
    """Return list of canonical agent names."""
    return list(_AGENTS.keys())


def get_agent_aliases() -> dict[str, str]:
    """Return mapping of alias -> canonical name."""
    return dict(_AGENT_ALIASES)


def validate_agent_args(args: argparse.Namespace) -> list[str]:
    """Validate common agent arguments. Returns list of warning messages."""
    warnings: list[str] = []

    if getattr(args, "run_as_me", False) and not getattr(args, "sandbox", False):
        warnings.append("--run-as-me is only valid with --sandbox, ignoring.")

    return warnings


def _resolve_agent(name: str) -> str | None:
    """Resolve agent name or alias to canonical name."""
    if name in _AGENTS:
        return name
    return _AGENT_ALIASES.get(name)


def list_agents() -> int:
    """List all available agents. Returns exit code."""
    if not _AGENTS:
        eprint(f"{tag('AGENT')} No agents registered.")
        return 0

    eprint(f"{tag('AGENT')} Available agents:\n")
    for name, (_, _, description, aliases) in _AGENTS.items():
        alias_str = f" ({', '.join(aliases)})" if aliases else ""
        eprint(f"  {name:14}{alias_str:10} {description}")
    eprint()
    eprint("Usage: cf run agent <name> [options] [-- <agent-args>]")
    eprint("       cf r ag <name> ...")
    return 0


def run_agent(agent_name: str, args: argparse.Namespace) -> int:
    """Launch the specified agent. Returns exit code."""
    canonical = _resolve_agent(agent_name)
    if canonical is None:
        available = ", ".join(_AGENTS.keys())
        aliases = ", ".join(_AGENT_ALIASES.keys())
        eprint(f"{tag('AGENT')} Unknown agent: {agent_name}")
        eprint(f"   Available: {available}")
        eprint(f"   Aliases:   {aliases}")
        return 1

    module_path, func_name, _, _ = _AGENTS[canonical]

    import importlib

    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        eprint(f"{tag('AGENT')} Failed to import agent module '{module_path}': {exc}")
        return 1

    run_fn = getattr(mod, func_name, None)
    if run_fn is None:
        eprint(f"{tag('AGENT')} Agent module '{module_path}' has no '{func_name}' function")
        return 1

    return run_fn(args)


def build_parser(parent: argparse.ArgumentParser) -> None:
    """Build the agent subcommand parser.

    Called from main.py to register the 'agent' subcommand.
    """
    parent.epilog = (
        "examples:\n"
        "  cf r ag cc                       Launch Claude Code\n"
        "  cf r ag mc --sandbox             Launch MiMo in sandbox\n"
        "  cf r ag pc                       Launch Pi Code\n"
        "  cf r ag list                     List available agents"
    )
    from codefreedom.cli.formatter import CodeFreedomHelpFormatter
    parent.formatter_class = CodeFreedomHelpFormatter

    subparsers = parent.add_subparsers(dest="agent_name", title="agents")

    # 'list' sub-action
    subparsers.add_parser(
        "list",
        help="List available agents",
        description="List all registered coding agents.",
    )

    # Dynamically create sub-parser for each registered agent (with aliases)
    for name, (module_path, _, description, aliases) in _AGENTS.items():
        agent_parser = subparsers.add_parser(
            name,
            aliases=aliases,
            help=description,
            description=f"Launch {description}.",
        )

        # Common agent flags
        agent_parser.add_argument(
            "-p",
            "--profile",
            type=str,
            default="default",
            metavar="NAME",
            help="Load a named profile (default: 'default')",
        )
        agent_parser.add_argument(
            "-l",
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

    # Resolve alias to canonical name
    canonical = _resolve_agent(agent_name)
    if canonical:
        args.agent_name = canonical

    # Collect forwarded args (everything after --)
    forwarded = getattr(args, "agent_args", [])
    args.agent_args = forwarded

    return run_agent(canonical or agent_name, args)
