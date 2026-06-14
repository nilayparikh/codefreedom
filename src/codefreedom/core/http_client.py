"""Shared HTTP client wrapping stdlib urllib with CodeFreedom conventions.

Provides get_json, get_text, get_response, and check_health helpers
along with HTTPError / HTTPStatusError exception types that callers
use for error handling.  Zero third-party dependencies — only stdlib.
"""

from __future__ import annotations

import json as _json
import urllib.error
import urllib.request
from typing import Any


# ── Exception hierarchy ───────────────────────────────────────────────────────


class HTTPError(Exception):
    """Base HTTP error (network or protocol failure)."""


class HTTPStatusError(HTTPError):
    """Non-2xx response from the server."""

    def __init__(self, message: str, *, status_code: int, url: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.url = url


# ── Response wrapper ─────────────────────────────────────────────────────────


class Response:
    """Thin wrapper around urllib's response, providing a familiar interface."""

    def __init__(self, status_code: int, headers: dict[str, str], body: bytes) -> None:
        self.status_code = status_code
        self.headers = headers
        self._body = body

    def json(self) -> Any:
        return _json.loads(self._body)

    @property
    def text(self) -> str:
        return self._body.decode("utf-8", errors="replace")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise HTTPStatusError(
                f"HTTP {self.status_code}",
                status_code=self.status_code,
                url="",
            )


# ── Internal helper ──────────────────────────────────────────────────────────


def _do_get(
    url: str,
    *,
    timeout: float = 10.0,
    headers: dict[str, str] | None = None,
) -> Response:
    """Perform a GET request using stdlib urllib. Raises HTTPError on failure."""
    req = urllib.request.Request(url, method="GET")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_headers = dict(resp.headers.items())
            body = resp.read()
            return Response(
                status_code=resp.status,
                headers=raw_headers,
                body=body,
            )
    except urllib.error.HTTPError as exc:
        body = exc.read() if exc.fp else b""
        raise HTTPStatusError(
            f"HTTP {exc.code}",
            status_code=exc.code,
            url=url,
        ) from exc
    except urllib.error.URLError as exc:
        raise HTTPError(str(exc.reason)) from exc


# ── Public API ───────────────────────────────────────────────────────────────


def get_json(
    url: str,
    *,
    timeout: float = 10.0,
    headers: dict[str, str] | None = None,
    bearer: str | None = None,
) -> dict:
    """GET a JSON endpoint. Returns parsed dict. Raises HTTPError on failure."""
    hdrs = dict(headers) if headers else {}
    if bearer:
        hdrs["Authorization"] = f"Bearer {bearer}"
    resp = _do_get(url, timeout=timeout, headers=hdrs)
    resp.raise_for_status()
    return resp.json()


def get_text(
    url: str,
    *,
    timeout: float = 15.0,
    headers: dict[str, str] | None = None,
) -> str:
    """GET a text endpoint. Returns decoded string. Raises HTTPError on failure."""
    hdrs = dict(headers) if headers else {}
    resp = _do_get(url, timeout=timeout, headers=hdrs)
    resp.raise_for_status()
    return resp.text


def check_health(url: str, *, timeout: float = 5.0) -> bool:
    """Return True if endpoint responds 2xx, False on any error."""
    try:
        resp = _do_get(url, timeout=timeout)
        return 200 <= resp.status_code < 300
    except HTTPError:
        return False


def get_response(
    url: str,
    *,
    timeout: float = 10.0,
    headers: dict[str, str] | None = None,
    bearer: str | None = None,
) -> Response:
    """GET a URL and return the full Response object. Raises on failure."""
    hdrs = dict(headers) if headers else {}
    if bearer:
        hdrs["Authorization"] = f"Bearer {bearer}"
    resp = _do_get(url, timeout=timeout, headers=hdrs)
    resp.raise_for_status()
    return resp
