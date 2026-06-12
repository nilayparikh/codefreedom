"""Shared HTTP client wrapping httpx with CodeFreedom conventions.

Replaces scattered urllib.request / urlopen calls across the codebase.
"""

from __future__ import annotations

import httpx


def get_json(
    url: str,
    *,
    timeout: float = 10.0,
    headers: dict[str, str] | None = None,
    bearer: str | None = None,
) -> dict:
    """GET a JSON endpoint. Returns parsed dict. Raises httpx.HTTPError on failure."""
    hdrs = dict(headers) if headers else {}
    if bearer:
        hdrs["Authorization"] = f"Bearer {bearer}"

    resp = httpx.get(url, headers=hdrs, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def get_text(
    url: str,
    *,
    timeout: float = 15.0,
    headers: dict[str, str] | None = None,
) -> str:
    """GET a text endpoint. Returns decoded string. Raises httpx.HTTPError on failure."""
    hdrs = dict(headers) if headers else {}

    resp = httpx.get(url, headers=hdrs, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def check_health(url: str, *, timeout: float = 5.0) -> bool:
    """Return True if endpoint responds 2xx, False on any error."""
    try:
        resp = httpx.get(url, timeout=timeout)
        return 200 <= resp.status_code < 300
    except httpx.HTTPError:
        return False
