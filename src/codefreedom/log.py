"""Shared logging utilities for CodeFreedom."""

import sys


def eprint(*args, **kwargs) -> None:
    """Print to stderr (convenience wrapper)."""
    print(*args, file=sys.stderr, **kwargs)