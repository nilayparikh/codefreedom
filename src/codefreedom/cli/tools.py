"""Unified tools command — manage all auxiliary tools as a group.

Usage:
    codefreedom tools start    Start all tools (no-op if already running)
    codefreedom tools stop     Stop all tools
    codefreedom tools restart  Restart all tools
    codefreedom tools status   Show status of all tools

Tools use Docker as the source of truth — no /proc tracking.
Profiles are loaded from ~/.codefreedom/profiles/.
"""

from __future__ import annotations

import argparse
from typing import Callable

from codefreedom.env_loader import eprint
from codefreedom.cli.docker_utils import container_is_running
from codefreedom.cli.chrome import (
    _load_profile as chrome_load_profile,
    start as chrome_start,
    stop as chrome_stop,
)
from codefreedom.cli.web import (
    _load_profile as web_load_profile,
    start as web_start,
    stop as web_stop,
)
from codefreedom.cli.github import (
    _load_profile as github_load_profile,
    start as github_start,
    stop as github_stop,
)
from codefreedom.cli.web_bridge import (
    _load_profile as web_bridge_load_profile,
    start as web_bridge_start,
    stop as web_bridge_stop,
)

_TOOLS: list[tuple[str, str, Callable, Callable, Callable]] = [
    ("chrome", "Chrome browser", chrome_load_profile, chrome_start, chrome_stop),
    ("web", "Web search", web_load_profile, web_start, web_stop),
    ("github", "GitHub MCP", github_load_profile, github_start, github_stop),
    (
        "web-bridge",
        "Web bridge",
        web_bridge_load_profile,
        web_bridge_start,
        web_bridge_stop,
    ),
]


def _load_all_settings() -> list[tuple[str, str, dict, Callable, Callable]]:
    """Load settings for all tools. Returns (name, label, settings, start_fn, stop_fn) tuples."""
    results: list[tuple[str, str, dict, Callable, Callable]] = []
    for name, label, load_fn, start_fn, stop_fn in _TOOLS:
        try:
            settings = load_fn()
            results.append((name, label, settings, start_fn, stop_fn))
        except Exception as exc:
            eprint(f"[TOOLS] Failed to load profile for '{label}': {exc}")
    return results


def _for_each_tool(action: str) -> int:
    """Run an action across all tools. Returns exit code (0 if all ok)."""
    failures = 0
    verb = action.capitalize().rstrip("e") + "ing"
    for _name, label, settings, start_fn, stop_fn in _load_all_settings():
        eprint(f"[TOOLS] {verb} {label}...")
        if action == "start":
            rc = start_fn(settings)
        elif action == "stop":
            rc = stop_fn(settings)
        elif action == "restart":
            stop_fn(settings)
            rc = start_fn(settings)
        else:
            rc = 0
        if rc != 0:
            eprint(f"[TOOLS] {label} failed.")
            failures += 1
    if failures:
        eprint(f"[TOOLS] {failures} tool(s) failed to {action}.")
        return 1
    eprint(f"[TOOLS] All tools {action}ed.")
    return 0


def start_all() -> int:
    """Start all tools (no-op if already running). Returns exit code."""
    return _for_each_tool("start")


def stop_all() -> int:
    """Stop all tools. Returns exit code."""
    return _for_each_tool("stop")


def restart_all() -> int:
    """Restart all tools. Returns exit code."""
    return _for_each_tool("restart")


def status_all() -> int:
    """Show status of all tools. Returns exit code (1 if any are down)."""
    all_running = True
    for name, label, settings, _start_fn, _stop_fn in _load_all_settings():
        container_name = settings.get("container_name", f"codefreedom-{name}")
        if container_is_running(container_name):
            port = settings.get("port", "?")
            eprint(f"[TOOLS] {label:15} RUNNING  ({container_name}, port {port})")
        else:
            all_running = False
            eprint(f"[TOOLS] {label:15} STOPPED  ({container_name})")
    if all_running:
        eprint("[TOOLS] All tools are running.")
        return 0
    eprint("[TOOLS] Some tools are not running. Use 'cf tools start'.")
    return 1


def ensure_tools() -> int:
    """Ensure all tools are running (start if missing). Used by cf px / cf cc."""
    failures = 0
    for name, label, settings, start_fn, _stop_fn in _load_all_settings():
        container_name = settings.get("container_name", f"codefreedom-{name}")
        if not container_is_running(container_name):
            eprint(f"[TOOLS] Auto-starting {label} ({container_name})...")
            if start_fn(settings) != 0:
                eprint(f"[TOOLS] {label} failed — continuing.")
                failures += 1
    if failures:
        return 1
    return 0


def run(args: argparse.Namespace) -> int:
    """Execute the tools subcommand. Returns exit code."""
    action = args.action or "status"
    if action == "start":
        return start_all()
    elif action == "stop":
        return stop_all()
    elif action == "restart":
        return restart_all()
    elif action == "status":
        return status_all()
    else:
        eprint(f"[ERROR] Unknown action: {action}")
        eprint("   Valid actions: start, stop, restart, status")
        return 1
