"""Web search tool — headless browser in Docker for web search/scraping.

Part of the unified tool group.  All tools are managed together:
    cf tools start     Start all tools (no-op if already running)
    cf tools stop      Stop all tools
    cf tools restart   Restart all tools
    cf tools status    Show status of all tools

The container runs an MCP-only server with two tools:
    web_search(query) — search configured engines
    web_fetch(url)    — fetch a page (bypasses anti-bot)

Settings are loaded from ~/.codefreedom/profiles/web.yaml.
Use `cf init recipe` to initialize.

Search engines are configured in the profile's 'search_engines' field
(each entry: {url, parser}) and passed to the container as the SEARCH_ENGINES
environment variable (JSON-serialized).
"""

from __future__ import annotations

import argparse
import json
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

from codefreedom.schemas.web import WebConfig

# ── Defaults ─────────────────────────────────────────────────────────────

_DEFAULT_IMAGE = "docker.io/nilayparikh/codefreedom:web-latest"
_DEFAULT_CONTAINER_NAME = "codefreedom-web"
_DEFAULT_PORT = 8420
_DEFAULT_SEARCH_COOLDOWN_SECONDS = 10.0


def _profile_path() -> Path:
    """Return the web tool profile path (~/.codefreedom/profiles/web.yaml)."""
    return tool_profile_path("web.yaml")


# ── Profile loader ───────────────────────────────────────────────────────


def _load_profile() -> dict:
    """Load web tool profile from ~/.codefreedom/profiles/web.yaml.

    Returns a flat dict with keys: image, container_name, port, data_dir, env,
    search_engines, parser_registry.
    Any missing key falls back to the hardcoded default above.
    """
    settings: dict = {
        "image": _DEFAULT_IMAGE,
        "container_name": _DEFAULT_CONTAINER_NAME,
        "port": _DEFAULT_PORT,
        "mcp_path": "/mcp",
        "data_dir": tool_data_dir("web"),
        "env": {},
        "search_engines": {},
        "parser_registry": {},
        "search_cooldown_seconds": _DEFAULT_SEARCH_COOLDOWN_SECONDS,
    }
    return load_tool_profile(
        "web",
        settings,
        "web.yaml",
        schema_class=WebConfig,
        env_port_var="CODEFREEDOM_WEB_PORT",
        extra_keys=[
            "mcp_path",
            "search_engines",
            "parser_registry",
            "search_cooldown_seconds",
        ],
    )


# ── Init ────────────────────────────────────────────────────────────────────


def init_tool() -> int:
    """Initialize the web tool profile via recipes."""
    return init_tool_redirect("web.yaml")


# ── Actions ──────────────────────────────────────────────────────────────


def start(settings: dict) -> int:
    if not start_tool_init_gate("web.yaml", "web"):
        return 1

    _print_tool_notice("web")

    image = settings["image"]
    container_name = settings["container_name"]
    port = settings["port"]
    data_dir = settings["data_dir"]

    if container_is_running(container_name):
        eprint(f"[WEB] Container '{container_name}' is already running.")
        return 0

    if not start_tool_docker_guard("WEB"):
        return 1

    resolved_data = resolve_data_dir(data_dir)
    eprint(f"[WEB] Using data dir: {resolved_data}")

    start_tool_remove_stopped(container_name, "WEB")

    if not start_tool_ensure_image(settings, "WEB"):
        return 1

    # Build environment flags from profile
    env_vars = dict(settings.get("env", {}))
    # Serialize search_engines as SEARCH_ENGINES env var for the container
    search_engines = settings.get("search_engines", {})
    if isinstance(search_engines, dict) and search_engines:
        env_vars["SEARCH_ENGINES"] = json.dumps(search_engines)
    # Serialize parser_registry as PARSER_REGISTRY env var for the container
    parser_registry = settings.get("parser_registry", {})
    if isinstance(parser_registry, dict) and parser_registry:
        env_vars["PARSER_REGISTRY"] = json.dumps(parser_registry)
    # Pass the search cooldown (seconds) into the container
    cooldown = settings.get("search_cooldown_seconds", _DEFAULT_SEARCH_COOLDOWN_SECONDS)
    if cooldown is not None:
        env_vars["SEARCH_COOLDOWN_SECONDS"] = str(float(cooldown))
    env_flags: list[str] = []
    for key, val in env_vars.items():
        env_flags.extend(["-e", f"{key}={val}"])

    eprint(f"[WEB] Starting container '{container_name}'...")
    result = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "--restart",
            "unless-stopped",
            "--shm-size=192m",
            "-m",
            "2g",
            "--memory-swap",
            "2g",
            "-p",
            f"{port}:8420",
            "-v",
            f"{resolved_data}:/userdata",
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

    eprint(f"[WEB] Container started: {result.stdout.strip()[:12]}")
    eprint(f"[WEB] MCP endpoint: http://127.0.0.1:{port}/mcp")
    return 0


def stop(settings: dict) -> int:
    return stop_tool_container(settings, "WEB")


def restart(settings: dict) -> int:
    rc = restart_tool_container(settings, "WEB")
    if rc == 0:
        port = settings["port"]
        eprint(f"[WEB] MCP endpoint: http://127.0.0.1:{port}/mcp")
    return rc


def status(settings: dict) -> int:
    container_name = settings["container_name"]
    port = settings["port"]

    if container_is_running(container_name):
        eprint(f"[WEB] Container '{container_name}' is running.")
        eprint(f"[WEB] MCP endpoint: http://127.0.0.1:{port}/mcp")
        eprint("[WEB] Tools: web_search, web_fetch.")
        return 0

    if container_exists(container_name):
        eprint(f"[WEB] Container '{container_name}' exists but is not running.")
        return 1

    eprint("[WEB] No web container found.")
    eprint("   Use: cf tools start.")
    return 1


# ── Entry point ──────────────────────────────────────────────────────────


def run(args: argparse.Namespace) -> int:
    settings = _load_profile()

    # Override port from CLI if specified
    if getattr(args, "port", None) and args.port != _DEFAULT_PORT:
        settings["port"] = args.port

    if args.action == "start":
        return start(settings)
    elif args.action == "stop":
        return stop(settings)
    elif args.action == "restart":
        return restart(settings)
    elif args.action == "status":
        return status(settings)
    else:
        eprint(f"[ERROR] Unknown action: {args.action}.")
        eprint("   Valid actions: start, stop, restart, status.")
        return 1
