"""Chrome browser tool — run headless Chrome in Docker for browser automation.

Part of the unified tool group.  All tools are managed together:
    cf tools start     Start all tools (no-op if already running)
    cf tools stop      Stop all tools
    cf tools restart   Restart all tools
    cf tools status    Show status of all tools

Settings are loaded from ~/.codefreedom/profiles/chrome.yaml.
Use `cf init` to initialize.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from codefreedom.log import eprint
from codefreedom.cli.docker_utils import (
    container_is_running,
    init_tool_redirect,
    load_tool_profile,
    print_tool_notice,
    resolve_data_dir,
    restart_tool_container,
    start_tool_container,
    start_tool_docker_guard,
    start_tool_init_gate,
    stop_tool_container,
    tool_data_dir,
    tool_profile_path,
)

from codefreedom.tools.schemas.chrome import ChromeConfig

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

    print_tool_notice("chrome")

    container_name = settings["container_name"]
    port = settings["port"]
    env_vars = settings.get("env", {})

    if container_is_running(container_name):
        eprint(f"[CHROME] Container '{container_name}' is already running.")
        return 0

    if not start_tool_docker_guard("CHROME"):
        return 1

    if "CHROME_DEBUG_PORT" not in env_vars:
        settings["env"]["CHROME_DEBUG_PORT"] = str(port)

    mcp_port = settings.get("mcp_port", 9223)
    if "MCP_PORT" not in env_vars:
        settings["env"]["MCP_PORT"] = str(mcp_port)

    cdp_proxy_port = settings.get("cdp_proxy_port", 9220)
    if "CDP_PROXY_PORT" not in env_vars:
        settings["env"]["CDP_PROXY_PORT"] = str(cdp_proxy_port)

    resolved_data = resolve_data_dir(settings["data_dir"])
    eprint(f"[CHROME]   CDP port: {port}  MCP port: {mcp_port}")

    docker_args = [
        "--shm-size=512m",
        "-p", f"0.0.0.0:{port}:{cdp_proxy_port}",
        "-p", f"0.0.0.0:{mcp_port}:{mcp_port}",
        "-v", f"{resolved_data}:/data/chrome",
    ]

    rc = start_tool_container(settings, "CHROME", docker_args)
    if rc != 0:
        return 1

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
    from codefreedom.cli.docker_utils import status_tool_container

    port = settings["port"]
    extra = (
        f"[CHROME] CDP debug URL: http://127.0.0.1:{port}\n"
        f"[CHROME] DevTools: devtools://devtools/bundled/inspector.html?ws=127.0.0.1:{port}"
    )
    return status_tool_container(settings, "CHROME", extra_info=extra)


def url(settings: dict) -> int:
    """Print the CDP debug URL. Returns exit code.

    Note: intentionally uses stdout (print) so the URL is machine-readable
    for scripting.  All other output in this module uses eprint (stderr).
    """
    container_name = settings["container_name"]
    port = settings["port"]

    if not container_is_running(container_name):
        eprint("[CHROME] Chrome container is not running.")
        eprint("   Use: cf tools start.")
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
    from codefreedom.cli.common import run_tool_action

    return run_tool_action(
        action,
        start_fn=lambda: start(settings),
        stop_fn=lambda: stop(settings),
        restart_fn=lambda: restart(settings),
        status_fn=lambda: status(settings),
        url_fn=lambda: url(settings),
    )


# ── Tool class for MCP endpoint registration ──────────────────────────────


class ChromeTool:
    @property
    def mcp_server_name(self) -> str:
        return "chrome-devtools"

    @property
    def mcp_endpoint(self) -> tuple[int, str]:
        settings = _load_profile()
        port = settings.get("mcp_port", 9223)
        path = settings.get("mcp_path", "/mcp")
        return port, path
