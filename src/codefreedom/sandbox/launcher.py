"""Shared sandbox launcher — CANONICAL OWNER of container lifecycle.

This module owns:
- Container creation and cleanup (run_sandbox)
- Container status queries (sandbox_status)
- Container stop operations (sandbox_stop)
- Shared sandbox preparation (prepare_sandbox + SandboxPrep)

launcher.py owns agent-specific orchestration (MCP config, sandbox dirs,
Claude binary lookup) and delegates container operations here.
"""

from __future__ import annotations

import os
import secrets
import signal
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from codefreedom.docker.pull import pull_if_stale
from codefreedom.log import eprint, tag
from codefreedom.sandbox.signals import forward_signal
from codefreedom.sandbox.terminal import terminal_size

_DEFAULT_CONTAINER_HOME = "/home/codefreedom"


@dataclass
class SandboxPrep:
    """Resolved sandbox parameters shared by every agent's ``run_docker``.

    Built once by :func:`prepare_sandbox` from the common inputs and
    consumed by each agent to assemble its (agent-specific) volume mounts
    and exec command before calling :func:`run_sandbox`.
    """

    image: str
    container_name: str
    container_home: str
    container_user_flag: list[str]
    env_flags: list[str] = field(default_factory=list)


def prepare_sandbox(
    *,
    profile_env: dict[str, str],
    sandbox_images: dict[str, str],
    default_image: str,
    container_prefix: str,
    run_as_me: bool = False,
    gpu_type: str | None = None,
) -> SandboxPrep:
    """Resolve the sandbox inputs shared by every agent's ``run_docker``.

    Handles:
    1. Image selection (GPU-type override vs default)
    2. Ephemeral container-name generation
    3. ``-e KEY=VALUE`` env-flag list (profile env + terminal size)
    4. ``--run-as-me`` container identity (uid/gid + home) resolution

    Returns a :class:`SandboxPrep` the caller combines with its
    agent-specific config/volumes before calling :func:`run_sandbox`.
    """
    if gpu_type:
        image = (
            sandbox_images.get(gpu_type)
            or f"docker.io/nilayparikh/codefreedom:{gpu_type}-latest"
        )
        eprint(f"{tag('GPU')} Selected '{gpu_type}' sandbox image: {image}.")
    else:
        image = sandbox_images.get("default") or default_image

    container_name = f"{container_prefix}{secrets.token_hex(2)}"

    eprint(f"{tag('IMAGE')} Using sandbox image: {image}.")
    eprint(f"{tag('CONTAINER')} Name: {container_name}.")

    env_flags: list[str] = []
    for key in sorted(profile_env.keys()):
        val = profile_env[key]
        if val is not None:
            env_flags.extend(["-e", f"{key}={val}"])

    cols, lines = terminal_size()
    env_flags.extend(["-e", f"COLUMNS={cols}", "-e", f"LINES={lines}"])

    if run_as_me and hasattr(os, "getuid"):
        host_uid = os.getuid()
        host_gid = os.getgid()
        container_home = f"/home/{Path.home().name}"
        container_user_flag = ["-u", f"{host_uid}:{host_gid}"]
        eprint(
            f"{tag('SANDBOX')} --run-as-me: uid={host_uid}({Path.home().name}) gid={host_gid}"
        )
    else:
        if run_as_me:
            eprint(
                f"{tag('WARN')} --run-as-me not supported on Windows; running as default user."
            )
        container_home = _DEFAULT_CONTAINER_HOME
        container_user_flag = []
        eprint(
            f"{tag('SANDBOX')} Running as default container user 'codefreedom' (uid 1000)."
        )

    return SandboxPrep(
        image=image,
        container_name=container_name,
        container_home=container_home,
        container_user_flag=container_user_flag,
        env_flags=env_flags,
    )


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
        image: Docker image reference (e.g. ``docker.io/nilayparikh/codefreedom:ubuntu-latest``)
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
        eprint(f"{tag('IMAGE')} Pulling '{image}'...")
        pull = subprocess.run(
            ["docker", "pull", image],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if pull.returncode != 0:
            eprint(f"{tag('ERROR')} Failed to pull image '{image}'.")
            if pull.stderr:
                eprint(f"   {pull.stderr.strip()}")
            return 1
    else:
        pull_if_stale(image, label="IMAGE")

    # ── Start ephemeral container ─────────────────────────────────────────────
    eprint(f"{tag('RUN')} Creating ephemeral container '{container_name}'...")
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
        eprint(f"{tag('ERROR')} Failed to start container.")
        if create.stderr:
            eprint(f"   {create.stderr.strip()}")
        return 1
    eprint(f"{tag('SANDBOX')} Container started.")

    # ── Exec agent into the container ─────────────────────────────────────────
    eprint(f"{tag('EXEC')} Attaching agent session...")

    exec_cmd = list(exec_image_cmd)
    for flag_set in (exec_extra_env, env_flags):
        if flag_set:
            idx = exec_cmd.index(container_name)
            exec_cmd = exec_cmd[:idx] + flag_set + exec_cmd[idx:]

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
        eprint(f"{tag('CLEAN')} Stopping container '{container_name}'...")
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
        eprint(f"{tag('SANDBOX')} Container cleaned up.")

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
            eprint(f"{tag('SANDBOX')} No containers found with prefix '{container_prefix}'.")
            return 0
        eprint(output)
        return 0
    except subprocess.SubprocessError as exc:
        eprint(f"{tag('ERROR')} Failed to list containers: {exc}")
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
            eprint(f"{tag('SANDBOX')} No containers found with prefix '{container_prefix}'.")
            return 0

        for cid in ids:
            eprint(f"{tag('SANDBOX')} Stopping container {cid}...")
            subprocess.run(["docker", "stop", cid], check=False, timeout=15)
            subprocess.run(["docker", "rm", "-f", cid], check=False, timeout=5)

        eprint(f"{tag('SANDBOX')} Containers stopped.")
        return 0
    except subprocess.SubprocessError as exc:
        eprint(f"{tag('ERROR')} Failed to stop containers: {exc}")
        return 1
