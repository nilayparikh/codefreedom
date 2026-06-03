"""Sandbox launcher -- runs code agents in ephemeral Docker containers with GPU passthrough.

Pre-configured images (docker.io/nilayparikh/codefreedom — also available on ghcr.io/nilayparikh/codefreedom as a mirror):
- CUDA (NVIDIA): cuda-latest, cuda-v0.1, cuda-v0.1.0
- ROCm (AMD): rocm-latest, rocm-v0.1, rocm-v0.1.0
- Ubuntu (General): latest, v0.1, v0.1.0

Each sandbox session gets a fresh container with a random name -- no more
container-locking from shared reuse."""

from __future__ import annotations

import os
import secrets
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from codefreedom.env_loader import eprint

# ── Constants ──────────────────────────────────────────────────────────────────

REGISTRY = os.environ.get("CLAUDE_CODE_REGISTRY", "docker.io/nilayparikh")
IMAGE_NAME = os.environ.get("CLAUDE_CODE_IMAGE_NAME", "codefreedom")
IMAGE_TAG = os.environ.get("CLAUDE_CODE_IMAGE_TAG", "latest")
TARGET_IMAGE = f"{REGISTRY}/{IMAGE_NAME}:{IMAGE_TAG}"

HOME_DIR = Path.home()
CODEFREEDOM_DIR = HOME_DIR / ".codefreedom"

_CONTAINER_PREFIX = "codefreedom-"


def _generate_container_name() -> str:
    """Generate a random container name: codefreedom-XXXX (4 alphanumeric chars)."""
    suffix = secrets.token_hex(2)  # 4 hex chars
    return f"{_CONTAINER_PREFIX}{suffix}"


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
    """Show all codefreedom sandbox containers. Returns exit code."""
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"name={_CONTAINER_PREFIX}",
                "--format",
                "{{.Names}}\t{{.Status}}\t{{.CreatedAt}}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        containers = [l for l in result.stdout.strip().split("\n") if l]
        if containers:
            eprint(f"[STATUS] {len(containers)} codefreedom sandbox container(s):")
            for line in containers:
                name, status_line, _created = line.split("\t", 2)
                marker = "[RUNNING]" if "Up " in status_line else "[STOPPED]"
                eprint(f"   {marker} {name}  ({status_line})")
            eprint("\n   Stop all:  codefreedom claude --stop")
        else:
            eprint("[STATUS] No codefreedom sandbox containers found.")
        return 0
    except subprocess.TimeoutExpired:
        eprint("[STATUS] Docker command timed out. Is Docker running?")
        return 1
    except FileNotFoundError:
        eprint("[ERROR] Docker not found.")
        return 1


def stop() -> int:
    """Stop and remove all codefreedom sandbox containers. Returns exit code."""
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                f"name={_CONTAINER_PREFIX}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        ids = [c for c in result.stdout.strip().split("\n") if c]
        if not ids:
            eprint("[CLEAN] No codefreedom sandbox containers to remove.")
            return 0

        eprint(f"[CLEAN] Stopping {len(ids)} container(s)...")
        subprocess.run(
            ["docker", "stop"] + ids,
            capture_output=True,
            timeout=30,
            check=False,
        )
        subprocess.run(
            ["docker", "rm", "-f"] + ids,
            capture_output=True,
            timeout=30,
            check=False,
        )
        eprint("   [OK] All sandbox containers removed.")
        return 0
    except subprocess.TimeoutExpired:
        eprint("[ERROR] Docker command timed out.")
        return 1
    except FileNotFoundError:
        eprint("[ERROR] Docker not found.")
        return 1


# ── Sandbox Directory Setup ────────────────────────────────────────────────────


def ensure_codefreedom_dir(profile_name: str) -> tuple[Path, Path]:
    """Create ~/.codefreedom/sandbox/{profile}/.claude and a fresh .claude.json.

    Does NOT seed from the host's ~/.claude.json -- the sandbox starts clean so
    Claude Code inside the container populates it naturally with only the paths
    that exist in the container (/workspace).

    Also ensures the shared tools cache directory exists for all sandbox sessions.

    Returns (claude_dir, claude_json_path) -- the .claude directory and the
    .claude.json file path inside the profile's sandbox directory.
    """
    profile_dir = CODEFREEDOM_DIR / "sandbox" / profile_name
    profile_dir.mkdir(parents=True, exist_ok=True)

    claude_dir = profile_dir / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    eprint(f"[SANDBOX] Isolated .claude dir: {claude_dir}")

    # ── Fresh .claude.json (never copy from host) ──────────────────────
    sandbox_json = profile_dir / ".claude.json"
    if not sandbox_json.exists():
        sandbox_json.write_text("{}")
        eprint(f"[SANDBOX] Created fresh .claude.json: {sandbox_json}")
    else:
        eprint(f"[SANDBOX] Using existing .claude.json: {sandbox_json}")

    # ── Shared tools cache (used by Chrome DevTools MCP, etc.) ─────
    tools_cache = CODEFREEDOM_DIR / "sandbox" / "tools" / ".cache"
    tools_cache.mkdir(parents=True, exist_ok=True)

    return claude_dir, sandbox_json


# ── Execution ──────────────────────────────────────────────────────────────────


def run_local(
    profile_env: Dict[str, str],
    claude_args: List[str],
    dangerously_skip: bool = False,
) -> int:
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

    # Local mode: no bypass by default — use --dangerously-skip-permissions
    # to opt in for CI/non-interactive environments.
    cmd = [claude_bin]
    if dangerously_skip:
        cmd.append("--dangerously-skip-permissions")
    cmd.extend(claude_args)

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
    profile_name: str,
    gpu_type: str | None = None,
    sandbox_images: Dict[str, str] | None = None,
) -> int:
    """Run claude inside an ephemeral Docker container. Each session gets a fresh
    container with a random name -- cleaned up on exit (including Ctrl+C).

    If *gpu_type* is set (\"cuda\" or \"rocm\"), *sandbox_images* is consulted
    for a matching image reference, falling back to the standard tag naming
    convention (``docker.io/nilayparikh/codefreedom:{gpu_type}-latest``).
    Otherwise ``sandbox_images[\"default\"]`` (or ``TARGET_IMAGE``) is used.
    """

    sandbox_images = sandbox_images or {}

    # ── Resolve image based on GPU type ────────────────────────────────────
    if gpu_type:
        # Check profile's sandbox_images mapping first
        if gpu_type in sandbox_images:
            image = sandbox_images[gpu_type]
        else:
            # Fall back to standard tag convention
            registry = REGISTRY
            name = IMAGE_NAME
            image = f"{registry}/{name}:{gpu_type}-latest"
        eprint(f"[GPU] Selected '{gpu_type}' sandbox image: {image}")
    else:
        image = sandbox_images.get("default") or TARGET_IMAGE

    container_name = _generate_container_name()

    eprint(f"[IMAGE] Using sandbox image: {image}")
    eprint(f"[CONTAINER] Name: {container_name}")

    env_flags: List[str] = []
    for key in sorted(profile_env.keys()):
        val = profile_env[key]
        if val:
            env_flags.extend(["-e", f"{key}={val}"])

    cols, lines = terminal_size()
    env_flags.extend(["-e", f"COLUMNS={cols}", "-e", f"LINES={lines}"])

    uid = os.getuid()
    gid = os.getgid()

    # ── Ensure isolated sandbox .claude dir exists for this profile ───────
    sandbox_claude_dir, sandbox_claude_json = ensure_codefreedom_dir(profile_name)

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
        f"{sandbox_claude_dir}:/home/{HOME_DIR.name}/.claude",
        "-v",
        f"{sandbox_claude_json}:/home/{HOME_DIR.name}/.claude.json",
        "-e",
        f"HOME=/home/{HOME_DIR.name}",
        "-v",
        f"{workspace_dir / '.claude'}:/workspace/.claude",
        "-v",
        f"{CODEFREEDOM_DIR / 'sandbox' / 'tools' / '.cache'}:/home/{HOME_DIR.name}/.cache",
    ]

    # ── Ensure image is available ─────────────────────────────────────────
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
        eprint(f"[IMAGE] Using cached image '{image}'")

    # ── Ensure workspace .claude dir exists ───────────────────────────────
    (workspace_dir / ".claude").mkdir(parents=True, exist_ok=True)

    # ── Start ephemeral container ─────────────────────────────────────────
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
    eprint("   [OK] Container started.")

    # ── Exec claude into the container ────────────────────────────────────
    eprint("[EXEC] Attaching Claude Code session...")

    exec_cmd = (
        ["docker", "exec", "-it"]
        + ["-u", f"{uid}:{gid}", "-e", f"HOME=/home/{HOME_DIR.name}"]
        + env_flags
        + [container_name, "claude", "--dangerously-skip-permissions"]
        + claude_args
    )

    exit_code = 1
    try:
        proc = subprocess.Popen(exec_cmd)
        signal.signal(signal.SIGINT, lambda s, f: _forward_signal(proc, s, f))
        signal.signal(signal.SIGTERM, lambda s, f: _forward_signal(proc, s, f))
        proc.wait()
        exit_code = proc.returncode
    except KeyboardInterrupt:
        exit_code = 130
    finally:
        # ── Clean up the ephemeral container ──────────────────────────
        eprint(f"[CLEAN] Stopping container '{container_name}'...")
        subprocess.run(
            ["docker", "stop", container_name],
            capture_output=True,
            timeout=15,
            check=False,
        )
        # --rm flag handles auto-removal; force-remove as fallback
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            timeout=5,
            check=False,
        )
        eprint("   [OK] Container cleaned up.")

    return exit_code
