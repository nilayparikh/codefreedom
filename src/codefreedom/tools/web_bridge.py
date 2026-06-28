"""Web search bridge tool — SearXNG-shaped HTTP bridge in front of Camoufox MCP.

Part of the unified tool group.  All tools are managed together:
    cf run tools start     Start all tools (no-op if already running)
    cf run tools stop      Stop all tools
    cf run tools restart   Restart all tools
    cf run tools status    Show status of all tools

Translates SearXNG-style /search requests into MCP calls against the
Camoufox web_search tool.  LiteLLM's websearch_interception routes Claude
Code's native WebSearch through this bridge.

Settings are loaded from the unified ~/.codefreedom/config/profiles.yaml.
"""

from __future__ import annotations

import argparse

from codefreedom.log import eprint, tag
from codefreedom.core.container import (
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
)

from codefreedom.tools.schemas.web_bridge import WebBridgeConfig

# ── Defaults ──────────────────────────────────────────────────────────────────

_DEFAULT_IMAGE = "docker.io/nilayparikh/codefreedom:web-bridge-latest"
_DEFAULT_CONTAINER_NAME = "codefreedom-web-bridge"
_DEFAULT_PORT = 8500


# ── Profile loader ────────────────────────────────────────────────────────────


def _load_profile() -> dict:
    """Load web-bridge tool settings from the unified profiles.yaml.

    Returns a flat dict with keys: image, container_name, port, data_dir, env.
    Any missing key falls back to the hardcoded default above.
    """
    settings: dict = {
        "image": _DEFAULT_IMAGE,
        "container_name": _DEFAULT_CONTAINER_NAME,
        "port": _DEFAULT_PORT,
        "data_dir": tool_data_dir("web-bridge"),
        "bind_host": "0.0.0.0",
        "remote_url": "",
        "env": {},
    }
    return load_tool_profile(
        "web-bridge",
        settings,
        schema_class=WebBridgeConfig,
        env_port_var="CODEFREEDOM_WEB_BRIDGE_PORT",
        extra_keys=["bind_host", "remote_url"],
    )


# ── Init ──────────────────────────────────────────────────────────────────────


def init_tool() -> int:
    """Initialize the web-bridge tool profile via recipes."""
    return init_tool_redirect("web-bridge")


# ── Actions ───────────────────────────────────────────────────────────────────


def start(settings: dict) -> int:
    """Start the web-bridge container. Returns exit code."""
    if not start_tool_init_gate("web-bridge"):
        return 1

    print_tool_notice("web-bridge")

    container_name = settings["container_name"]
    port = settings["port"]
    bind_host = settings.get("bind_host", "0.0.0.0")

    if container_is_running(container_name):
        eprint(f"{tag('WEB-BRIDGE')} Container '{container_name}' is already running.")
        return 0

    if not start_tool_docker_guard("WEB-BRIDGE"):
        return 1

    resolved_data = resolve_data_dir(settings["data_dir"])
    docker_args = [
        "-p",
        f"{bind_host}:{port}:8500",
        "-v",
        f"{resolved_data}:/app/data",
    ]

    rc = start_tool_container(settings, "WEB-BRIDGE", docker_args)
    if rc != 0:
        return 1

    eprint(f"{tag('WEB-BRIDGE')} Container started.")
    eprint(f"{tag('WEB-BRIDGE')} SearXNG endpoint: http://127.0.0.1:{port}/search")
    eprint(f"{tag('WEB-BRIDGE')} Health: http://127.0.0.1:{port}/healthz")
    return 0


def stop(settings: dict) -> int:
    """Stop and remove the web-bridge container. Returns exit code."""
    return stop_tool_container(settings, "WEB-BRIDGE")


def restart(settings: dict) -> int:
    """Restart the web-bridge container. Returns exit code."""
    rc = restart_tool_container(settings, "WEB-BRIDGE")
    if rc == 0:
        port = settings["port"]
        eprint(f"{tag('WEB-BRIDGE')} SearXNG endpoint: http://127.0.0.1:{port}/search")
    return rc


def status(settings: dict) -> int:
    """Show web-bridge container status. Returns exit code."""
    from codefreedom.cli.docker_utils import status_tool_container

    port = settings["port"]
    extra = (
        f"[WEB-BRIDGE] SearXNG endpoint: http://127.0.0.1:{port}/search\n"
        f"[WEB-BRIDGE] Health: http://127.0.0.1:{port}/healthz"
    )
    return status_tool_container(settings, "WEB-BRIDGE", extra_info=extra)


def run(args: argparse.Namespace) -> int:
    """Execute the web-bridge tool subcommand. Returns exit code."""
    from codefreedom.core.tool_base import dispatch_tool_run

    return dispatch_tool_run(
        args,
        load_profile=_load_profile,
        default_port=_DEFAULT_PORT,
        start=start,
        stop=stop,
        restart=restart,
        status=status,
    )


# ── Tool class for MCP endpoint registration ──────────────────────────────


class WebBridgeTool:
    @property
    def mcp_server_name(self) -> str:
        return "web-bridge"

    @property
    def mcp_endpoint(self) -> tuple[int, str]:
        settings = _load_profile()
        port = settings.get("port", 8500)
        return port, "/search"
