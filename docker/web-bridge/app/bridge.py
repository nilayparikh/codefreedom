"""SearXNG-shaped HTTP bridge in front of the CodeFreedom Camoufox MCP web_search.

Exposes a small subset of the SearXNG JSON API:

    GET /search?q=<query>&format=json   -> SearXNG-shaped JSON
    GET /healthz                        -> {"status": "ok"}

Talks to the Camoufox container via FastMCP Streamable HTTP at
``${MCP_WEB_URL}/mcp``. The bridge initializes a fresh MCP session per
request (stateless) — simple, crash-safe, adds one extra round trip per
query. If latency ever matters we can promote to a pooled session.

Failure modes:
  * MCP unreachable        -> HTTP 502 ``{"error": "mcp_unreachable", ...}``
  * MCP returns error      -> HTTP 502 ``{"error": "mcp_error", "detail": ...}``
  * Cooldown not elapsed   -> HTTP 429 ``{"error": "cooldown", "retry_after": N}``
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any

import httpx
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

# ── Configuration ──────────────────────────────────────────────────────────

MCP_WEB_URL = os.environ.get("MCP_WEB_URL", "http://host.docker.internal:8420/mcp")
MCP_TIMEOUT_SECONDS = float(os.environ.get("MCP_TIMEOUT_SECONDS", "30"))
COOLDOWN_SECONDS = float(os.environ.get("WEB_BRIDGE_COOLDOWN_SECONDS", "2.0"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "info").upper()

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("web-bridge")

# ── Cooldown state ─────────────────────────────────────────────────────────

_last_call_ts: float | None = None
_call_lock_token: str | None = None  # identifies the cooldown owner for debugging


def _cooldown_remaining() -> float:
    """Seconds left in the cooldown window. 0 if not in cooldown."""
    if _last_call_ts is None:
        return 0.0
    elapsed = time.monotonic() - _last_call_ts
    remaining = COOLDOWN_SECONDS - elapsed
    return max(0.0, remaining)


# ── MCP client (stateless) ─────────────────────────────────────────────────


class McpError(RuntimeError):
    """Raised when the MCP server returns an error or is unreachable."""


def _parse_json_or_sse(body: str) -> dict[str, Any]:
    """Parse either a plain JSON body or an MCP SSE `event: message` frame.

    FastMCP Streamable HTTP may return `text/event-stream` with content like:

        event: message
        data: {"jsonrpc":"2.0", ...}

    This helper accepts both that format and raw JSON.
    """
    text = body.strip()
    if not text:
        raise ValueError("empty body")

    # Fast path: plain JSON response.
    if text.startswith("{"):
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("JSON body is not an object")
        return parsed

    # Streamable HTTP (SSE): extract and join all `data:` lines.
    data_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("data:"):
            data_lines.append(line[5:].strip())

    if not data_lines:
        raise ValueError("SSE body has no data lines")

    payload = "\n".join(data_lines)
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("SSE payload JSON is not an object")
    return parsed


async def _mcp_call_search(query: str) -> dict[str, Any]:
    """Call the ``web_search`` tool on the Camoufox MCP.

    Performs a fresh session handshake (``initialize`` + ``notifications/initialized``)
    then issues a ``tools/call`` for ``web_search(query=...)``. Returns the
    parsed MCP result ``content[0].text`` (which is a JSON string from the tool).
    Raises :class:`McpError` on transport or protocol failures.
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    async with httpx.AsyncClient(
        timeout=MCP_TIMEOUT_SECONDS, headers=headers
    ) as client:
        # 1. Initialize a session.
        init_payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "codefreedom-web-bridge", "version": "0.1.0"},
            },
        }
        try:
            init_resp = await client.post(MCP_WEB_URL, json=init_payload)
        except httpx.HTTPError as exc:
            raise McpError(f"mcp_unreachable: {exc}") from exc

        if init_resp.status_code >= 400:
            raise McpError(
                f"mcp_init_failed: HTTP {init_resp.status_code}: {init_resp.text[:200]}"
            )

        session_id = init_resp.headers.get("mcp-session-id")
        if not session_id:
            raise McpError("mcp_init_failed: missing Mcp-Session-Id header")

        # 2. Send notifications/initialized (MCP requires this after handshake).
        notif_headers = {**headers, "Mcp-Session-Id": session_id}
        notif_payload = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }
        try:
            notif_resp = await client.post(
                MCP_WEB_URL, json=notif_payload, headers=notif_headers
            )
            # Notifications get 202 Accepted with empty body — anything 2xx is fine.
            if notif_resp.status_code >= 400:
                log.warning(
                    "MCP notifications/initialized returned HTTP %d (continuing)",
                    notif_resp.status_code,
                )
        except httpx.HTTPError as exc:
            # Notifications are best-effort — log and continue.
            log.warning("MCP notifications/initialized failed: %s (continuing)", exc)

        # 3. Call the web_search tool.
        call_payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {
                "name": "web_search",
                "arguments": {"query": query},
            },
        }
        try:
            call_resp = await client.post(
                MCP_WEB_URL, json=call_payload, headers=notif_headers
            )
        except httpx.HTTPError as exc:
            raise McpError(f"mcp_call_failed: {exc}") from exc

        if call_resp.status_code >= 400:
            raise McpError(
                f"mcp_call_failed: HTTP {call_resp.status_code}: {call_resp.text[:200]}"
            )

        try:
            call_data = _parse_json_or_sse(call_resp.text)
        except (json.JSONDecodeError, ValueError) as exc:
            raise McpError(f"mcp_call_failed: invalid response payload: {exc}") from exc

        # JSON-RPC level error.
        if "error" in call_data:
            err = call_data["error"]
            msg = err.get("message", "unknown error") if isinstance(err, dict) else str(err)
            raise McpError(f"mcp_error: {msg}")

        result = call_data.get("result", {})
        if result.get("isError"):
            # MCP tool-level error (returned in content[].text as JSON string).
            content = result.get("content", [])
            if content and isinstance(content, list):
                first = content[0]
                if isinstance(first, dict) and first.get("type") == "text":
                    raise McpError(f"mcp_error: {first.get('text', '')[:200]}")
            raise McpError("mcp_error: tool reported isError=True")

        # Success — extract text payload.
        content = result.get("content", [])
        if not content or not isinstance(content, list):
            raise McpError("mcp_error: empty content array")

        first = content[0]
        if not isinstance(first, dict) or first.get("type") != "text":
            raise McpError(f"mcp_error: unexpected content type: {first}")

        text = first.get("text", "")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise McpError(f"mcp_error: tool text is not valid JSON: {exc}") from exc


# ── Mapper: MCP web_search response -> SearXNG JSON ───────────────────────


def _map_mcp_to_searxng(mcp_data: dict[str, Any], query: str) -> dict[str, Any]:
    """Convert the MCP ``web_search`` JSON into SearXNG's ``format=json`` shape.

    Field mapping:
        MCP results[].title     -> SearXNG results[].title
        MCP results[].url       -> SearXNG results[].url
        MCP results[].snippet   -> SearXNG results[].content
        MCP results[].engine    -> SearXNG results[].engine
        MCP ai_summaries[].text -> SearXNG answers[]
        MCP ai_summaries[].sources[] -> merged into results[] as engine="ai"

    If the MCP response has an "error" field, the SearXNG response includes
    an error block and returns an empty result list.
    """
    searxng: dict[str, Any] = {
        "query": mcp_data.get("query", query),
        "results": [],
        "answers": [],
        "infoboxes": [],
        "suggestions": [],
        "number_of_results": 0,
    }

    # Surface any MCP-side error to the caller.
    if "error" in mcp_data:
        searxng["error"] = mcp_data["error"]
        return searxng

    seen_urls: set[str] = set()
    for r in mcp_data.get("results", []) or []:
        if not isinstance(r, dict):
            continue
        url = r.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        searxng["results"].append(
            {
                "title": r.get("title", ""),
                "url": url,
                "content": r.get("snippet", ""),
                "engine": r.get("engine", ""),
            }
        )

    # AI summaries -> SearXNG answers (and merged source results).
    for summary in mcp_data.get("ai_summaries", []) or []:
        if not isinstance(summary, dict):
            continue
        text = summary.get("text", "")
        if text:
            searxng["answers"].append(text)
        for src in summary.get("sources", []) or []:
            if not isinstance(src, dict):
                continue
            src_url = src.get("url", "")
            if not src_url or src_url in seen_urls:
                continue
            seen_urls.add(src_url)
            searxng["results"].append(
                {
                    "title": src.get("text", ""),
                    "url": src_url,
                    "content": "",
                    "engine": "ai",
                }
            )

    searxng["number_of_results"] = len(searxng["results"])
    return searxng


# ── FastAPI app ────────────────────────────────────────────────────────────

app = FastAPI(
    title="CodeFreedom Web Search Bridge",
    version="0.1.0",
    description=(
        "SearXNG-shaped HTTP front for the CodeFreedom Camoufox MCP web_search. "
        "Lets LiteLLM's websearch_interception route Claude Code's native WebSearch "
        "to a local stealth browser."
    ),
    docs_url=None,  # No interactive docs in the container; we keep it minimal.
    redoc_url=None,
)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/search")
async def search(
    q: str = Query(..., min_length=1, description="Search query"),
    # `format` is part of the SearXNG-shaped API contract; we always reply JSON,
    # so the param is accepted/validated but not consumed. Use an alias to keep
    # the URL name `format` while avoiding shadowing the built-in.
    # `noqa: ARG001` — accepted by API but intentionally unused in the body.
    format_: str = Query("json", pattern="^json$", alias="format"),  # noqa: ARG001
) -> JSONResponse:
    # pylint: disable-next=global-statement
    global _last_call_ts, _call_lock_token
    log.info("search: q=%r format=%r", q, format_)

    # Cooldown check.
    remaining = _cooldown_remaining()
    if remaining > 0:
        log.info("cooldown: %.2fs remaining", remaining)
        return JSONResponse(
            status_code=429,
            content={
                "error": "cooldown",
                "retry_after": round(remaining, 3),
                "results": [],
                "answers": [],
            },
            headers={"Retry-After": str(max(1, int(remaining) + 1))},
        )

    # Mark cooldown owner before the call (in case MCP hangs, the window
    # still protects downstream callers).
    _last_call_ts = time.monotonic()
    _call_lock_token = str(uuid.uuid4())

    try:
        mcp_data = await _mcp_call_search(q)
    except McpError as exc:
        log.warning("MCP call failed: %s", exc)
        return JSONResponse(
            status_code=502,
            content={
                "error": str(exc),
                "results": [],
                "answers": [],
                "query": q,
            },
        )
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        # Last-resort guard for the HTTP boundary: never let an unknown failure
        # escape as an unhandled 500 with a stack trace. Logged via log.exception.
        log.exception("unexpected error in /search")
        return JSONResponse(
            status_code=500,
            content={
                "error": f"internal_error: {exc}",
                "results": [],
                "answers": [],
                "query": q,
            },
        )

    searxng = _map_mcp_to_searxng(mcp_data, query=q)
    log.info(
        "search ok: results=%d answers=%d",
        searxng.get("number_of_results", 0),
        len(searxng.get("answers", [])),
    )
    return JSONResponse(content=searxng)
