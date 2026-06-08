"""Shared Docker utilities for tool modules (chrome, web, etc.).

Extracts container lifecycle helpers that were duplicated across
tool modules so bug fixes and improvements only need to be made once.
"""

from __future__ import annotations

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
