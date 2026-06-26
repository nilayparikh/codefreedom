"""Shared logging utilities for CodeFreedom."""
from __future__ import annotations

import sys
from typing import Any


def eprint(*args: Any, **kwargs: Any) -> None:
    """Print to stderr (convenience wrapper)."""
    print(*args, file=sys.stderr, **kwargs)


# ── ANSI color helpers ───────────────────────────────────────────────────────
# Use only when stdout is a TTY; wrap with _supports_color() before calling.

_RESET = "\033[0m"
_BOLD = "\033[1m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_CYAN = "\033[36m"
_DIM = "\033[2m"


def _supports_color() -> bool:
    """Return True if stdout is a TTY that likely supports ANSI colors."""
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _supports_color_stderr() -> bool:
    """Return True if stderr is a TTY that likely supports ANSI colors."""
    return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()


def green(text: str) -> str:
    """Wrap text in green if stdout supports color."""
    if _supports_color():
        return f"{_GREEN}{text}{_RESET}"
    return text


def yellow(text: str) -> str:
    """Wrap text in yellow/amber if stdout supports color."""
    if _supports_color():
        return f"{_YELLOW}{text}{_RESET}"
    return text


def red(text: str) -> str:
    """Wrap text in red if stdout supports color."""
    if _supports_color():
        return f"{_RED}{text}{_RESET}"
    return text


def bold(text: str) -> str:
    """Wrap text in bold if stdout supports color."""
    if _supports_color():
        return f"{_BOLD}{text}{_RESET}"
    return text


def cyan(text: str) -> str:
    """Wrap text in cyan if stdout supports color."""
    if _supports_color():
        return f"{_CYAN}{text}{_RESET}"
    return text


def dim(text: str) -> str:
    """Wrap text in dim if stdout supports color."""
    if _supports_color():
        return f"{_DIM}{text}{_RESET}"
    return text


# ── Tag coloring ─────────────────────────────────────────────────────────────
# Maps tag names to their default color for print()-style output.
# Tags not in this map are printed dim.  Warnings/errors in messages
# (containing "Warning:", "Error:", "Failed:") get upgraded automatically.

_TAG_GREEN = frozenset({
    "OK", "SET", "SAME", "CREATE", "MKDIR", "BACKUP", "PRUNE", "KEEP",
})
_TAG_YELLOW = frozenset({
    "WARN", "SKIP", "DEINIT", "ADMIN", "DELETE",
})
_TAG_RED = frozenset({
    "FAIL", "MISSING", "ERROR",
})
_TAG_CYAN = frozenset({
    "PLAN", "SECRETS", "RECIPE", "STORE", "PROXY", "RESTORE", "VSCODE",
    "TOOLS", "AGENT", "DOCTOR", "SANDBOX", "MCP", "FETCH", "INFO",
    "ENV", "GPU", "IMAGE", "CONTAINER", "NATIVE", "CONFIG", "LOCAL",
    "COMMIT", "PUSH", "LSP", "LEAN-CTX", "CODEX", "PI",
    "CHROME", "CLEAN", "EXEC", "GITHUB", "INIT", "MIMO",
    "OPENCODE", "PROFILE", "PROFILES", "RUN", "UPDATE",
    "WEB", "WEB-BRIDGE",
})


def tag(name: str) -> str:
    """Return a colored ``[TAG]`` string for print/eprint output.

    Color is determined by the tag name.  Returns ``[NAME]`` with the
    appropriate ANSI color when stdout/stderr is a TTY, plain ``[NAME]``
    otherwise.
    """
    upper = name.upper()
    colored = f"[{upper}]"

    if upper in _TAG_GREEN:
        colored = green(colored)
    elif upper in _TAG_RED:
        colored = red(bold(colored))
    elif upper in _TAG_YELLOW:
        colored = yellow(colored)
    elif upper in _TAG_CYAN:
        colored = cyan(colored)
    else:
        colored = dim(colored)

    return colored
