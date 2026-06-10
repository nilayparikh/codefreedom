"""Shared Docker utilities for tool modules (chrome, web, etc.).

Extracts container lifecycle helpers that were duplicated across
tool modules so bug fixes and improvements only need to be made once.
"""

from __future__ import annotations

import os
import random
import socket
import string
import subprocess
from pathlib import Path
from typing import Any

import yaml

from pydantic import BaseModel

from codefreedom.env_loader import eprint
from codefreedom.interpolate import interpolate_all_strings


def resolve_data_dir(data_dir: str) -> Path:
    """Resolve data_dir, respecting ``CODEFREEDOM_HOME`` if set.

    When ``CODEFREEDOM_HOME`` points to a custom location (not
    ``~/.codefreedom``), any ``~/.codefreedom/...`` prefix in *data_dir*
    is transparently rewritten so tool data always lands inside the
    correct CodeFreedom home.

    Falls back to ``Path.expanduser()`` if ``CODEFREEDOM_HOME`` is not
    set or if the path doesn't start with ``~/.codefreedom``.
    """
    from codefreedom.config import get_codefreedom_dir

    cf_dir = get_codefreedom_dir()
    default_cf = Path.home() / ".codefreedom"

    if cf_dir != default_cf and "~/.codefreedom" in data_dir:
        path = Path(data_dir.replace("~/.codefreedom", str(cf_dir)))
    else:
        path = Path(data_dir).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def container_exists(name: str) -> bool:
    """Check if a container exists (running or stopped)."""
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"name={name}",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return name in result.stdout.strip().split("\n")
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def container_is_running(name: str) -> bool:
    """Check if a container is currently running."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={name}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return name in result.stdout.strip().split("\n")
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def check_docker_available() -> bool:
    """Return True if Docker CLI is available (installed and in PATH)."""
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def ensure_image(
    image: str,
    label: str = "TOOL",
    *,
    build_tip: str = "",
    profile_path: str = "~/.codefreedom/profiles/<tool>.json",
) -> bool:
    """Ensure the Docker image is available locally; pull if missing.

    Args:
        image: Docker image reference (e.g. 'codefreedom:chrome').
        label: Log prefix label (e.g. 'CHROME', 'WEB').
        build_tip: Tool-specific Docker build command hint.
        profile_path: Path to the profile file for the 'set image' tip.

    Returns:
        True if the image is available (cached or pulled successfully).
    """
    _inspect = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if _inspect.returncode == 0:
        print(f"[{label}] Using cached image '{image}'", flush=True)
        return True

    print(f"[{label}] Image '{image}' not found locally, pulling...", flush=True)
    pull = subprocess.run(
        ["docker", "pull", image],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if pull.returncode == 0:
        print("   [OK] Image pulled.", flush=True)
        return True

    import sys

    print(f"[ERROR] Failed to pull image '{image}'.", file=sys.stderr)
    if pull.stderr:
        print(f"   {pull.stderr.strip()}", file=sys.stderr)
    print("", file=sys.stderr)
    print("  Tips:", file=sys.stderr)
    if build_tip:
        print(f"    * Build locally:  {build_tip}", file=sys.stderr)
    print(
        f"    * Set 'image' in {profile_path} to your local tag",
        file=sys.stderr,
    )
    print("    * Wait for CI to publish the image to ghcr.io", file=sys.stderr)
    return False


def generate_container_name(base_name: str) -> str:
    """Append a 4-character random lowercase alphanumeric suffix to *base_name*.

    Prevents container name collisions when multiple CodeFreedom profiles
    run the same tool (e.g. chrome, web, github) simultaneously.

    Example: ``codefreedom-chrome`` → ``codefreedom-chrome-a1b2``
    """
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{base_name}-{suffix}"


def find_containers_by_base(base_name: str) -> list[str]:
    """Find running or stopped Docker containers whose name starts with *base_name*.

    Uses ``docker ps -a --filter name=<base_name>`` with a regex anchor so
    ``codefreedom-chrome`` matches ``codefreedom-chrome-A1B2`` but not
    ``codefreedom-chrome-extra``.

    Returns a list of matching container names (newest first).
    """
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"name={base_name}",
                "--format",
                "{{.Names}}\t{{.CreatedAt}}",
                "--latest",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if not result.stdout.strip():
            return []
        lines = result.stdout.strip().split("\n")
        # Filter: only names that start with base_name followed by '-'
        matched = [
            line.split("\t")[0]
            for line in lines
            if line.split("\t")[0].startswith(f"{base_name}-")
        ]
        # Sort by creation time descending (newest first)
        matched.sort(key=_container_created_at, reverse=True)
        return matched
    except (subprocess.SubprocessError, FileNotFoundError):
        return []


def _container_created_at(name: str) -> str:
    """Return the created-at timestamp for a container (for sorting)."""
    try:
        r = subprocess.run(
            ["docker", "inspect", "--format", "{{.Created}}", name],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except (subprocess.SubprocessError, FileNotFoundError):
        return ""


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a TCP port is available for binding on *host*.

    Returns True if the port is free, False if something is already listening.
    """
    try:
        with socket.create_connection((host, port), timeout=2):
            return False
    except (OSError, socket.timeout):
        return True


# ── CodeFreedom container name patterns for port discovery ──────────────────

_CODEFREEDOM_CONTAINER_PATTERNS: list[str] = [
    "litellm-codefreedom",
    "codefreedom-web-bridge",
    "codefreedom-chrome",
    "codefreedom-web",
    "codefreedom-tools-github",
    "codefreedom-",
]


def get_codefreedom_container_ports() -> set[int]:
    """Return host TCP ports bound by running CodeFreedom Docker containers.

    Queries Docker for all running containers whose names match known
    CodeFreedom patterns (proxy, chrome, web, github, sandbox) and
    extracts their host port mappings.  This covers containers started
    via ``cf proxy start``, ``cf tools <name> start``, and session-
    managed tools from ``acquire_tools``.

    For ``--network host`` containers (chrome), the exposed container
    ports are directly on the host — we record them from the image's
    ``EXPOSE`` declarations.
    """
    ports: set[int] = set()

    try:
        # Get all running containers matching any known pattern
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return ports

        container_names = result.stdout.strip().split("\n")
    except (subprocess.SubprocessError, FileNotFoundError):
        return ports

    for name in container_names:
        name = name.strip()
        if not name:
            continue

        # Check if this container matches any known CodeFreedom pattern
        is_cf = any(name.startswith(p) for p in _CODEFREEDOM_CONTAINER_PATTERNS)
        if not is_cf:
            continue

        # Inspect port bindings, exposed ports, and network mode
        try:
            inspect = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{json .NetworkSettings.Ports}}|{{json .Config.ExposedPorts}}|{{.HostConfig.NetworkMode}}",
                    name,
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if inspect.returncode != 0 or not inspect.stdout.strip():
                continue

            raw = inspect.stdout.strip()
            parts = raw.rsplit("|", 2)
            network_ports_json = parts[0] if len(parts) >= 1 else ""
            exposed_ports_json = parts[1] if len(parts) >= 2 else ""
            network_mode = parts[2] if len(parts) >= 3 else ""

            import json as _json

            if network_mode == "host":
                # Host-network container: ports are directly on host.
                # Read exposed ports from Config.ExposedPorts.
                try:
                    exposed = _json.loads(exposed_ports_json) if exposed_ports_json else {}
                except _json.JSONDecodeError:
                    exposed = {}
                for key in exposed:
                    if "/tcp" in key:
                        try:
                            p = int(key.split("/")[0])
                            ports.add(p)
                        except (ValueError, IndexError):
                            pass
            else:
                # Bridged container: extract host-side port from NetworkSettings.Ports.
                try:
                    pmap = _json.loads(network_ports_json) if network_ports_json else {}
                except _json.JSONDecodeError:
                    pmap = {}
                for binds in pmap.values():
                    if isinstance(binds, list):
                        for b in binds:
                            hp = b.get("HostPort", "")
                            if hp.isdigit():
                                ports.add(int(hp))
        except (subprocess.SubprocessError, FileNotFoundError):
            continue

    return ports


# ── Shared tool helpers ─────────────────────────────────────────────────────

# Tool profile files always go to ~/.codefreedom/ (shared across projects).
_TOOL_PROFILE_PATHS: set[str] = {
    "profiles/chrome.yaml",
    "profiles/web.yaml",
    "profiles/github.yaml",
    "profiles/web-bridge.yaml",
}


def tool_home() -> Path:
    """Return the tool home directory.

    Defaults to ``~/.codefreedom``, overridable via ``CODEFREEDOM_TOOL_HOME``
    env var (used by tests for isolation).
    """
    override = os.environ.get("CODEFREEDOM_TOOL_HOME")
    if override:
        return Path(override)
    return Path.home() / ".codefreedom"


def tool_data_dir(tool_name: str) -> str:
    """Return the default data dir under ~/.codefreedom/sandbox/tools/<name>."""
    return str(tool_home() / "sandbox" / "tools" / tool_name)


def tool_profile_path(tool_filename: str) -> Path:
    """Return the tool profile path (~/.codefreedom/profiles/<filename>)."""
    return tool_home() / "profiles" / tool_filename


def init_tool_redirect(tool_filename: str) -> int:
    """Redirect tool init to the recipe system.

    Standard init handler for all tools — points users to ``cf init recipe``.
    """
    profile_path = tool_home() / "profiles" / tool_filename
    if profile_path.exists():
        tool_label = tool_filename.replace(".yaml", "")
        eprint(f"[{tool_label}] Profile already exists at ~/.codefreedom/profiles/{tool_filename}")
        return 0
    eprint(
        f"[{tool_filename.replace('.yaml', '')}] No profile found."
        " Run 'cf init recipe' to install the default recipe."
    )
    from codefreedom.cli.tool_init_utils import print_help_section

    label = tool_filename.replace(".yaml", "")
    print_help_section(
        f"{label} init",
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


def load_tool_profile(
    tool_key: str,
    defaults: dict[str, Any],
    profile_filename: str,
    schema_class: type[BaseModel] | None = None,
    env_port_var: str | None = None,
    extra_keys: list[str] | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    """Load a tool profile from ~/.codefreedom/profiles/<filename>.

    Shared loader used by all tool modules.  Handles YAML reading,
    ``${VAR}`` interpolation, Pydantic validation (non-fatal), and
    merging of profile values over hardcoded defaults.

    Args:
        tool_key: Key in the YAML dict for this tool (e.g. ``"chrome"``).
        defaults: Dict of hardcoded defaults (mutated in place).
        profile_filename: Profile filename (e.g. ``"chrome.yaml"``).
        schema_class: Optional Pydantic model for validation (non-fatal).
        env_port_var: Env var name for port override (e.g. ``"CODEFREEDOM_CHROME_PORT"``).
        extra_keys: Extra dict-key names to transfer from profile to settings.
        label: Log prefix label (defaults to *tool_key* upper).

    Returns *defaults* (the same dict, mutated).
    """
    from pydantic import ValidationError

    tag = (label or tool_key).upper()
    profile_path = tool_home() / "profiles" / profile_filename

    if not profile_path.exists():
        return defaults

    try:
        with open(profile_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except (yaml.YAMLError, OSError) as exc:
        eprint(f"[{tag}] Warning: failed to read {profile_path}: {exc}")
        return defaults

    if not isinstance(raw, dict):
        eprint(f"[{tag}] Warning: invalid profile format in {profile_path}")
        return defaults

    # Interpolate ${VAR} references in env values
    interpolate_all_strings(raw)

    # Validate with Pydantic (non-fatal — warn on failure)
    if schema_class is not None:
        try:
            schema_class.model_validate(raw, strict=False)
        except ValidationError as exc:
            eprint(f"[{tag}] Warning: validation issue in profile: {exc}")

    cfg = raw.get(tool_key, {})
    if not isinstance(cfg, dict):
        return defaults

    # Standard keys
    for key in ("image", "container_name", "data_dir"):
        if isinstance(cfg.get(key), str) and cfg[key]:
            defaults[key] = cfg[key]
    if isinstance(cfg.get("port"), int) and cfg["port"] > 0:
        defaults["port"] = cfg["port"]
    # Machine env var override for port
    if env_port_var:
        env_port = os.environ.get(env_port_var)
        if env_port is not None:
            try:
                defaults["port"] = int(env_port)
            except (ValueError, TypeError):
                pass
    if isinstance(cfg.get("env"), dict):
        defaults["env"] = cfg["env"]

    # Extra keys specific to the tool
    for key in (extra_keys or []):
        val = cfg.get(key)
        if key == "port":
            continue  # handled above
        if key == "mcp_path":
            if isinstance(val, str) and val:
                defaults[key] = val
        elif key == "mcp_port":
            if isinstance(val, int) and val > 0:
                defaults[key] = val
        elif key == "cdp_proxy_port":
            if isinstance(val, int) and val > 0:
                defaults[key] = val
        elif key == "search_engines":
            if isinstance(val, dict):
                defaults[key] = val
        elif key == "parser_registry":
            if isinstance(val, dict):
                defaults[key] = val
        elif key == "search_cooldown_seconds":
            if isinstance(val, (int, float)) and val >= 0:
                defaults[key] = float(val)
        elif isinstance(val, (str, int, float)) and val:
            defaults[key] = val

    return defaults


def stop_tool_container(settings: dict, label: str) -> int:
    """Stop and remove a tool container.  Shared implementation.

    Matches the web_bridge variant which handles both ``running`` and
    ``exists-but-stopped`` states — the other tools had a bug where a
    manually-stopped container would be left behind.
    """
    container_name = settings["container_name"]

    if not container_exists(container_name):
        eprint(f"[{label}] No container '{container_name}' found.")
        return 0

    if not container_is_running(container_name):
        eprint(f"[{label}] Container '{container_name}' exists but is not running.")
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            timeout=15,
            check=False,
        )
        return 0

    eprint(f"[{label}] Stopping container '{container_name}'...")
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
    eprint(f"[{label}] Container stopped and removed.")
    return 0


def restart_tool_container(settings: dict, label: str) -> int:
    """Restart a tool container using ``docker restart``.

    Preserves the container ID, logs, and network namespace. Does NOT pull
    a new image — to pick up a new image tag, use ``stop`` then ``start``.

    Returns exit code: 0 on success, 1 if container does not exist or
    docker restart fails.
    """
    container_name = settings["container_name"]

    if not container_exists(container_name):
        eprint(f"[{label}] Container '{container_name}' does not exist.")
        eprint("   Use: cf tools start")
        return 1

    eprint(f"[{label}] Restarting container '{container_name}'...")
    result = subprocess.run(
        ["docker", "restart", container_name],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        eprint(f"[ERROR] Failed to restart {label} container.")
        if result.stderr:
            eprint(f"   {result.stderr.strip()}")
        return 1

    eprint(f"[{label}] Container restarted.")
    return 0


def status_tool_container(settings: dict, label: str, extra_info: str = "") -> int:
    """Show container status. Returns 0 if running, 1 otherwise."""
    container_name = settings["container_name"]
    port = settings.get("port", "?")

    if container_is_running(container_name):
        eprint(f"[{label}] Container '{container_name}' is running.")
        eprint(f"[{label}] Port: {port}")
        if extra_info:
            eprint(extra_info)
        return 0

    if container_exists(container_name):
        eprint(f"[{label}] Container '{container_name}' exists but is not running.")
        return 1

    eprint(f"[{label}] No {label} container found.")
    eprint("   Use: cf tools start")
    return 1


def start_tool_init_gate(profile_filename: str, label: str) -> bool:
    """Check that the tool profile exists.  Prints help if missing.

    Returns True if profile exists, False otherwise.
    """
    profile_path = tool_home() / "profiles" / profile_filename
    if profile_path.exists():
        return True

    eprint(f"[{label}] Tool profile not found.")
    eprint("      Run:  cf init recipe")
    return False


def start_tool_docker_guard(label: str) -> bool:
    """Check that Docker is available.  Prints help if missing.

    Returns True if Docker is ready, False otherwise.
    """
    if check_docker_available():
        return True
    eprint(f"[{label}] Docker not found. Install Docker and try again.")
    return False


def start_tool_remove_stopped(container_name: str, label: str) -> None:
    """Remove a stopped container if it exists, preparing for a fresh start."""
    if container_exists(container_name):
        eprint(f"[{label}] Removing existing container '{container_name}'...")
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            timeout=15,
            check=False,
        )


def start_tool_ensure_image(settings: dict, label: str) -> bool:
    """Ensure the Docker image is available; returns True on success."""
    return ensure_image(
        settings["image"],
        label=label,
        build_tip=f"docker build -t {settings['image']} -f docker/{label.lower()}/Dockerfile.{label.capitalize()} docker/{label.lower()}/",
        profile_path=f"~/.codefreedom/profiles/{label.lower().replace('-', '_')}.yaml",
    )
