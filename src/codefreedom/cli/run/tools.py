"""Unified tools command — manage all auxiliary tools as a group.

Usage:
    codefreedom run tools start    Start all tools (no-op if already running)
    codefreedom run tools stop     Stop all tools
    codefreedom run tools restart  Restart all tools
    codefreedom run tools status   Show status of all tools

Tools use Docker as the source of truth — no /proc tracking.
Profiles are loaded from ~/.codefreedom/profiles/.

Lifecycle orchestration is owned by tools/registry.py.
This module handles CLI parsing, user output, and delegates to the registry.
"""

from __future__ import annotations

import argparse

from codefreedom.config import load_config
from codefreedom.config.errors import ConfigError
from codefreedom.log import eprint, tag
from codefreedom.tools.registry import (
    get_all_tool_status,
    start_all_tools,
    stop_all_tools,
)

_TOOL_NAMES: set[str] = {"chrome", "web", "github", "web-bridge"}


def _remote_tools(selected: set[str] | None = None) -> dict[str, str]:
    try:
        config = load_config()
    except ConfigError:
        return {}
    remote: dict[str, str] = {}
    for tool_name in _TOOL_NAMES:
        if selected and tool_name not in selected:
            continue
        tool_cfg = config.for_tool(tool_name)
        remote_url = str(tool_cfg.extra.get("remote_url", "") or "")
        if remote_url:
            remote[tool_name] = remote_url
    return remote


def _filter_remote(selected: set[str] | None) -> tuple[set[str] | None, bool]:
    """Print remote-tool warnings and return the local-only subset.

    Returns ``(filtered_selected, should_return)``.  When
    ``should_return`` is True, every selected tool is remote and the
    caller should short-circuit with exit code 1.
    """
    remote = _remote_tools(selected)
    if not remote:
        return selected, False
    for tool_name, remote_url in remote.items():
        eprint(f"{tag('TOOLS')} Tool '{tool_name}' is configured remote at {remote_url}.")
    eprint("   Remove remote settings to run those tools locally.")
    filtered = {name for name in (selected or _TOOL_NAMES) if name not in remote}
    if not filtered:
        return None, True
    return filtered, False


def start_all(selected: set[str] | None = None) -> int:
    """Start tools (no-op if already running). Returns exit code."""
    selected, should_return = _filter_remote(selected)
    if should_return:
        return 1
    eprint(f"{tag('TOOLS')} Starting tools...")
    rc = start_all_tools(selected)
    if rc == 0:
        eprint(f"{tag('TOOLS')} All tools started.")
    return rc


def stop_all(selected: set[str] | None = None) -> int:
    """Stop tools. Returns exit code."""
    selected, should_return = _filter_remote(selected)
    if should_return:
        return 1
    eprint(f"{tag('TOOLS')} Stopping tools...")
    rc = stop_all_tools(selected)
    if rc == 0:
        eprint(f"{tag('TOOLS')} All tools stopped.")
    return rc


def restart_all(selected: set[str] | None = None) -> int:
    """Restart tools. Returns exit code."""
    stop_all(selected)
    return start_all(selected)


def status_all(selected: set[str] | None = None) -> int:
    """Show status of tools. Returns exit code (1 if any are down)."""
    all_running = True
    for name, label, running in get_all_tool_status():
        if selected and name not in selected:
            continue
        if running:
            eprint(f"{tag('TOOLS')} {label:15} RUNNING")
        else:
            all_running = False
            eprint(f"{tag('TOOLS')} {label:15} STOPPED")
    if all_running:
        eprint(f"{tag('TOOLS')} All tools are running.")
        return 0
    eprint(f"{tag('TOOLS')} Some tools are not running. Use 'cf run tools start'.")
    return 1


def ensure_tools(selected: set[str] | None = None) -> int:
    """Ensure tools are running (start if missing). Used by cf r px / cf r ag cc."""
    eprint(f"{tag('TOOLS')} Ensuring tools are running...")
    return start_all_tools(selected)


def run(args: argparse.Namespace) -> int:
    """Execute the tools subcommand. Returns exit code."""
    action = args.action or "status"

    selected: set[str] | None = None
    if any(getattr(args, name, False) for name in _TOOL_NAMES):
        selected = {name for name in _TOOL_NAMES if getattr(args, name, False)}

    if action == "start":
        return start_all(selected)
    elif action == "stop":
        return stop_all(selected)
    elif action == "restart":
        return restart_all(selected)
    elif action == "status":
        return status_all(selected)
    else:
        eprint(f"{tag('ERROR')} Unknown action: {action}")
        eprint("   Valid actions: start, stop, restart, status")
        return 1
