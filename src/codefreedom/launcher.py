"""Claude Code launcher — agent-specific orchestration.

This module owns:
- Container naming (_generate_container_name)
- MCP config generation (_write_mcp_json)
- Claude binary lookup (find_claude_binary)
- Sandbox directory setup (ensure_codefreedom_dir)
- Local execution (run_local)
- Docker execution setup and delegation (run_docker)

Container lifecycle (create, exec, stop, cleanup) is delegated to
sandbox/launcher.py — the canonical owner of container operations.

Pre-configured images (docker.io/nilayparikh/codefreedom — also available on ghcr.io/nilayparikh/codefreedom as a mirror):
- CUDA (NVIDIA): cuda-latest, cuda-v0.1, cuda-v0.1.0
- ROCm (AMD): rocm-latest, rocm-v0.1, rocm-v0.1.0
- Ubuntu (General): latest, v0.1, v0.1.0

Each sandbox session gets a fresh container with a random name -- no more
container-locking from shared reuse."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Dict, List

from codefreedom.core.config import get_codefreedom_dir
from codefreedom.log import eprint, tag
from codefreedom.tools.registry import load_tool_mcp_endpoints
from codefreedom.sandbox.signals import forward_signal
from codefreedom.sandbox.terminal import terminal_size

# ── Constants ──────────────────────────────────────────────────────────────────

REGISTRY = os.environ.get("CLAUDE_CODE_REGISTRY", "docker.io/nilayparikh")
IMAGE_NAME = os.environ.get("CLAUDE_CODE_IMAGE_NAME", "codefreedom")
IMAGE_TAG = os.environ.get("CLAUDE_CODE_IMAGE_TAG", "latest")
TARGET_IMAGE = f"{REGISTRY}/{IMAGE_NAME}:{IMAGE_TAG}"

HOME_DIR = Path.home()
CODEFREEDOM_DIR = get_codefreedom_dir()

_CONTAINER_PREFIX = "codefreedom-"


def _generate_container_name() -> str:
    """Generate a random container name: codefreedom-XXXXXX (6 hex chars)."""
    suffix = secrets.token_hex(3)
    return f"{_CONTAINER_PREFIX}{suffix}"


def _write_mcp_json(workspace_dir: Path, acquired_tools: list[str]) -> None:
    """Write .mcp.json into the workspace so Claude Code connects to acquired tool
    containers via their HTTP MCP endpoints.
    """
    mcp_config = load_tool_mcp_endpoints(acquired_tools)
    auto_servers = mcp_config.get("mcpServers", {})
    if not auto_servers:
        eprint(f"{tag('MCP')} No MCP endpoints to register.")
        return

    mcp_path = workspace_dir / ".mcp.json"
    existing: dict = {}
    if mcp_path.exists():
        try:
            existing = json.loads(mcp_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            eprint(
                f"{tag('MCP')} Could not parse existing {mcp_path} — backing up and replacing."
            )
            backup = mcp_path.with_suffix(".mcp.json.bak")
            try:
                mcp_path.rename(backup)
            except OSError:
                pass

    existing.setdefault("mcpServers", {})
    existing["mcpServers"].update(auto_servers)
    mcp_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    eprint(
        f"{tag('MCP')} Wrote {len(auto_servers)} MCP server(s) to {mcp_path}: "
        + ", ".join(auto_servers.keys())
    )

    other = [s for s in existing["mcpServers"] if s not in auto_servers]
    if other:
        eprint(
            f"{tag('MCP')} Preserved {len(other)} existing MCP server(s): {', '.join(other)}"
        )


def find_claude_binary() -> str | None:
    """Locate the claude CLI binary."""
    return shutil.which("claude")


# ── Status / Stop Commands ─────────────────────────────────────────────────────


def status() -> int:
    """Show all codefreedom sandbox containers. Returns exit code."""
    from codefreedom.sandbox.launcher import sandbox_status

    return sandbox_status(_CONTAINER_PREFIX)


def stop() -> int:
    """Stop and remove all codefreedom sandbox containers. Returns exit code."""
    from codefreedom.sandbox.launcher import sandbox_stop

    return sandbox_stop(_CONTAINER_PREFIX)


# ── Sandbox Directory Setup ────────────────────────────────────────────────────


def ensure_codefreedom_dir(profile_name: str) -> tuple[Path, Path]:
    """Create ~/.codefreedom/sandbox/{profile}/.claude and a fresh .claude.json.

    Does NOT seed from the host's ~/.claude.json -- the sandbox starts clean so
    Claude Code inside the container populates it naturally with only the paths
    that exist in the container (/workspace).

    Also ensures the shared tools cache directory exists for all sandbox sessions.

    All directories are made world-writable (0o777) so the container user
    (codefreedom, uid 1000) can read/write regardless of host uid mismatch.

    Returns (claude_dir, claude_json_path) -- the .claude directory and the
    .claude.json file path inside the profile's sandbox directory.
    """
    profile_dir = CODEFREEDOM_DIR / "sandbox" / profile_name
    profile_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(profile_dir, 0o777)

    claude_dir = profile_dir / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(claude_dir, 0o777)
    eprint(f"{tag('SANDBOX')} Isolated .claude dir: {claude_dir}.")

    # ── Fresh .claude.json (never copy from host) ──────────────────────
    sandbox_json = profile_dir / ".claude.json"
    if not sandbox_json.exists():
        sandbox_json.write_text("{}")
        os.chmod(sandbox_json, 0o666)
        eprint(f"{tag('SANDBOX')} Created fresh .claude.json: {sandbox_json}.")
    else:
        os.chmod(sandbox_json, 0o666)
        eprint(f"{tag('SANDBOX')} Using existing .claude.json: {sandbox_json}.")

    # ── Shared tools cache (used by Chrome DevTools MCP, etc.) ─────
    tools_cache = CODEFREEDOM_DIR / "sandbox" / "tools" / ".cache"
    tools_cache.mkdir(parents=True, exist_ok=True)
    os.chmod(tools_cache, 0o777)

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

    eprint(f"{tag('LOCAL')} Running Claude Code natively...")

    env = {**os.environ}
    env.update(profile_env)

    # Local mode: no bypass by default — use --dangerously-skip-permissions
    # to opt in for CI/non-interactive environments.
    cmd = [claude_bin]
    if dangerously_skip:
        cmd.append("--dangerously-skip-permissions")
    cmd.extend(claude_args)

    try:
        proc = subprocess.Popen(cmd, env=env)
        signal.signal(signal.SIGINT, lambda s, f: forward_signal(proc, s, f))
        signal.signal(signal.SIGTERM, lambda s, f: forward_signal(proc, s, f))
        proc.wait()
        return proc.returncode
    except FileNotFoundError:
        eprint(f"{tag('ERROR')} Claude binary not found at {claude_bin}.")
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
    run_as_me: bool = False,
    container_name: str | None = None,
    acquired_tools: list[str] | None = None,
) -> int:
    """Run claude inside an ephemeral Docker container.

    Delegates container lifecycle to the shared sandbox launcher.
    """
    from codefreedom.sandbox.launcher import run_sandbox

    sandbox_images = sandbox_images or {}

    # ── Resolve image ──────────────────────────────────────────────────────────
    if gpu_type:
        image = (
            sandbox_images.get(gpu_type) or f"{REGISTRY}/{IMAGE_NAME}:{gpu_type}-latest"
        )
        eprint(f"{tag('GPU')} Selected '{gpu_type}' sandbox image: {image}.")
    else:
        image = sandbox_images.get("default") or TARGET_IMAGE

    if container_name is None:
        container_name = _generate_container_name()

    eprint(f"{tag('IMAGE')} Using sandbox image: {image}.")
    eprint(f"{tag('CONTAINER')} Name: {container_name}.")

    # ── Build env flags ───────────────────────────────────────────────────────
    env_flags: List[str] = []
    for key in sorted(profile_env.keys()):
        val = profile_env[key]
        if val is not None:
            env_flags.extend(["-e", f"{key}={val}"])

    cols, lines = terminal_size()
    env_flags.extend(["-e", f"COLUMNS={cols}", "-e", f"LINES={lines}"])

    # ── Sandbox directory setup ───────────────────────────────────────────────
    sandbox_claude_dir, sandbox_claude_json = ensure_codefreedom_dir(profile_name)

    # ── Container identity ────────────────────────────────────────────────────
    if run_as_me and hasattr(os, "getuid"):
        host_uid = os.getuid()
        host_gid = os.getgid()
        container_home = f"/home/{HOME_DIR.name}"
        container_user_flag = ["-u", f"{host_uid}:{host_gid}"]
        eprint(
            f"{tag('SANDBOX')} --run-as-me: uid={host_uid}({HOME_DIR.name}) gid={host_gid}"
        )
    else:
        if run_as_me:
            eprint(
                f"{tag('SANDBOX')} --run-as-me not supported on Windows; running as default user."
            )
        container_home = "/home/codefreedom"
        container_user_flag = []
        eprint(
            f"{tag('SANDBOX')} Running as default container user 'codefreedom' (uid 1000)."
        )
        eprint(
            f"{tag('SANDBOX')} If you see permission errors on /workspace, grant access with:"
        )
        eprint(f"           sudo chown -R 1000:1000 {workspace_dir}")
        eprint(
            "           Or re-run with --run-as-me to match your host user identity."
        )

    # ── Docker run base options ───────────────────────────────────────────────
    base_opts = [
        "--gpus",
        "all",
        "--network",
        "host",
        *container_user_flag,
        "--ipc=host",
        "-v",
        f"{workspace_dir}:/workspace",
        "-w",
        "/workspace",
        "-v",
        f"{HOME_DIR / '.gitconfig'}:{container_home}/.gitconfig:ro",
        "-v",
        f"{HOME_DIR / '.ssh'}:{container_home}/.ssh:ro",
        "-v",
        f"{sandbox_claude_dir}:{container_home}/.claude",
        "-v",
        f"{sandbox_claude_json}:{container_home}/.claude.json",
        "-e",
        f"HOME={container_home}",
        "-v",
        f"{workspace_dir / '.claude'}:/workspace/.claude",
        "-v",
        f"{CODEFREEDOM_DIR / 'sandbox' / 'tools' / '.cache'}:{container_home}/.cache",
    ]

    # ── MCP JSON for tools ────────────────────────────────────────────────────
    if acquired_tools:
        _write_mcp_json(workspace_dir, acquired_tools)
    (workspace_dir / ".claude").mkdir(parents=True, exist_ok=True)

    # ── Exec command ──────────────────────────────────────────────────────────
    exec_image_cmd = (
        ["docker", "exec", "-it"]
        + container_user_flag
        + ["-e", f"HOME={container_home}"]
        + [container_name, "claude", "--dangerously-skip-permissions"]
        + claude_args
    )

    return run_sandbox(
        image=image,
        container_name=container_name,
        base_opts=base_opts,
        env_flags=env_flags,
        exec_image_cmd=exec_image_cmd,
    )
