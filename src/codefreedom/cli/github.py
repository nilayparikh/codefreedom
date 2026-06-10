"""GitHub MCP Server tool — stdio↔HTTP bridge over ghcr.io/github/github-mcp-server.

Part of the unified tool group.  All tools are managed together:
    cf tools start     Start all tools (no-op if already running)
    cf tools stop      Stop all tools
    cf tools restart   Restart all tools
    cf tools status    Show status of all tools

The container runs a Python bridge that wraps github-mcp-server stdio with an
HTTP MCP endpoint on port 8082.  Coding agents connect via
http://127.0.0.1:8082/mcp just like the chrome and web tools.

Settings are loaded from ~/.codefreedom/profiles/github.yaml.
Use `cf init recipe` to initialize.
"""

from __future__ import annotations

import argparse
import random
import socket
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

from codefreedom.schemas.github import GithubConfig

# ── Defaults ──────────────────────────────────────────────────────────────────

_DEFAULT_IMAGE = "docker.io/nilayparikh/codefreedom:github-latest"
_DEFAULT_CONTAINER_NAME = "codefreedom-tools-github"
_DEFAULT_PORT = 0  # 0 = auto-pick random free port


# ── Random port helper ────────────────────────────────────────────────────────

_PORT_RANGE_START = 8100
_PORT_RANGE_END = 8199


def _find_free_port() -> int:
    """Find an unused TCP port in the configured range."""
    for _ in range(50):
        port = random.randint(_PORT_RANGE_START, _PORT_RANGE_END)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    # Fallback — let OS pick, localhost only
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get_mapped_port(container_name: str) -> int | None:
    """Return the host port mapped to container port 8082 via docker port."""
    result = subprocess.run(
        ["docker", "port", container_name, "8082"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        # Output: "0.0.0.0:8123" — extract port
        line = result.stdout.strip().split("\n")[0]
        if ":" in line:
            return int(line.rsplit(":", 1)[-1])
    return None


def _profile_path() -> Path:
    """Return the github tool profile path (~/.codefreedom/profiles/github.yaml)."""
    return tool_profile_path("github.yaml")


# ── Profile loader ────────────────────────────────────────────────────────────


def _load_profile() -> dict:
    """Load github tool profile from ~/.codefreedom/profiles/github.yaml.

    Returns a flat dict with keys: image, container_name, port, data_dir, env.
    Any missing key falls back to the hardcoded default above.
    """
    settings: dict = {
        "image": _DEFAULT_IMAGE,
        "container_name": _DEFAULT_CONTAINER_NAME,
        "port": _DEFAULT_PORT,
        "data_dir": tool_data_dir("github"),
        "env": {},
    }
    return load_tool_profile(
        "github",
        settings,
        "github.yaml",
        schema_class=GithubConfig,
        env_port_var="CODEFREEDOM_GITHUB_PORT",
    )


# ── Init ────────────────────────────────────────────────────────────────────


def init_tool() -> int:
    """Initialize the github tool profile via recipes."""
    return init_tool_redirect("github.yaml")


# ── Actions ────────────────────────────────────────────────────────────────────


def start(settings: dict) -> int:
    """Start the GitHub MCP container. Returns exit code."""
    if not start_tool_init_gate("github.yaml", "github"):
        return 1

    _print_tool_notice("github")

    image = settings["image"]
    container_name = settings["container_name"]
    data_dir = settings["data_dir"]
    env_vars = dict(settings.get("env", {}))

    # Validate required token
    token = env_vars.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
    if not token:
        eprint("[ERROR] GITHUB_PERSONAL_ACCESS_TOKEN is not set.")
        eprint("   Set it in ~/.codefreedom/profiles/github.yaml under env:")
        eprint('     "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_..." }')
        return 1

    if container_is_running(container_name):
        port = _get_mapped_port(container_name) or settings["port"]
        eprint(f"[GITHUB] Container '{container_name}' is already running.")
        eprint(f"[GITHUB]   MCP endpoint: http://127.0.0.1:{port}/mcp")
        return 0

    if not start_tool_docker_guard("GITHUB"):
        return 1

    # Resolve & create data directory
    resolved_data = resolve_data_dir(data_dir)
    eprint(f"[GITHUB] Using data dir: {resolved_data}")

    start_tool_remove_stopped(container_name, "GITHUB")

    if not start_tool_ensure_image(settings, "GITHUB"):
        return 1

    # Pick port: use explicit setting, or auto-pick from random range
    host_port = settings["port"]
    if host_port == 0:
        host_port = _find_free_port()

    # Build environment flags
    env_flags: list[str] = []
    for key, val in env_vars.items():
        env_flags.extend(["-e", f"{key}={val}"])

    eprint(f"[GITHUB] Starting container '{container_name}'...")
    eprint(f"[GITHUB]   HTTP MCP port: {host_port}")
    create = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "--restart",
            "unless-stopped",
            "-p",
            f"0.0.0.0:{host_port}:8082",
            "-v",
            f"{resolved_data}:/data",
            *env_flags,
            image,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if create.returncode != 0:
        eprint("[ERROR] Failed to start GitHub MCP container.")
        if create.stderr:
            eprint(f"   {create.stderr.strip()}")
        return 1

    eprint("   [OK] Container started.")
    eprint(f"   MCP endpoint: http://127.0.0.1:{host_port}/mcp")
    return 0


def stop(settings: dict) -> int:
    """Stop and remove the GitHub MCP container. Returns exit code."""
    return stop_tool_container(settings, "GITHUB")


def restart(settings: dict) -> int:
    """Restart the GitHub MCP container using ``docker restart``."""
    rc = restart_tool_container(settings, "GITHUB")
    if rc == 0:
        port = _get_mapped_port(settings["container_name"]) or "?"
        eprint(f"   MCP endpoint: http://127.0.0.1:{port}/mcp")
    return rc


def status(settings: dict) -> int:
    """Show GitHub MCP container status. Returns exit code."""
    container_name = settings["container_name"]

    if container_is_running(container_name):
        port = _get_mapped_port(container_name) or "?"
        eprint(f"[GITHUB] Container '{container_name}' is running.")
        eprint(f"[GITHUB] MCP endpoint: http://127.0.0.1:{port}/mcp")
        eprint("[GITHUB] Tools: GitHub API operations (issues, PRs, repos, etc.)")
        return 0

    if container_exists(container_name):
        eprint(f"[GITHUB] Container '{container_name}' exists but is not running.")
        return 1

    eprint("[GITHUB] No GitHub MCP container found.")
    eprint("   Use: cf tools start")
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
        eprint(f"[ERROR] Unknown action: {args.action}")
        return 1
