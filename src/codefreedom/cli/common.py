"""Shared CLI utilities -- reusable patterns for all subcommands.

Provides:
    display_profiles()     — display available profiles in a consistent format
    load_profile_env_only() — load profile env without tools
    write_output_file()    — write content to file with security permissions
    confirm_stdout_output() — output to stdout with confirmation prompt
    run_tool_action()      — dispatch tool actions (start/stop/restart/status)
    add_profile_args()     — add common --profile/--list-profiles args
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from codefreedom.config.runtime import resolve_agent_runtime
from codefreedom.log import eprint, tag

# ── Profile display ─────────────────────────────────────────────────────────


def display_profiles(
    profiles_path: Path,
    profiles: list[dict[str, Any]],
    show_env_keys: bool = True,
    show_tools: bool = True,
) -> int:
    """Display available profiles in a consistent format.

    This is the single source of truth for profile display across all
    subcommands (claude, mimo, etc).

    Args:
        profiles_path: Path to the profiles file (for display)
        profiles: List of profile dicts from list_profiles()
        show_env_keys: Whether to show env_keys details (default True)
        show_tools: Whether to show tools (default True)

    Returns:
        0 on success
    """
    if not profiles:
        eprint(f"{tag('PROFILES')} No profiles found.")
        return 0

    eprint(f"{tag('PROFILES')} Available profiles ({profiles_path}):\n")
    for p in profiles:
        override_word = "override" if len(p["env_keys"]) == 1 else "overrides"
        inheritance = (
            "standalone"
            if p["standalone"]
            else f"inherits from 'default' — {len(p['env_keys'])} {override_word}"
        )
        eprint(f"  {p['name']}")
        eprint(f"    {p['description']}")
        eprint(f"    ({inheritance})")
        if show_env_keys and p["env_keys"]:
            keys_summary = ", ".join(p["env_keys"][:5])
            if len(p["env_keys"]) > 5:
                keys_summary += ", …"
            eprint(f"    sets: {keys_summary}")
        if p.get("local_env_keys"):
            eprint(f"    local: {', '.join(p['local_env_keys'])}")
        if show_tools and p.get("tools"):
            eprint(f"    tools: {', '.join(p['tools'])}")
        eprint()
    return 0


# ── Profile env loading ─────────────────────────────────────────────────────


def load_profile_env_only(
    profile_name: str,
    profiles_path: Path,
    base_env: dict[str, str],
    error_prefix: str = "codefreedom setup init",
    agent: str = "",
) -> tuple[dict[str, str], int]:
    """Load profile env without tools.

    This is the single source of truth for profile loading in cmd_config
    functions (claude config, mimo config, etc).

    Args:
        profile_name: Name of the profile to load
        profiles_path: Path to the profiles file
        base_env: Base environment from load_env_chain()
        error_prefix: Prefix for error messages (e.g. "codefreedom setup init")
        agent: Canonical agent name (e.g. "claude-code").  When empty it is
            inferred from the profiles filename.

    Returns:
        Tuple of (profile_env, exit_code) where exit_code is 0 on success,
        1 on error.
    """
    from codefreedom.config.errors import ProfileError

    profile_env: dict[str, str] = {}

    if not profiles_path.exists() and profile_name != "default":
        eprint(
            f"[ERROR] Profile '{profile_name}' requested but no profiles file found."
        )
        return profile_env, 1
    elif not profiles_path.exists():
        eprint(f"{tag('ERROR')} No profiles file found. Run `{error_prefix}` first.")
        return profile_env, 1

    try:
        resolved_agent = agent or _agent_name_from_profiles_path(profiles_path)
        runtime = resolve_agent_runtime(
            resolved_agent,
            workspace_dir=Path.cwd(),
            profile_name=profile_name,
            mode="local",
        )
        profile_env = runtime.profile_env
    except (ProfileError, ValueError) as exc:
        eprint(f"{tag('ERROR')} {exc}")
        return profile_env, 1

    if not profile_env:
        eprint(f"{tag('ERROR')} Profile resolved to an empty environment.")
        return profile_env, 1

    return profile_env, 0


# ── Output helpers ──────────────────────────────────────────────────────────


def write_output_file(
    content: str,
    out_path: str | Path,
    warning_prefix: str = "[CONFIG]",
) -> int:
    """Write content to a file with security permissions.

    Creates parent directories if needed, writes content, and sets
    restrictive permissions (0o600).

    Args:
        content: The content to write
        out_path: The output file path
        warning_prefix: Prefix for log messages

    Returns:
        0 on success
    """
    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(content, encoding="utf-8")
    out_file.chmod(0o600)
    eprint(f"{warning_prefix} Written to {out_file.resolve()}")
    return 0


def confirm_stdout_output(
    content: str,
    warning_prefix: str = "[CONFIG]",
) -> int:
    """Output to stdout with confirmation prompt.

    Warns about sensitive values and asks for confirmation before
    writing to stdout.

    Args:
        content: The content to print
        warning_prefix: Prefix for log messages

    Returns:
        0 on success, 1 if user declines or aborts
    """
    eprint(
        f"{warning_prefix} Outputting to stdout. Values may be captured in terminal logs."
    )
    try:
        response = input(f"{warning_prefix} Proceed? [y/N] ")
        if response.lower() not in ("y", "yes"):
            eprint(f"{warning_prefix} Aborted.")
            return 1
    except (EOFError, KeyboardInterrupt):
        eprint()
        eprint(f"{warning_prefix} Aborted.")
        return 1

    print(content)
    return 0


# ── Environment loading ─────────────────────────────────────────────────────


def load_profile_with_tools(
    profile_name: str,
    profiles_path: Path,
    base_env: dict[str, str],
    mode: str,
    show_errors: bool = True,
    agent: str = "",
) -> tuple[dict[str, str], list[str], int]:
    """Load profile env and tools in one call.

    This eliminates the repeated profile loading pattern across subcommands.

    Args:
        profile_name: Name of the profile to load
        profiles_path: Path to the profiles file
        base_env: Base environment from load_env_chain()
        mode: "local"
        show_errors: Whether to print error messages (default True)
        agent: Canonical agent name (e.g. "claude-code").  When empty it is
            inferred from the profiles filename.

    Returns:
        Tuple of (profile_env, tools, exit_code)
        exit_code is 0 on success, 1 on error.
    """
    from codefreedom.config.errors import ProfileError

    profile_env: dict[str, str] = {}
    tools: list[str] = []

    if not profiles_path.exists() and profile_name != "default":
        if show_errors:
            eprint(
                f"[ERROR] Profile '{profile_name}' requested but no profiles file found."
            )
        return profile_env, tools, 1
    elif not profiles_path.exists():
        if show_errors:
            eprint(f"{tag('PROFILE')} No profiles file found. Using defaults only.")
        return profile_env, tools, 0

    try:
        resolved_agent = agent or _agent_name_from_profiles_path(profiles_path)
        runtime = resolve_agent_runtime(
            resolved_agent,
            workspace_dir=Path.cwd(),
            profile_name=profile_name,
            mode=mode,
        )
        profile_env = runtime.profile_env
        tools = runtime.tools
    except (ProfileError, ValueError) as e:
        if show_errors:
            eprint(f"{tag('ERROR')} {e}")
        return profile_env, tools, 1

    return profile_env, tools, 0


def _agent_name_from_profiles_path(profiles_path: Path) -> str:
    """Infer canonical agent name from a profile filename."""
    name = profiles_path.name
    mapping = {
        "claude-code.yaml": "claude-code",
        "mimo-code.yaml": "mimo-code",
        "opencode.yaml": "open-code",
        "open-code.yaml": "open-code",
        "pi-code.yaml": "pi-code",
        "codex-code.yaml": "codex-code",
        "profiles.yaml": "",  # unified format — agent resolved separately
    }
    if name not in mapping:
        raise ValueError(f"Unknown profiles path: {profiles_path}")
    return mapping[name]


# ── Tool execution helpers ──────────────────────────────────────────────────


def acquire_and_run(
    session_id: str,
    tools: list[str],
    profile_name: str,
    run_fn: Callable[[list[str]], int],
) -> int:
    """Acquire tools, run function, and release tools.

    This eliminates the repeated try/finally pattern for tool management.

    Args:
        session_id: Unique session identifier
        tools: List of tools to acquire
        profile_name: Profile name for tool acquisition
        run_fn: Function to call while tools are acquired.
                Receives the list of successfully acquired tool names.

    Returns:
        Exit code from run_fn
    """
    from codefreedom.tools.registry import acquire_tools, release_tools

    acquired_tools: list[str] = []
    if tools:
        eprint(f"{tag('TOOLS')} Profile '{profile_name}' declares tools: {', '.join(tools)}")
        acquired_tools = acquire_tools(session_id, tools, profile_name)
        if acquired_tools:
            eprint(f"{tag('TOOLS')} Running: {', '.join(acquired_tools)}")

    try:
        return run_fn(acquired_tools)
    finally:
        if acquired_tools:
            release_tools(session_id, acquired_tools)


# ── Tool action dispatch ────────────────────────────────────────────────────


def run_tool_action(
    action: str,
    start_fn: Callable[[], int],
    stop_fn: Callable[[], int],
    restart_fn: Callable[[], int],
    status_fn: Callable[[], int],
    url_fn: Callable[[], int] | None = None,
) -> int:
    """Dispatch tool actions (start/stop/restart/status).

    This eliminates the duplicated if/elif dispatch pattern in all tool modules.

    Args:
        action: The action string (start, stop, restart, status, url)
        start_fn: Function to call for start action
        stop_fn: Function to call for stop action
        restart_fn: Function to call for restart action
        status_fn: Function to call for status action
        url_fn: Optional function for url action (chrome only)

    Returns:
        Exit code from the called function
    """
    if action == "start":
        return start_fn()
    elif action == "stop":
        return stop_fn()
    elif action == "restart":
        return restart_fn()
    elif action == "status":
        return status_fn()
    elif action == "url" and url_fn:
        return url_fn()
    else:
        valid_actions = ["start", "stop", "restart", "status"]
        if url_fn:
            valid_actions.append("url")
        eprint(f"{tag('ERROR')} Unknown action: {action}.")
        eprint(f"   Valid actions: {', '.join(valid_actions)}.")
        return 1


# ── Common argument definitions ─────────────────────────────────────────────


def add_profile_args(
    parser: argparse.ArgumentParser,
    *,
    add_list_profiles: bool = True,
) -> None:
    """Add common --profile and --list-profiles arguments to a parser.

    This eliminates the repeated add_argument() calls for these common flags.

    Args:
        parser: The argument parser to add arguments to
        add_list_profiles: Whether to add --list-profiles flag (default True)
    """
    parser.add_argument(
        "--profile",
        type=str,
        default="default",
        metavar="NAME",
        help="Load a named profile (default: 'default')",
    )
    if add_list_profiles:
        parser.add_argument(
            "--list-profiles",
            action="store_true",
            help="List available profiles and exit",
        )


def add_config_args(parser: argparse.ArgumentParser) -> None:
    """Add common --profile and --out arguments for config subcommands.

    This eliminates the repeated add_argument() calls for config subcommands
    (claude config, mimo config).

    Args:
        parser: The argument parser to add arguments to
    """
    parser.add_argument(
        "--profile",
        type=str,
        default="default",
        metavar="NAME",
        help="Profile to resolve (default: 'default')",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        metavar="FILE",
        help="Write to FILE instead of stdout (recommended to avoid leaking secrets)",
    )
