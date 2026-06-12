"""Shared terminal-size detection for sandbox launchers."""

from __future__ import annotations

import os
import subprocess
from typing import Tuple


def terminal_size() -> Tuple[str, str]:
    """Get terminal width and height as strings.

    Checks env vars CODEFREEDOM_COLUMNS/CODEFREEDOM_LINES, then agent-specific
    vars (CLAUDE_CODE_COLUMNS/CLAUDE_CODE_LINES and MIMO_CODE_COLUMNS/
    MIMO_CODE_LINES), then falls back to stty size, then to (80, 24).
    """
    cols = (
        os.environ.get("CODEFREEDOM_COLUMNS")
        or os.environ.get("CLAUDE_CODE_COLUMNS")
        or os.environ.get("MIMO_CODE_COLUMNS")
    )
    lines = (
        os.environ.get("CODEFREEDOM_LINES")
        or os.environ.get("CLAUDE_CODE_LINES")
        or os.environ.get("MIMO_CODE_LINES")
    )
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
