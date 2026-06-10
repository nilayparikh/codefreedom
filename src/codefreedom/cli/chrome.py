"""Chrome browser tool — run headless Chrome in Docker for browser automation.

Part of the unified tool group.  All tools are managed together:
    cf tools start     Start all tools (no-op if already running)
    cf tools stop      Stop all tools
    cf tools restart   Restart all tools
    cf tools status    Show status of all tools

Settings are loaded from ~/.codefreedom/profiles/chrome.yaml.
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

from codefreedom.schemas.chrome import ChromeConfig

# ── Defaults ──────────────────────────────────────────────────────────────────

_DEFAULT_IMAGE = "docker.io/nilayparikh/codefreedom:chrome-latest"
_DEFAULT_CONTAINER_NAME = "codefreedom-chrome"
_DEFAULT_PORT = 9222


def _profile_path() -> Path:
    """Return the chrome tool profile path (~/.codefreedom/profiles/chrome.yaml)."""
    return tool_profile_path("chrome.yaml")


# ── Profile loader ────────────────────────────────────────────────────────────


def _load_profile() -> dict:
    """Load chrome tool profile from ~/.codefreedom/profiles/chrome.yaml.

    Returns a flat dict with keys: image, container_name, port, data_dir, env.
    Any missing key falls back to the hardcoded default above.
    """
    settings: dict = {
        "image": _DEFAULT_IMAGE,
        "container_name": _DEFAULT_CONTAINER_NAME,
        "port": _DEFAULT_PORT,
        "mcp_port": 9223,
        "mcp_path": "/mcp",
        "cdp_proxy_port": 9220,
        "data_dir": tool_data_dir("chrome"),
        "env": {},
    }
    return load_tool_profile(
        "chrome",
        settings,
        "chrome.yaml",
        schema_class=ChromeConfig,
        env_port_var="CODEFREEDOM_CHROME_PORT",
        extra_keys=["mcp_port", "mcp_path", "cdp_proxy_port"],
    )


# ── Init ────────────────────────────────────────────────────────────────────


def init_tool() -> int:
    """Initialize the chrome tool profile via recipes."""
    return init_tool_redirect("chrome.yaml")


# ── Actions ────────────────────────────────────────────────────────────────────


def start(settings: dict) -> int:
    """Start the Chrome browser container. Returns exit code."""
    if not start_tool_init_gate("chrome.yaml", "chrome"):
        return 1

    _print_tool_notice("chrome")

    image = settings["image"]
    container_name = settings["container_name"]
    port = settings["port"]
    data_dir = settings["data_dir"]
    env_vars = settings.get("env", {})

    if container_is_running(container_name):
        eprint(f"[CHROME] Container '{container_name}' is already running.")
        return 0

    if not start_tool_docker_guard("CHROME"):
        return 1

    # Resolve & create data directory
    resolved_data = resolve_data_dir(data_dir)
    eprint(f"[CHROME] Using data dir: {resolved_data}")

    start_tool_remove_stopped(container_name, "CHROME")

    if not start_tool_ensure_image(settings, "CHROME"):
        return 1

    # Build environment flags
    env_flags: list[str] = []
    for key, val in env_vars.items():
        env_flags.extend(["-e", f"{key}={val}"])
    # Ensure CHROME_DEBUG_PORT is set (used by the wrapper + healthcheck)
    if "CHROME_DEBUG_PORT" not in env_vars:
        env_flags.extend(["-e", f"CHROME_DEBUG_PORT={port}"])

    # Set MCP_PORT for the container's mcp-proxy bridge
    mcp_port = settings.get("mcp_port", 9223)
    if "MCP_PORT" not in env_vars:
        env_flags.extend(["-e", f"MCP_PORT={mcp_port}"])

    # Set CDP_PROXY_PORT for the socat forwarder.
    cdp_proxy_port = settings.get("cdp_proxy_port", 9220)
    if "CDP_PROXY_PORT" not in env_vars:
        env_flags.extend(["-e", f"CDP_PROXY_PORT={cdp_proxy_port}"])

    # Start container — headless Chrome + MCP proxy.
    # Uses explicit port mapping (not --network host) so the ports are
    # visible in `docker inspect` / `docker ps` and the container is
    # reachable from other Docker containers (e.g. sandboxes) via the
    # Docker bridge network.
    # CDP is exposed via a socat forwarder inside the container
    # (0.0.0.0:CDP_PROXY_PORT -> 127.0.0.1:CHROME_DEBUG_PORT) because
    # Chrome 149+ ignores --remote-debugging-address=0.0.0.0 and only
    # binds to localhost.
    # --shm-size=512m prevents Chrome from crashing on /dev/shm in containers.
    eprint(f"[CHROME] Starting container '{container_name}'...")
    eprint(f"[CHROME]   CDP port: {port}  MCP port: {mcp_port}")
    create = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "--shm-size=512m",
            "--restart",
            "unless-stopped",
            "-p",
            f"0.0.0.0:{port}:{cdp_proxy_port}",
            "-p",
            f"0.0.0.0:{mcp_port}:{mcp_port}",
            "-v",
            f"{resolved_data}:/data/chrome",
            *env_flags,
            image,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if create.returncode != 0:
        eprint("[ERROR] Failed to start Chrome container.")
        if create.stderr:
            eprint(f"   {create.stderr.strip()}")
        return 1

    eprint("   [OK] Container started.")
    eprint(f"   CDP debug URL: http://127.0.0.1:{port}")
    eprint(
        f"   MCP endpoint:  http://127.0.0.1:{mcp_port}{settings.get('mcp_path', '/mcp')}"
    )
    eprint(
        f"   DevTools:      devtools://devtools/bundled/inspector.html?ws=127.0.0.1:{port}"
    )
    return 0


def stop(settings: dict) -> int:
    """Stop and remove the Chrome container. Returns exit code."""
    return stop_tool_container(settings, "CHROME")


def restart(settings: dict) -> int:
    """Restart the Chrome container using ``docker restart``."""
    rc = restart_tool_container(settings, "CHROME")
    if rc == 0:
        port = settings["port"]
        eprint(f"   CDP debug URL: http://127.0.0.1:{port}")
    return rc


def status(settings: dict) -> int:
    """Show Chrome container status. Returns exit code."""
    container_name = settings["container_name"]
    port = settings["port"]

    if container_is_running(container_name):
        eprint(f"[CHROME] Container '{container_name}' is running.")
        eprint(f"[CHROME] CDP debug URL: http://127.0.0.1:{port}")
        eprint(
            f"[CHROME] DevTools: devtools://devtools/bundled/inspector.html?ws=127.0.0.1:{port}"
        )
        return 0

    if container_exists(container_name):
        eprint(f"[CHROME] Container '{container_name}' exists but is not running.")
        return 1

    eprint("[CHROME] No Chrome container found.")
    eprint("   Use: cf tools start")
    return 0


def url(settings: dict) -> int:
    """Print the CDP debug URL. Returns exit code.

    Note: intentionally uses stdout (print) so the URL is machine-readable
    for scripting.  All other output in this module uses eprint (stderr).
    """
    container_name = settings["container_name"]
    port = settings["port"]

    if not container_is_running(container_name):
        eprint("[CHROME] Chrome container is not running.")
        eprint("   Use: cf tools start")
        return 1

    print(f"http://127.0.0.1:{port}")
    return 0


def run(args: argparse.Namespace) -> int:
    """Execute the chrome tool subcommand. Returns exit code."""
    settings = _load_profile()

    # CLI --port flag overrides profile only when explicitly provided
    if getattr(args, "port", None) and args.port != _DEFAULT_PORT:
        settings["port"] = args.port

    action = args.action or "status"

    if action == "start":
        return start(settings)
    elif action == "stop":
        return stop(settings)
    elif action == "restart":
        return restart(settings)
    elif action == "status":
        return status(settings)
    elif action == "url":
        return url(settings)
    else:
        eprint(f"[ERROR] Unknown action: {action}")
        eprint("   Valid actions: start, stop, restart, status, url")
        return 1
