"""Browser auto-open side effect.

Called by :mod:`codebase_memory.manager` after a successful
``CREATED`` or ``RESTARTED`` reconcile. Never raises — opening a browser
is a UI nicety, not a critical step.
"""
from __future__ import annotations

import logging
import webbrowser
from urllib.parse import quote


_log = logging.getLogger(__name__)


def open_ui(url: str) -> bool:
    """Open ``url`` in the user's default browser. Returns success bool.

    Cross-platform via Python stdlib ``webbrowser``: ``xdg-open`` on
    Linux, ``open`` on macOS, ``start`` on Windows. WSL/SSH-without-X
    forward will return ``False``; the caller should log the URL so the
    user can open it manually.

    Catches every exception: a broken ``$BROWSER`` env var or an
    uninstalled browser must not break ``cf r ag``.
    """
    try:
        ok = bool(webbrowser.open(url, new=2))
    except Exception as exc:  # noqa: BLE001 — intentional, side-effect only
        _log.debug("webbrowser.open raised: %s", exc)
        return False
    return ok


def safe_url(host: str, port: int, path: str = "/") -> str:
    """Build a browser-friendly URL. ``host`` is always ``127.0.0.1``."""
    return f"http://{quote(host, safe=':')}:{port}{path}"
