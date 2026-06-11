"""Web search bridge tool — SearXNG-shaped HTTP bridge in front of Camoufox MCP.

Part of the unified tool group.  All tools are managed together:
    cf tools start     Start all tools (no-op if already running)
    cf tools stop      Stop all tools
    cf tools restart   Restart all tools
    cf tools status    Show status of all tools

Translates SearXNG-style /search requests into MCP calls against the
Camoufox web_search tool.  LiteLLM's websearch_interception routes Claude
Code's native WebSearch through this bridge.

Settings are loaded from ~/.codefreedom/profiles/web-bridge.yaml.
Use `cf init recipe` to initialize.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from codefreedom.env_loader import eprint
from codefreedom.cli.docker_utils import (
    container_exists,
    container_is_running,
    init_tool_redirect,
    load_tool_profile,
    resolve_data_dir,
    restart_tool_container,
    start_tool_docker_guard,
    start_tool_ensure_image,
    start_tool_init_gate,
    start_tool_remove_stopped,
    stop_tool_container,
    tool_data_dir,
    tool_profile_path,
)
from codefreedom.cli.tool_init_utils import (
    _print_tool_notice,
)

from codefreedom.schemas.web_bridge import WebBridgeConfig

# ── Defaults ──────────────────────────────────────────────────────────────────

_DEFAULT_IMAGE = "docker.io/nilayparikh/codefreedom:web-bridge"
_DEFAULT_CONTAINER_NAME = "codefreedom-web-bridge"
_DEFAULT_PORT = 8500


def _profile_path() -> Path:
    """Return the web-bridge tool profile path (~/.codefreedom/profiles/web-bridge.yaml)."""
    return tool_profile_path("web-bridge.yaml")


# ── Profile loader ────────────────────────────────────────────────────────────


def _load_profile() -> dict:
    """Load web-bridge tool profile from ~/.codefreedom/profiles/web-bridge.yaml.

    Returns a flat dict with keys: image, container_name, port, data_dir, env.
    Any missing key falls back to the hardcoded default above.
    """
    settings: dict = {
        "image": _DEFAULT_IMAGE,
        "container_name": _DEFAULT_CONTAINER_NAME,
        "port": _DEFAULT_PORT,
        "data_dir": tool_data_dir("web-bridge"),
        "env": {},
    }
    return load_tool_profile(
        "web_bridge",
        settings,
        "web-bridge.yaml",
        schema_class=WebBridgeConfig,
        env_port_var="CODEFREEDOM_WEB_BRIDGE_PORT",
    )


# ── Init ──────────────────────────────────────────────────────────────────────


def init_tool() -> int:
    """Initialize the web-bridge tool profile via recipes."""
    return init_tool_redirect("web-bridge.yaml")


# ── Actions ───────────────────────────────────────────────────────────────────


def start(settings: dict) -> int:
    """Start the web-bridge container. Returns exit code."""
    if not start_tool_init_gate("web-bridge.yaml", "web-bridge"):
        return 1

    _print_tool_notice("web-bridge")

    image = settings["image"]
    container_name = settings["container_name"]
    port = settings["port"]
    data_dir = settings["data_dir"]
    env_vars = dict(settings.get("env", {}))

    if container_is_running(container_name):
        eprint(f"[WEB-BRIDGE] Container '{container_name}' is already running.")
        return 0

    if not start_tool_docker_guard("WEB-BRIDGE"):
        return 1

    resolved_data = resolve_data_dir(data_dir)
    eprint(f"[WEB-BRIDGE] Using data dir: {resolved_data}")

    start_tool_remove_stopped(container_name, "WEB-BRIDGE")

    if not start_tool_ensure_image(settings, "WEB-BRIDGE"):
        return 1

    env_flags: list[str] = []
    for key, val in env_vars.items():
        env_flags.extend(["-e", f"{key}={val}"])

    eprint(f"[WEB-BRIDGE] Starting container '{container_name}'...")
    result = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "--restart",
            "unless-stopped",
            "-p",
            f"{port}:8500",
            "-v",
            f"{resolved_data}:/app/data",
            *env_flags,
            image,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    if result.returncode != 0:
        eprint(f"[ERROR] Failed to start container: {result.stderr.strip()}")
        return 1

    eprint(f"[WEB-BRIDGE] Container started: {result.stdout.strip()[:12]}")
    eprint(f"[WEB-BRIDGE] SearXNG endpoint: http://127.0.0.1:{port}/search")
    eprint(f"[WEB-BRIDGE] Health: http://127.0.0.1:{port}/healthz")
    return 0


def stop(settings: dict) -> int:
    """Stop and remove the web-bridge container. Returns exit code."""
    return stop_tool_container(settings, "WEB-BRIDGE")


def restart(settings: dict) -> int:
    """Restart the web-bridge container. Returns exit code."""
    rc = restart_tool_container(settings, "WEB-BRIDGE")
    if rc == 0:
        port = settings["port"]
        eprint(f"[WEB-BRIDGE] SearXNG endpoint: http://127.0.0.1:{port}/search")
    return rc


def status(settings: dict) -> int:
    """Show web-bridge container status. Returns exit code."""
    container_name = settings["container_name"]
    port = settings["port"]

    if container_is_running(container_name):
        eprint(f"[WEB-BRIDGE] Container '{container_name}' is running.")
        eprint(f"[WEB-BRIDGE] SearXNG endpoint: http://127.0.0.1:{port}/search")
        eprint(f"[WEB-BRIDGE] Health: http://127.0.0.1:{port}/healthz")
        return 0

    if container_exists(container_name):
        eprint(f"[WEB-BRIDGE] Container '{container_name}' exists but is not running.")
        return 1

    eprint("[WEB-BRIDGE] No web-bridge container found.")
    eprint("   Use: cf tools start.")
    return 1


def run(args: argparse.Namespace) -> int:
    """Execute the web-bridge tool subcommand. Returns exit code."""
    settings = _load_profile()

    action = args.action or "status"

    if action == "start":
        return start(settings)
    elif action == "stop":
        return stop(settings)
    elif action == "restart":
        return restart(settings)
    elif action == "status":
        return status(settings)
    else:
        eprint(f"[ERROR] Unknown action: {action}.")
        eprint("   Valid actions: start, stop, restart, status.")
        return 1
        return 1
