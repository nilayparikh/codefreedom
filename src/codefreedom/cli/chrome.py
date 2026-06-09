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

from codefreedom.schemas.chrome import ChromeConfig

# ── Defaults ──────────────────────────────────────────────────────────────────

_DEFAULT_IMAGE = "docker.io/nilayparikh/codefreedom:chrome-latest"
_DEFAULT_CONTAINER_NAME = "codefreedom-chrome"
_DEFAULT_PORT = 9222


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
    """Return the default data dir under ~/.codefreedom/sandbox/tools/chrome."""
    return str(_tool_home() / "sandbox" / "tools" / "chrome")


def _profile_path() -> Path:
    """Return the chrome tool profile path (~/.codefreedom/profiles/chrome.yaml)."""
    return _tool_home() / "profiles" / "chrome.yaml"


# ── Profile loader ────────────────────────────────────────────────────────────


def _load_profile() -> dict:
    """Load chrome tool profile from ~/.codefreedom/profiles/chrome.yaml.

    Returns a flat dict with keys: image, container_name, port, data_dir, env.
    Any missing key falls back to the hardcoded default above.
    """
    profile_path = _profile_path()
    settings: dict = {
        "image": _DEFAULT_IMAGE,
        "container_name": _DEFAULT_CONTAINER_NAME,
        "port": _DEFAULT_PORT,
        "mcp_port": 9223,
        "mcp_path": "/mcp",
        "data_dir": _default_data_dir(),
        "env": {},
    }

    if not profile_path.exists():
        return settings

    try:
        with open(profile_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except (yaml.YAMLError, OSError) as exc:
        eprint(f"[CHROME] Warning: failed to read {profile_path}: {exc}")
        return settings

    if not isinstance(raw, dict):
        eprint(f"[CHROME] Warning: invalid profile format in {profile_path}")
        return settings

    # Interpolate ${VAR} references in env values
    interpolate_all_strings(raw)

    # Validate with Pydantic (non-fatal — warn on failure)
    try:
        ChromeConfig.model_validate(raw, strict=False)
    except ValidationError as exc:
        eprint(f"[CHROME] Warning: validation issue in profile: {exc}")

    chrome_cfg = raw.get("chrome", {})
    if not isinstance(chrome_cfg, dict):
        return settings

    # Merge — profile values override defaults
    if isinstance(chrome_cfg.get("image"), str) and chrome_cfg["image"]:
        settings["image"] = chrome_cfg["image"]
    if (
        isinstance(chrome_cfg.get("container_name"), str)
        and chrome_cfg["container_name"]
    ):
        settings["container_name"] = chrome_cfg["container_name"]
    if isinstance(chrome_cfg.get("port"), int) and chrome_cfg["port"] > 0:
        settings["port"] = chrome_cfg["port"]
    # Machine env var override (checked at profile load time)
    env_port = os.environ.get("CODEFREEDOM_CHROME_PORT")
    if env_port is not None:
        try:
            settings["port"] = int(env_port)
        except (ValueError, TypeError):
            pass
    if isinstance(chrome_cfg.get("mcp_port"), int) and chrome_cfg["mcp_port"] > 0:
        settings["mcp_port"] = chrome_cfg["mcp_port"]
    if isinstance(chrome_cfg.get("mcp_path"), str) and chrome_cfg["mcp_path"]:
        settings["mcp_path"] = chrome_cfg["mcp_path"]
    if isinstance(chrome_cfg.get("data_dir"), str) and chrome_cfg["data_dir"]:
        settings["data_dir"] = chrome_cfg["data_dir"]
    if isinstance(chrome_cfg.get("env"), dict):
        settings["env"] = chrome_cfg["env"]

    return settings


# ── Init ────────────────────────────────────────────────────────────────────


def init_tool() -> int:
    """Initialize the chrome tool profile via recipes.

    Tools are auto-initialized when ``cf init recipe`` copies the profile
    to ``~/.codefreedom/profiles/chrome.yaml``.
    """
    profile_path = _profile_path()
    if profile_path.exists():
        eprint("[chrome] Profile already exists at ~/.codefreedom/profiles/chrome.yaml")
        return 0
    eprint(
        "[chrome] No profile found. Run 'cf init recipe' to install the default recipe."
    )
    from codefreedom.cli.tool_init_utils import print_help_section

    print_help_section(
        "chrome init",
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


# ── Actions ────────────────────────────────────────────────────────────────────


def start(settings: dict) -> int:
    """Start the Chrome browser container. Returns exit code."""
    # ── Init gate: refuse to start if tool not initialized ───────────────
    profile_path = _profile_path()
    if not profile_path.exists():
        eprint("[chrome] Tool profile not found.")
        eprint("         Run:  cf init recipe")
        return 1

    # ── Third-party notice on every start ────────────────────────────────
    _print_tool_notice("chrome")

    image = settings["image"]
    container_name = settings["container_name"]
    port = settings["port"]
    data_dir = settings["data_dir"]
    env_vars = settings.get("env", {})

    if container_is_running(container_name):
        eprint(f"[CHROME] Container '{container_name}' is already running.")
        return 0

    # Check if Docker is available
    if not check_docker_available():
        eprint("[ERROR] Docker not found. Install Docker and try again.")
        return 1

    # Resolve & create data directory
    resolved_data = resolve_data_dir(data_dir)
    eprint(f"[CHROME] Using data dir: {resolved_data}")

    # Remove existing container if stopped
    if container_exists(container_name):
        eprint(f"[CHROME] Removing existing container '{container_name}'...")
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            timeout=15,
            check=False,
        )

    # Ensure image is available
    if not ensure_image(
        image,
        label="CHROME",
        build_tip="docker build -t codefreedom:chrome -f docker/chrome/Dockerfile.Chrome docker/chrome/",
        profile_path="~/.codefreedom/profiles/chrome.yaml",
    ):
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

    # Start container — headless Chrome + MCP proxy.
    # --network host avoids NAT issues with CDP on arm64 Chromium builds.
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
            "--network",
            "host",
            "--shm-size=512m",
            "--restart",
            "unless-stopped",
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
    container_name = settings["container_name"]

    if not container_exists(container_name):
        eprint(f"[CHROME] Container '{container_name}' does not exist.")
        return 0

    eprint(f"[CHROME] Stopping container '{container_name}'...")
    subprocess.run(
        ["docker", "stop", container_name],
        capture_output=True,
        timeout=30,
        check=False,
    )
    subprocess.run(
        ["docker", "rm", container_name],
        capture_output=True,
        timeout=15,
        check=False,
    )
    eprint("   [OK] Container stopped and removed.")
    return 0


def restart(settings: dict) -> int:
    """Restart the Chrome container using `docker restart`.

    Preserves the container ID, logs, and network namespace. Does NOT pull
    a new image — to pick up a new image tag, use `stop` then `start`.

    Returns exit code: 0 on success, 1 if container does not exist or
    docker restart fails.
    """
    container_name = settings["container_name"]

    if not container_exists(container_name):
        eprint(f"[CHROME] Container '{container_name}' does not exist.")
        eprint("   Use: cf tools start")
        return 1

    eprint(f"[CHROME] Restarting container '{container_name}'...")
    result = subprocess.run(
        ["docker", "restart", container_name],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        eprint("[ERROR] Failed to restart Chrome container.")
        if result.stderr:
            eprint(f"   {result.stderr.strip()}")
        return 1

    port = settings["port"]
    eprint("   [OK] Container restarted.")
    eprint(f"   CDP debug URL: http://127.0.0.1:{port}")
    return 0


def status(settings: dict) -> int:
    """Show Chrome container status. Returns exit code.

    Pattern matches web.status() -- simple container_is_running / exists checks.
    """
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
