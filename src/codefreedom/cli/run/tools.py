"""Unified tools command — manage all auxiliary tools as a group.

Usage:
    codefreedom tools start    Start all tools (no-op if already running)
    codefreedom tools stop     Stop all tools
    codefreedom tools restart  Restart all tools
    codefreedom tools status   Show status of all tools

Tools use Docker as the source of truth — no /proc tracking.
Profiles are loaded from ~/.codefreedom/profiles/.

Lifecycle orchestration is owned by tools/registry.py.
This module handles CLI parsing, user output, and delegates to the registry.
"""

from __future__ import annotations

import argparse

from codefreedom.log import eprint, tag
from codefreedom.tools.registry import (
    get_all_tool_status,
    start_all_tools,
    stop_all_tools,
)

_TOOL_NAMES: set[str] = {"chrome", "web", "github", "web-bridge"}


def start_all(selected: set[str] | None = None) -> int:
    """Start tools (no-op if already running). Returns exit code."""
    eprint(f"{tag('TOOLS')} Starting tools...")
    rc = start_all_tools(selected)
    if rc == 0:
        eprint(f"{tag('TOOLS')} All tools started.")
    return rc


def stop_all(selected: set[str] | None = None) -> int:
    """Stop tools. Returns exit code."""
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
    eprint(f"{tag('TOOLS')} Some tools are not running. Use 'cf tools start'.")
    return 1


def ensure_tools(selected: set[str] | None = None) -> int:
    """Ensure tools are running (start if missing). Used by cf px / cf cc."""
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
