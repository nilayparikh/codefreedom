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

_TOOLS: list[tuple[str, str, callable, callable]] = [
    ("chrome", "Chrome browser", chrome_start, chrome_stop),
    ("web", "Web search", web_start, web_stop),
    ("github", "GitHub MCP", github_start, github_stop),
    ("web-bridge", "Web bridge", web_bridge_start, web_bridge_stop),
]


def _load_all_settings() -> list[tuple[str, str, dict]]:
    """Load settings for all tools. Returns (name, label, settings) tuples."""
    results: list[tuple[str, str, dict]] = []
    for name, label, _start, _stop in _TOOLS:
        try:
            if name == "chrome":
                settings = chrome_load_profile()
            elif name == "web":
                settings = web_load_profile()
            elif name == "github":
                settings = github_load_profile()
            elif name == "web-bridge":
                settings = web_bridge_load_profile()
            else:
                continue
            results.append((name, label, settings))
        except Exception as exc:
            eprint(f"[tools] Failed to load profile for '{label}': {exc}")
    return results


def _run_tool(name: str, label: str, settings: dict, action: str) -> int:
    """Run a single tool action. Returns 0 on success."""
    from codefreedom.cli.chrome import start as ch_start, stop as ch_stop
    from codefreedom.cli.web import start as w_start, stop as w_stop
    from codefreedom.cli.github import start as gh_start, stop as gh_stop
    from codefreedom.cli.web_bridge import start as wb_start, stop as wb_stop

    starters = {
        "chrome": ch_start,
        "web": w_start,
        "github": gh_start,
        "web-bridge": wb_start,
    }
    stoppers = {
        "chrome": ch_stop,
        "web": w_stop,
        "github": gh_stop,
        "web-bridge": wb_stop,
    }

    if action == "start":
        return starters[name](settings)
    elif action == "stop":
        return stoppers[name](settings)
    elif action == "restart":
        stoppers[name](settings)
        return starters[name](settings)
    return 0


def start_all() -> int:
    """Start all tools (no-op if already running). Returns exit code."""
    failures = 0
    for name, label, settings in _load_all_settings():
        eprint(f"[tools] Starting {label}...")
        if _run_tool(name, label, settings, "start") != 0:
            eprint(f"[tools]   {label} FAILED")
            failures += 1
    if failures:
        eprint(f"[tools] {failures} tool(s) failed to start.")
        return 1
    eprint("[tools] All tools started.")
    return 0


def stop_all() -> int:
    """Stop all tools. Returns exit code."""
    failures = 0
    for name, label, settings in _load_all_settings():
        eprint(f"[tools] Stopping {label}...")
        if _run_tool(name, label, settings, "stop") != 0:
            eprint(f"[tools]   {label} FAILED")
            failures += 1
    if failures:
        return 1
    eprint("[tools] All tools stopped.")
    return 0


def restart_all() -> int:
    """Restart all tools. Returns exit code."""
    failures = 0
    for name, label, settings in _load_all_settings():
        eprint(f"[tools] Restarting {label}...")
        if _run_tool(name, label, settings, "restart") != 0:
            eprint(f"[tools]   {label} FAILED")
            failures += 1
    if failures:
        return 1
    eprint("[tools] All tools restarted.")
    return 0


def status_all() -> int:
    """Show status of all tools. Returns exit code (1 if any are down)."""
    all_running = True
    for name, label, settings in _load_all_settings():
        container_name = settings.get("container_name", f"codefreedom-{name}")
        if container_is_running(container_name):
            port = settings.get("port", "?")
            eprint(f"[tools]   [{label:15}] RUNNING  ({container_name}, port {port})")
        else:
            all_running = False
            eprint(f"[tools]   [{label:15}] STOPPED  ({container_name})")
    if all_running:
        eprint("[tools] All tools are running.")
        return 0
    eprint("[tools] Some tools are not running. Use 'cf tools start'.")
    return 1


def ensure_tools() -> int:
    """Ensure all tools are running (start if missing). Used by cf px / cf cc."""
    failures = 0
    for name, label, settings in _load_all_settings():
        container_name = settings.get("container_name", f"codefreedom-{name}")
        if not container_is_running(container_name):
            eprint(f"[tools] Auto-starting {label} ({container_name})...")
            if _run_tool(name, label, settings, "start") != 0:
                eprint(f"[tools]   {label} FAILED — continuing.")
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
