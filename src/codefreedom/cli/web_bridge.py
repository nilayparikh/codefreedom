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
import os
import subprocess
from pathlib import Path

import yaml

from codefreedom.env_loader import eprint
from codefreedom.interpolate import interpolate_all_strings
from codefreedom.cli.docker_utils import (
    check_docker_available,
    container_exists,
    container_is_running,
    ensure_image,
    resolve_data_dir,
)
from codefreedom.cli.tool_init_utils import (
    _print_tool_notice,
)
from pydantic import ValidationError

from codefreedom.schemas.web_bridge import WebBridgeConfig

# ── Defaults ──────────────────────────────────────────────────────────────────

_DEFAULT_IMAGE = "docker.io/nilayparikh/codefreedom:web-bridge"
_DEFAULT_CONTAINER_NAME = "codefreedom-web-bridge"
_DEFAULT_PORT = 8500


def _tool_home() -> Path:
    """Return the tool home directory.

    Defaults to ``~/.codefreedom``, overridable via ``CODEFREEDOM_TOOL_HOME``
    env var (used by tests for isolation).
    """
    override = os.environ.get("CODEFREEDOM_TOOL_HOME")
    if override:
        return Path(override)
    return Path.home() / ".codefreedom"


def _default_data_dir() -> str:
    """Return the default data dir under ~/.codefreedom/sandbox/tools/web-bridge."""
    return str(_tool_home() / "sandbox" / "tools" / "web-bridge")


def _profile_path() -> Path:
    """Return the web-bridge tool profile path (~/.codefreedom/profiles/web-bridge.yaml)."""
    return _tool_home() / "profiles" / "web-bridge.yaml"


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
        "data_dir": _default_data_dir(),
        "env": {},
    }

    profile_path = _profile_path()
    if not profile_path.exists():
        return settings

    try:
        with open(profile_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except (yaml.YAMLError, OSError) as exc:
        eprint(f"[WEB-BRIDGE] Warning: failed to read {profile_path}: {exc}")
        return settings

    if not isinstance(raw, dict):
        eprint(f"[WEB-BRIDGE] Warning: invalid profile format in {profile_path}")
        return settings

    # Interpolate ${VAR} references in env values
    interpolate_all_strings(raw)

    # Validate with Pydantic (non-fatal — warn on failure)
    try:
        WebBridgeConfig.model_validate(raw, strict=False)
    except ValidationError as exc:
        eprint(f"[WEB-BRIDGE] Warning: validation issue in profile: {exc}")

    cfg = raw.get("web_bridge", {})
    if not isinstance(cfg, dict):
        return settings

    if isinstance(cfg.get("image"), str) and cfg["image"]:
        settings["image"] = cfg["image"]
    if isinstance(cfg.get("container_name"), str) and cfg["container_name"]:
        settings["container_name"] = cfg["container_name"]
    if isinstance(cfg.get("port"), int) and cfg["port"] > 0:
        settings["port"] = cfg["port"]
    # Machine env var override (checked at profile load time)
    env_port = os.environ.get("CODEFREEDOM_WEB_BRIDGE_PORT")
    if env_port is not None:
        try:
            settings["port"] = int(env_port)
        except (ValueError, TypeError):
            pass
    if isinstance(cfg.get("data_dir"), str) and cfg["data_dir"]:
        settings["data_dir"] = cfg["data_dir"]
    if isinstance(cfg.get("env"), dict):
        settings["env"] = cfg["env"]

    return settings


# ── Init ──────────────────────────────────────────────────────────────────────


def init_tool() -> int:
    """Initialize the web-bridge tool profile via recipes.

    Tools are auto-initialized when ``cf init recipe`` copies the profile
    to ``~/.codefreedom/profiles/web-bridge.yaml``.
    """
    profile_path = _profile_path()
    if profile_path.exists():
        eprint(
            "[web-bridge] Profile already exists at ~/.codefreedom/profiles/web-bridge.yaml"
        )
        return 0
    eprint(
        "[web-bridge] No profile found. Run 'cf init recipe' to install the default recipe."
    )
    from codefreedom.cli.tool_init_utils import print_help_section

    print_help_section(
        "web-bridge init",
        [
            "Use:  cf init recipe              # install _default base recipe",
            "      cf init recipe --list        # list available recipes",
            "      cf init recipe --plan <name> # preview a recipe without applying",
            "      cf init recipe <name>        # install a specific recipe",
        ],
        docs_url="https://nilayparikh.github.io/codefreedom/recipes/",
        include_disclaimer=True,
    )
    return 0


# ── Actions ───────────────────────────────────────────────────────────────────


def start(settings: dict) -> int:
    """Start the web-bridge container. Returns exit code."""
    profile_path = _profile_path()
    if not profile_path.exists():
        eprint("[web-bridge] Tool profile not found.")
        eprint("         Run:  cf init recipe")
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

    if not check_docker_available():
        eprint("[ERROR] Docker not found. Install Docker and try again.")
        return 1

    resolved_data = resolve_data_dir(data_dir)
    eprint(f"[WEB-BRIDGE] Using data dir: {resolved_data}")

    if container_exists(container_name):
        eprint(f"[WEB-BRIDGE] Removing existing container '{container_name}'...")
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            timeout=15,
            check=False,
        )

    if not ensure_image(
        image,
        label="WEB-BRIDGE",
        build_tip="docker build -t codefreedom:web-bridge -f docker/web-bridge/Dockerfile.Bridge docker/web-bridge/",
        profile_path="~/.codefreedom/profiles/web-bridge.yaml",
    ):
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
    container_name = settings["container_name"]

    if not container_exists(container_name):
        eprint(f"[WEB-BRIDGE] No container '{container_name}' found.")
        return 0

    if not container_is_running(container_name):
        eprint(f"[WEB-BRIDGE] Container '{container_name}' exists but is not running.")
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            timeout=15,
            check=False,
        )
        return 0

    eprint(f"[WEB-BRIDGE] Stopping container '{container_name}'...")
    result = subprocess.run(
        ["docker", "stop", "-t", "5", container_name],
        capture_output=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        eprint(f"[ERROR] Failed to stop container: {result.stderr.strip()}")
        return 1

    eprint(f"[WEB-BRIDGE] Removing container '{container_name}'...")
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        capture_output=True,
        timeout=15,
        check=False,
    )
    eprint("[WEB-BRIDGE] Container stopped and removed.")
    return 0


def restart(settings: dict) -> int:
    """Restart the web-bridge container. Returns exit code."""
    container_name = settings["container_name"]

    if not container_exists(container_name):
        eprint(f"[WEB-BRIDGE] Container '{container_name}' does not exist.")
        eprint("         Use: cf tools start")
        return 1

    eprint(f"[WEB-BRIDGE] Restarting container '{container_name}'...")
    result = subprocess.run(
        ["docker", "restart", container_name],
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        eprint(f"[ERROR] Failed to restart container: {result.stderr.strip()}")
        return 1

    eprint("[WEB-BRIDGE] Container restarted.")
    return 0


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
    eprint("   Use: cf tools start")
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
        eprint(f"[ERROR] Unknown action: {action}")
        eprint("   Valid actions: start, stop, restart, status")
        return 1
