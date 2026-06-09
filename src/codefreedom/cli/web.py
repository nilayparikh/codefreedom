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

from codefreedom.schemas.web import WebConfig

# ── Defaults ─────────────────────────────────────────────────────────────

_DEFAULT_IMAGE = "docker.io/nilayparikh/codefreedom:web-latest"
_DEFAULT_CONTAINER_NAME = "codefreedom-web"
_DEFAULT_PORT = 8420
_DEFAULT_SEARCH_COOLDOWN_SECONDS = 10.0

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
    """Return the default data dir under ~/.codefreedom/sandbox/tools/web."""
    return str(_tool_home() / "sandbox" / "tools" / "web")


def _profile_path() -> Path:
    """Return the web tool profile path (~/.codefreedom/profiles/web.yaml)."""
    return _tool_home() / "profiles" / "web.yaml"


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
        "data_dir": _default_data_dir(),
        "env": {},
        "search_engines": {},
        "parser_registry": {},
        "search_cooldown_seconds": _DEFAULT_SEARCH_COOLDOWN_SECONDS,
    }

    profile_path = _profile_path()
    if not profile_path.exists():
        return settings

    try:
        with open(profile_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except (yaml.YAMLError, OSError) as exc:
        eprint(f"[WEB] Warning: failed to read {profile_path}: {exc}")
        return settings

    if not isinstance(raw, dict):
        eprint(f"[WEB] Warning: invalid profile format in {profile_path}")
        return settings

    # Interpolate ${VAR} references in env values
    interpolate_all_strings(raw)

    # Validate with Pydantic (non-fatal — warn on failure)
    try:
        WebConfig.model_validate(raw, strict=False)
    except ValidationError as exc:
        eprint(f"[WEB] Warning: validation issue in profile: {exc}")

    cfg = raw.get("web", {})
    if not isinstance(cfg, dict):
        return settings

    if isinstance(cfg.get("image"), str) and cfg["image"]:
        settings["image"] = cfg["image"]
    if isinstance(cfg.get("container_name"), str) and cfg["container_name"]:
        settings["container_name"] = cfg["container_name"]
    if isinstance(cfg.get("port"), int) and cfg["port"] > 0:
        settings["port"] = cfg["port"]
    # Machine env var override (checked at profile load time)
    env_port = os.environ.get("CODEFREEDOM_WEB_PORT")
    if env_port is not None:
        try:
            settings["port"] = int(env_port)
        except (ValueError, TypeError):
            pass
    if isinstance(cfg.get("mcp_path"), str) and cfg["mcp_path"]:
        settings["mcp_path"] = cfg["mcp_path"]
    if isinstance(cfg.get("data_dir"), str) and cfg["data_dir"]:
        settings["data_dir"] = cfg["data_dir"]
    if isinstance(cfg.get("env"), dict):
        settings["env"] = cfg["env"]
    if isinstance(cfg.get("search_engines"), dict):
        settings["search_engines"] = cfg["search_engines"]
    if isinstance(cfg.get("parser_registry"), dict):
        settings["parser_registry"] = cfg["parser_registry"]

    cooldown = cfg.get("search_cooldown_seconds")
    if isinstance(cooldown, (int, float)) and cooldown >= 0:
        settings["search_cooldown_seconds"] = float(cooldown)

    return settings


# ── Init ────────────────────────────────────────────────────────────────────


def init_tool() -> int:
    """Initialize the web tool profile via recipes.

    Tools are auto-initialized when ``cf init recipe`` copies the profile
    to ``~/.codefreedom/profiles/web.yaml``.
    """
    profile_path = _profile_path()
    if profile_path.exists():
        eprint("[web] Profile already exists at ~/.codefreedom/profiles/web.yaml")
        return 0
    eprint("[web] No profile found. Run 'cf init recipe' to install the default recipe.")
    from codefreedom.cli.tool_init_utils import print_help_section

    print_help_section(
        "web init",
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


# ── Actions ──────────────────────────────────────────────────────────────


def start(settings: dict) -> int:
    # ── Init gate: refuse to start if tool not initialized ───────────────
    profile_path = _profile_path()
    if not profile_path.exists():
        eprint("[web] Tool profile not found.")
        eprint("      Run:  cf init recipe")
        return 1

    # ── Third-party notice on every start ────────────────────────────────
    _print_tool_notice("web")

    image = settings["image"]
    container_name = settings["container_name"]
    port = settings["port"]
    data_dir = settings["data_dir"]

    if container_is_running(container_name):
        eprint(f"[WEB] Container '{container_name}' is already running.")
        return 0

    if not check_docker_available():
        eprint("[ERROR] Docker not found. Install Docker and try again.")
        return 1

    resolved_data = resolve_data_dir(data_dir)
    eprint(f"[WEB] Using data dir: {resolved_data}")

    if container_exists(container_name):
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            timeout=10,
            check=False,
        )

    if not ensure_image(
        image,
        label="WEB",
        build_tip="docker build -t codefreedom:web -f docker/web/Dockerfile.Web docker/web/",
        profile_path="~/.codefreedom/profiles/web.yaml",
    ):
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
    container_name = settings["container_name"]
    if not container_exists(container_name):
        eprint(f"[WEB] Container '{container_name}' not found.")
        return 0

    eprint(f"[WEB] Stopping container '{container_name}'...")
    subprocess.run(
        ["docker", "stop", container_name], capture_output=True, timeout=30, check=False
    )
    subprocess.run(
        ["docker", "rm", container_name], capture_output=True, timeout=10, check=False
    )
    eprint("[WEB] Container stopped.")
    return 0


def restart(settings: dict) -> int:
    """Restart the web container using `docker restart`.

    Preserves the container ID, logs, and network namespace. Does NOT pull
    a new image — to pick up a new image tag, use `stop` then `start`.

    Returns exit code: 0 on success, 1 if container does not exist or
    docker restart fails.
    """
    container_name = settings["container_name"]
    if not container_exists(container_name):
        eprint(f"[WEB] Container '{container_name}' not found.")
        eprint("   Use: cf tools start")
        return 1

    eprint(f"[WEB] Restarting container '{container_name}'...")
    result = subprocess.run(
        ["docker", "restart", container_name],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        eprint("[ERROR] Failed to restart web container.")
        if result.stderr:
            eprint(f"   {result.stderr.strip()}")
        return 1

    port = settings["port"]
    eprint("[WEB] Container restarted.")
    eprint(f"[WEB] MCP endpoint: http://127.0.0.1:{port}/mcp")
    return 0


def status(settings: dict) -> int:
    container_name = settings["container_name"]
    port = settings["port"]

    if container_is_running(container_name):
        eprint(f"[WEB] Container '{container_name}' is running.")
        eprint(f"[WEB] MCP endpoint: http://127.0.0.1:{port}/mcp")
        eprint("[WEB] Tools: web_search, web_fetch")
        return 0

    if container_exists(container_name):
        eprint(f"[WEB] Container '{container_name}' exists but is not running.")
        return 1

    eprint("[WEB] No web container found.")
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
