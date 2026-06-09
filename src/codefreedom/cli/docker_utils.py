"""Shared Docker utilities for tool modules (chrome, web, etc.).

Extracts container lifecycle helpers that were duplicated across
tool modules so bug fixes and improvements only need to be made once.
"""

from __future__ import annotations

import random
import socket
import string
import subprocess
from pathlib import Path


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
