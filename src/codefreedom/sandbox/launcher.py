"""Shared sandbox launcher — CANONICAL OWNER of container lifecycle.

This module owns:
- Container creation and cleanup (run_sandbox)
- Container status queries (sandbox_status)
- Container stop operations (sandbox_stop)

launcher.py owns agent-specific orchestration (MCP config, sandbox dirs,
Claude binary lookup) and delegates container operations here.
"""

from __future__ import annotations

import signal
import subprocess
from typing import List

from codefreedom.log import eprint
from codefreedom.sandbox.signals import forward_signal


def run_sandbox(
    *,
    image: str,
    container_name: str,
    base_opts: List[str],
    env_flags: List[str],
    exec_image_cmd: List[str],
    exec_extra_env: List[str] | None = None,
) -> int:
    """Run an agent inside an ephemeral Docker container.

    Args:
        image: Docker image reference (e.g. ``docker.io/nilayparikh/codefreedom:claude-code-latest``)
        container_name: Unique name for the ephemeral container
        base_opts: List of docker run arguments (volumes, user, network, etc.)
        env_flags: List of -e KEY=VALUE pairs for the docker run and exec commands
        exec_image_cmd: Full command to run inside the container
            (e.g. ``["docker", "exec", "-it", ...]``)
        exec_extra_env: Additional -e KEY=VALUE pairs for the exec command only

    Returns:
        Exit code from the child process (0 on success, 130 on Ctrl+C)
    """
    # ── Ensure image is available ──────────────────────────────────────────────
    _inspect = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if _inspect.returncode != 0:
        eprint(f"[IMAGE] Pulling '{image}'...")
        pull = subprocess.run(
            ["docker", "pull", image],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if pull.returncode != 0:
            eprint(f"[ERROR] Failed to pull image '{image}'.")
            if pull.stderr:
                eprint(f"   {pull.stderr.strip()}")
            return 1
    else:
        eprint(f"[IMAGE] Using cached image '{image}'.")

    # ── Start ephemeral container ─────────────────────────────────────────────
    eprint(f"[RUN] Creating ephemeral container '{container_name}'...")
    create = subprocess.run(
        ["docker", "run", "-d", "--rm", "--name", container_name]
        + base_opts
        + env_flags
        + [image, "sleep", "infinity"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if create.returncode != 0:
        eprint("[ERROR] Failed to start container.")
        if create.stderr:
            eprint(f"   {create.stderr.strip()}")
        return 1
    eprint("[SANDBOX] Container started.")

    # ── Exec agent into the container ─────────────────────────────────────────
    eprint("[EXEC] Attaching agent session...")

    exec_cmd = list(exec_image_cmd)
    if exec_extra_env:
        exec_cmd = exec_cmd + exec_extra_env
    exec_cmd = exec_cmd + env_flags

    exit_code = 1
    proc: subprocess.Popen | None = None  # type: ignore[type-arg]
    try:
        proc = subprocess.Popen(exec_cmd)
        signal.signal(signal.SIGINT, lambda s, f: forward_signal(proc, s, f))  # type: ignore[arg-type]
        signal.signal(signal.SIGTERM, lambda s, f: forward_signal(proc, s, f))  # type: ignore[arg-type]
        if proc:
            proc.wait()
            exit_code = proc.returncode
    except KeyboardInterrupt:
        exit_code = 130
    finally:
        eprint(f"[CLEAN] Stopping container '{container_name}'...")
        subprocess.run(
            ["docker", "stop", container_name],
            capture_output=True,
            timeout=15,
            check=False,
        )
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            timeout=5,
            check=False,
        )
        eprint("[SANDBOX] Container cleaned up.")

    return exit_code


def sandbox_status(container_prefix: str) -> int:
    """Show all sandbox containers matching *container_prefix*. Returns exit code."""
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name={container_prefix}", "--format", "table {{.Names}}\t{{.Status}}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        output = result.stdout.strip()
        if not output:
            eprint(f"[SANDBOX] No containers found with prefix '{container_prefix}'.")
            return 0
        eprint(output)
        return 0
    except subprocess.SubprocessError as exc:
        eprint(f"[ERROR] Failed to list containers: {exc}")
        return 1


def sandbox_stop(container_prefix: str) -> int:
    """Stop and remove all sandbox containers matching *container_prefix*. Returns exit code."""
    try:
        find = subprocess.run(
            ["docker", "ps", "-a", "-q", "--filter", f"name={container_prefix}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        ids = [cid for cid in find.stdout.strip().split("\n") if cid]
        if not ids:
            eprint(f"[SANDBOX] No containers found with prefix '{container_prefix}'.")
            return 0

        for cid in ids:
            eprint(f"[SANDBOX] Stopping container {cid}...")
            subprocess.run(["docker", "stop", cid], check=False, timeout=15)
            subprocess.run(["docker", "rm", "-f", cid], check=False, timeout=5)

        eprint("[SANDBOX] Containers stopped.")
        return 0
    except subprocess.SubprocessError as exc:
        eprint(f"[ERROR] Failed to stop containers: {exc}")
        return 1
