"""Shared logging utilities for CodeFreedom."""

import sys
from typing import Any


def eprint(*args: Any, **kwargs: Any) -> None:
    """Print to stderr (convenience wrapper)."""
    print(*args, file=sys.stderr, **kwargs)
