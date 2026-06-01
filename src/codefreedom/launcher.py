"""Claude Code Docker launcher — runs Claude Code in a persistent container.

Migrated from .init's claude-code.py. Provides the core execution engine
for launching Claude Code through Docker with profile-based model routing.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from codefreedom.env_loader import eprint

# ── Constants ──────────────────────────────────────────────────────────────────

CONTAINER_NAME = os.environ.get("CLAUDE_CODE_CONTAINER_NAME", "claude-dev-workspace")
REGISTRY = os.environ.get("CLAUDE_CODE_REGISTRY", "ghcr.io/nilayparikh")
IMAGE_NAME = os.environ.get("CLAUDE_CODE_IMAGE_NAME", "claude-code")
IMAGE_TAG = os.environ.get("CLAUDE_CODE_IMAGE_TAG", "latest")
TARGET_IMAGE = f"{REGISTRY}/{IMAGE_NAME}:{IMAGE_TAG}"

HOME_DIR = Path.home()


# ── Helpers ────────────────────────────────────────────────────────────────────


def find_claude_binary() -> Optional[str]:
    """Locate the claude CLI binary."""
    return shutil.which("claude")


def terminal_size() -> Tuple[str, str]:
    """Get terminal width and height as strings."""
    cols = os.environ.get("CLAUDE_CODE_COLUMNS")
    lines = os.environ.get("CLAUDE_CODE_LINES")
    try:
        result = subprocess.run(
            ["stty", "size"], capture_output=True, text=True, timeout=2, check=False
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split()
            if len(parts) == 2:
                if not lines:
                    lines = parts[0]
                if not cols:
                    cols = parts[1]
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return cols or "80", lines or "24"


def _forward_signal(
    proc: subprocess.Popen,  # type: ignore[type-arg]
    signum: int,
    _frame: object,
) -> None:
    """Forward a signal to the child process (docker exec)."""
    if proc and proc.poll() is None:
        proc.send_signal(signum)


# ── Status / Stop Commands ─────────────────────────────────────────────────────


def status() -> int:
    """Show persistent container status. Returns exit code."""
    try:
        running = subprocess.run(
            ["docker", "ps", "-q", "-f", f"name=^{CONTAINER_NAME}$"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        exists = subprocess.run(
            ["docker", "ps", "-aq", "-f", f"name=^{CONTAINER_NAME}$"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        if running.stdout.strip():
            info = subprocess.run(
                [
                    "docker",
                    "ps",
                    "--filter",
                    f"name=^{CONTAINER_NAME}$",
                    "--format",
                    "{{.Status}}",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            status_line = info.stdout.strip() if info.returncode == 0 else "running"

            sessions = subprocess.run(
                ["docker", "top", CONTAINER_NAME, "-eo", "comm"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            session_count = (
                sessions.stdout.count("claude") if sessions.returncode == 0 else "?"
            )

            eprint(f"[STATUS] Container '{CONTAINER_NAME}' is running.")
            eprint(f"   Status: {status_line}")
            eprint(f"   Active Claude sessions: {session_count}")
            eprint("\n   Attach a new session:  codefreedom claude")
            eprint("   Stop the container:    codefreedom claude --stop")
        elif exists.stdout.strip():
            eprint(f"[STATUS] Container '{CONTAINER_NAME}' exists but is stopped.")
            eprint("   Restart it:  codefreedom claude")
            eprint("   Remove it:   codefreedom claude --stop")
        else:
            eprint(f"[STATUS] No container named '{CONTAINER_NAME}'.")
            eprint("   Create one:  codefreedom claude")
        return 0
    except subprocess.TimeoutExpired:
        eprint("[STATUS] Docker command timed out. Is Docker running?")
        return 1
    except FileNotFoundError:
        eprint("[ERROR] Docker not found. Install Docker or use --local.")
        return 1


def stop() -> int:
    """Stop and remove the persistent container. Returns exit code."""
    try:
        running = subprocess.run(
            ["docker", "ps", "-q", "-f", f"name=^{CONTAINER_NAME}$"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if running.stdout.strip():
            eprint(f"[CLEAN] Stopping container '{CONTAINER_NAME}'...")
            subprocess.run(
                ["docker", "stop", CONTAINER_NAME],
                capture_output=True,
                timeout=30,
                check=False,
            )
            eprint("   [OK] Container stopped.")

        exists = subprocess.run(
            ["docker", "ps", "-aq", "-f", f"name=^{CONTAINER_NAME}$"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if exists.stdout.strip():
            eprint("[CLEAN] Removing container...")
            subprocess.run(
                ["docker", "rm", "-f", CONTAINER_NAME],
                capture_output=True,
                timeout=30,
                check=False,
            )
            eprint("   [OK] Container removed.")
        else:
            eprint("[CLEAN] No container to remove.")
        return 0
    except subprocess.TimeoutExpired:
        eprint("[ERROR] Docker command timed out.")
        return 1
    except FileNotFoundError:
        eprint("[ERROR] Docker not found.")
        return 1


# ── Execution ──────────────────────────────────────────────────────────────────


def run_local(profile_env: Dict[str, str], claude_args: List[str]) -> int:
    """Run claude natively on the host. Returns exit code."""
    claude_bin = find_claude_binary()
    if not claude_bin:
        eprint(
            "[ERROR] Claude CLI not found. "
            "Install: npm install -g @anthropic-ai/claude-code"
        )
        return 1

    eprint("[LOCAL] Running Claude Code natively...")

    env = {**os.environ}
    for key, val in profile_env.items():
        if val:
            env[key] = val

    cmd = [claude_bin, "--dangerously-skip-permissions"] + claude_args

    try:
        proc = subprocess.Popen(cmd, env=env)
        signal.signal(signal.SIGINT, lambda s, f: _forward_signal(proc, s, f))
        signal.signal(signal.SIGTERM, lambda s, f: _forward_signal(proc, s, f))
        proc.wait()
        return proc.returncode
    except FileNotFoundError:
        eprint(f"[ERROR] Claude binary not found at {claude_bin}")
        return 1
    except KeyboardInterrupt:
        return 130


def run_docker(
    profile_env: Dict[str, str],
    claude_args: List[str],
    workspace_dir: Path,
) -> int:
    """Run claude inside a persistent Docker container. Returns exit code."""
    # Build env flags
    env_flags: List[str] = []
    for key in sorted(profile_env.keys()):
        val = profile_env[key]
        if val:
            env_flags.extend(["-e", f"{key}={val}"])

    cols, lines = terminal_size()
    env_flags.extend(["-e", f"COLUMNS={cols}", "-e", f"LINES={lines}"])

    uid = os.getuid()
    gid = os.getgid()

    base_opts = [
        "--gpus",
        "all",
        "--network",
        "host",
        "-u",
        f"{uid}:{gid}",
        "--ipc=host",
        "-v",
        f"{workspace_dir}:/workspace",
        "-w",
        "/workspace",
        "-v",
        f"{HOME_DIR / '.gitconfig'}:/root/.gitconfig:ro",
        "-v",
        f"{HOME_DIR / '.ssh'}:/root/.ssh:ro",
        "-v",
        f"{HOME_DIR / '.claude'}:/home/claude",
        "-e",
        "HOME=/home/claude",
        "-v",
        f"{workspace_dir / '.claude'}:/workspace/.claude",
    ]

    # ── Step A: Ensure image is pulled ─────────────────────────────────────
    eprint(f"[IMAGE] Ensuring '{TARGET_IMAGE}' is available...")
    pull = subprocess.run(
        ["docker", "pull", TARGET_IMAGE],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if pull.returncode != 0:
        fallback = f"{REGISTRY}/{IMAGE_NAME}:latest"
        eprint(f"[IMAGE] Tag '{IMAGE_TAG}' not found. Falling back to '{fallback}'...")
        pull = subprocess.run(
            ["docker", "pull", fallback],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if pull.returncode != 0:
            eprint("[ERROR] Failed to pull image.")
            if pull.stderr:
                eprint(f"   {pull.stderr.strip()}")
            return 1

    # ── Step B: Ensure config dirs exist ───────────────────────────────────
    (HOME_DIR / ".claude").mkdir(parents=True, exist_ok=True)
    (workspace_dir / ".claude").mkdir(parents=True, exist_ok=True)

    # ── Step C: Start persistent container if not running ──────────────────
    running = subprocess.run(
        ["docker", "ps", "-q", "-f", f"name=^{CONTAINER_NAME}$"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    if not running.stdout.strip():
        stale = subprocess.run(
            ["docker", "ps", "-aq", "-f", f"name=^{CONTAINER_NAME}$"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if stale.stdout.strip():
            eprint(f"[CLEAN] Removing stale container '{CONTAINER_NAME}'...")
            subprocess.run(
                ["docker", "rm", "-f", CONTAINER_NAME],
                capture_output=True,
                timeout=30,
                check=False,
            )

        eprint(f"[RUN] Starting persistent container '{CONTAINER_NAME}'...")
        create = subprocess.run(
            ["docker", "run", "-d", "--name", CONTAINER_NAME]
            + base_opts
            + env_flags
            + [TARGET_IMAGE, "sleep", "infinity"],
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
        eprint("   [OK] Container started (background).")
    else:
        eprint(f"[RUN] Reusing running container '{CONTAINER_NAME}'.")

    # ── Step D: Exec claude into the container ─────────────────────────────
    eprint("[EXEC] Attaching Claude Code session...")

    exec_cmd = (
        ["docker", "exec", "-it"]
        + ["-u", f"{uid}:{gid}", "-e", "HOME=/home/claude"]
        + env_flags
        + [CONTAINER_NAME, "claude", "--dangerously-skip-permissions"]
        + claude_args
    )

    try:
        proc = subprocess.Popen(exec_cmd)
        signal.signal(signal.SIGINT, lambda s, f: _forward_signal(proc, s, f))
        signal.signal(signal.SIGTERM, lambda s, f: _forward_signal(proc, s, f))
        proc.wait()
        return proc.returncode
    except KeyboardInterrupt:
        return 130
