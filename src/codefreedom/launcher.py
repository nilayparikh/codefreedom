"""Shared launcher utilities for CodeFreedom agents.

Provides MCP config writing, Claude MCP server registration, and native
host execution for Claude Code.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
from pathlib import Path

from codefreedom.core.config import get_codefreedom_dir
from codefreedom.core.remote_validation import RemoteValidationError, validate_remote_tools_or_raise
from codefreedom.log import eprint, tag
from codefreedom.tools.registry import load_tool_mcp_endpoints

REGISTRY = "docker.io/nilayparikh"
IMAGE_NAME = "codefreedom"
IMAGE_TAG = "latest"
TARGET_IMAGE = f"{REGISTRY}/{IMAGE_NAME}:{IMAGE_TAG}"
HOME_DIR = Path.home()
CODEFREEDOM_DIR = get_codefreedom_dir()


def _write_mcp_json(workspace_dir: Path, acquired_tools: list[str]) -> None:
    """Write ``.mcp.json`` into *workspace_dir* for non-Claude agents.

    Agents like MiMoCode, OpenCode, Pi Code, and Codex discover MCP tool
    endpoints from this file.  Existing non-tool entries are preserved.
    """
    mcp_path = workspace_dir / ".mcp.json"
    existing: dict = {}
    if mcp_path.exists():
        try:
            existing = json.loads(mcp_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}

    try:
        validate_remote_tools_or_raise(acquired_tools)
    except RemoteValidationError as exc:
        eprint(f"{tag('MCP')} {exc}")
        raise

    servers = load_tool_mcp_endpoints(acquired_tools)
    existing.setdefault("mcpServers", {})
    existing["mcpServers"].update(servers.get("mcpServers", {}))

    mcp_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    eprint(f"{tag('MCP')} Wrote {mcp_path}")


def find_claude_binary() -> str | None:
    """Locate the ``claude`` CLI binary on PATH."""
    return shutil.which("claude")


def run_local(
    profile_env: dict[str, str],
    agent_args: list[str],
    dangerously_skip: bool = False,
) -> int:
    """Run Claude Code natively on the host. Returns exit code."""

    def forward_signal(proc: subprocess.Popen, signum: int, _frame: object) -> None:
        if proc and proc.poll() is None:
            proc.send_signal(signum)

    claude_bin = find_claude_binary()
    if not claude_bin:
        eprint(
            "[ERROR] Claude Code (claude) not found on PATH.\n"
            "       Install: npm install -g @anthropic-ai/claude-code"
        )
        return 1

    eprint(f"{tag('LOCAL')} Running Claude Code natively...")

    env = {**os.environ}
    env.update(profile_env)

    cmd = [claude_bin]
    if dangerously_skip:
        cmd.append("--dangerously-skip-permissions")
    cmd.extend(agent_args)

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
