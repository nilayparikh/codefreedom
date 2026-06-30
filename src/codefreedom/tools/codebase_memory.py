"""Codebase Memory MCP tool — stdio↔HTTP bridge over codebase-memory-mcp.

Part of the unified tool group.  All tools are managed together:
    cf run tools start     Start all tools (no-op if already running)
    cf run tools stop      Stop all tools
    cf run tools restart   Restart all tools
    cf run tools status    Show status of all tools

The container runs a Python bridge that wraps the upstream
codebase-memory-mcp stdio MCP server with an HTTP MCP endpoint on
port 8330.  Coding agents connect via http://127.0.0.1:8330/mcp just
like the chrome, web, and github tools.

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

from codefreedom.tools.schemas.codebase_memory import CodebaseMemoryConfig

# ── Defaults ──────────────────────────────────────────────────────────────────

_DEFAULT_IMAGE = "docker.io/nilayparikh/codefreedom:codebase-memory-latest"
_DEFAULT_CONTAINER_NAME = "codefreedom-tools-codebase-memory"
_DEFAULT_PORT = 8330
_DEFAULT_UI_PORT = 9749
_DEFAULT_LOG_LEVEL = "info"


# ── Profile loader ────────────────────────────────────────────────────────────


def _load_profile() -> dict:
    """Load codebase-memory tool settings from the unified profiles.yaml.

    Returns a flat dict with keys: image, container_name, port, ui_port,
    data_dir, bind_host, remote_url, env, enable_ui, log_level,
    auto_index.

    Any missing key falls back to the hardcoded default above.
    """
    settings: dict = {
        "image": _DEFAULT_IMAGE,
        "container_name": _DEFAULT_CONTAINER_NAME,
        "port": _DEFAULT_PORT,
        "ui_port": _DEFAULT_UI_PORT,
        "data_dir": tool_data_dir("codebase-memory"),
        "bind_host": "0.0.0.0",
        "remote_url": "",
        "enable_ui": False,
        "log_level": _DEFAULT_LOG_LEVEL,
        "auto_index": False,
        "env": {},
    }
    return load_tool_profile(
        "codebase-memory",
        settings,
        schema_class=CodebaseMemoryConfig,
        env_port_var="CODEFREEDOM_CODEBASE_MEMORY_PORT",
        env_port_vars={"ui_port": "CODEFREEDOM_CODEBASE_MEMORY_UI_PORT"},
        extra_keys=["ui_port", "enable_ui", "log_level", "auto_index"],
    )


# ── Init ────────────────────────────────────────────────────────────────────


def init_tool() -> int:
    """Initialize the codebase-memory tool profile via recipes."""
    return init_tool_redirect("codebase-memory")


# ── Actions ───────────────────────────────────────────────────────────────────


def start(settings: dict) -> int:
    """Start the Codebase Memory MCP container. Returns exit code."""
    if not start_tool_init_gate("codebase-memory"):
        return 1

    print_tool_notice("codebase-memory")

    container_name = settings["container_name"]
    port = settings["port"]
    bind_host = settings.get("bind_host", "0.0.0.0")

    if container_is_running(container_name):
        eprint(f"{tag('CODEBASE-MEMORY')} Container '{container_name}' is already running.")
        eprint(f"{tag('CODEBASE-MEMORY')}   MCP endpoint: http://127.0.0.1:{port}/mcp")
        return 0

    if not start_tool_docker_guard("CODEBASE-MEMORY"):
        return 1

    env_vars = dict(settings.get("env", {}))
    settings["env"] = env_vars

    env_vars.setdefault("CBM_LOG_LEVEL", str(settings.get("log_level", _DEFAULT_LOG_LEVEL)))
    env_vars.setdefault("CBM_CACHE_DIR", "/cache")

    if settings.get("auto_index"):
        env_vars["CBM_AUTO_INDEX"] = "true"

    if settings.get("enable_ui"):
        env_vars["ENABLE_UI"] = "1"

    resolved_data = resolve_data_dir(settings["data_dir"])
    docker_args = [
        "--shm-size=512m",
        "-m",
        "4g",
        "--memory-swap",
        "4g",
        "-p",
        f"{bind_host}:{port}:8330",
        "-v",
        f"{resolved_data}:/cache",
    ]

    if settings.get("enable_ui"):
        ui_port = settings.get("ui_port", _DEFAULT_UI_PORT)
        docker_args.extend(["-p", f"{bind_host}:{ui_port}:9749"])

    rc = start_tool_container(settings, "CODEBASE-MEMORY", docker_args)
    if rc != 0:
        return 1

    eprint(f"{tag('CODEBASE-MEMORY')} Container started.")
    eprint(f"{tag('CODEBASE-MEMORY')} MCP endpoint: http://127.0.0.1:{port}/mcp")
    if settings.get("enable_ui"):
        ui_port = settings.get("ui_port", _DEFAULT_UI_PORT)
        eprint(f"{tag('CODEBASE-MEMORY')} Graph UI:    http://127.0.0.1:{ui_port}/")
    return 0


def stop(settings: dict) -> int:
    """Stop and remove the Codebase Memory MCP container. Returns exit code."""
    return stop_tool_container(settings, "CODEBASE-MEMORY")


def restart(settings: dict) -> int:
    """Restart the Codebase Memory MCP container using ``docker restart``."""
    rc = restart_tool_container(settings, "CODEBASE-MEMORY")
    if rc == 0:
        port = settings["port"]
        eprint(f"{tag('CODEBASE-MEMORY')} MCP endpoint: http://127.0.0.1:{port}/mcp")
        if settings.get("enable_ui"):
            ui_port = settings.get("ui_port", _DEFAULT_UI_PORT)
            eprint(f"{tag('CODEBASE-MEMORY')} Graph UI:    http://127.0.0.1:{ui_port}/")
    return rc


def status(settings: dict) -> int:
    """Show Codebase Memory MCP container status. Returns exit code."""
    from codefreedom.cli.docker_utils import status_tool_container

    port = settings["port"]
    extra = f"[CODEBASE-MEMORY] MCP endpoint: http://127.0.0.1:{port}/mcp"
    if settings.get("enable_ui"):
        ui_port = settings.get("ui_port", _DEFAULT_UI_PORT)
        extra += (
            f"\n[CODEBASE-MEMORY] Graph UI:    http://127.0.0.1:{ui_port}/"
            "\n[CODEBASE-MEMORY] Tools: index_repository, search_graph, trace_path,"
            " query_graph, get_architecture, get_code_snippet, search_code,"
            " detect_changes, manage_adr, list_projects, delete_project,"
            " index_status, get_graph_schema, ingest_traces."
        )
    else:
        extra += (
            "\n[CODEBASE-MEMORY] Tools: index_repository, search_graph, trace_path,"
            " query_graph, get_architecture, get_code_snippet, search_code,"
            " detect_changes, manage_adr, list_projects, delete_project,"
            " index_status, get_graph_schema, ingest_traces."
        )
    return status_tool_container(settings, "CODEBASE-MEMORY", extra_info=extra)


# ── Entry point ──────────────────────────────────────────────────────────


def run(args: argparse.Namespace) -> int:
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


class CodebaseMemoryTool:
    @property
    def mcp_server_name(self) -> str:
        return "codebase-memory"

    @property
    def mcp_endpoint(self) -> tuple[int, str]:
        settings = _load_profile()
        port = settings.get("port", _DEFAULT_PORT)
        return port, "/mcp"
