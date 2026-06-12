"""Shared signal forwarding for sandbox containers."""

from __future__ import annotations

import subprocess


def forward_signal(
    proc: subprocess.Popen,  # type: ignore[type-arg]
    signum: int,
    _frame: object,
) -> None:
    """Forward a signal to the child process (docker exec)."""
    if proc and proc.poll() is None:
        proc.send_signal(signum)
