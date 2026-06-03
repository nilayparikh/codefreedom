"""MCP server for CodeFreedom Camoufox — web_search + web_fetch.

Only two MCP tools:
  • web_search(query) — search Brave + Bing, return structured results + AI summaries
  • web_fetch(url)    — fetch a page, return text + HTML + optional screenshot

Internal: rate limiting (30s cooldown), session cleanup, parallel search.
Mounted at /mcp on the main HTTP server.
"""

# pylint: disable=global-statement,broad-exception-caught

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Callable, Coroutine
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from fastmcp import FastMCP
from logger import get_logger

log = get_logger(__name__)

_INSTRUCTIONS = (
    "CodeFreedom Camoufox — stealth browser for web search and scraping. "
    "TWO TOOLS: web_search(query) — searches Brave+Bing, returns structured results. "
    "web_fetch(url) — fetches a page blocked by standard HTTP, returns text+HTML. "
    "Internal: 30s cooldown between searches, session cleanup, Camoufox fingerprinting. "
    "Passes Cloudflare, CreepJS, BrowserScan, Pixelscan."
)

mcp = FastMCP("codefreedom-camoufox", instructions=_INSTRUCTIONS)

_dispatch: Callable[[dict], Coroutine[Any, Any, dict]] | None = None
_lock: asyncio.Lock | None = None
_last_search: float = 0.0
SEARCH_COOLDOWN = 30.0

ENGINE_URLS = {
    "brave": "https://search.brave.com/search?q={q}",
    "bing": "https://www.bing.com/search?q={q}&form=QBLH",
}


def set_dispatcher(
    fn: Callable[[dict], Coroutine[Any, Any, dict]], lock: asyncio.Lock | None = None
) -> None:
    global _dispatch, _lock
    _dispatch = fn
    _lock = lock


async def _call(action: str, **params: Any) -> dict:
    if not _dispatch:
        return {"success": False, "error": "Browser not ready"}
    filtered = {k: v for k, v in params.items() if v is not None}
    cmd: dict[str, Any] = {"action": action}
    cmd.update(filtered)
    if _lock:
        async with _lock:
            return await _dispatch(cmd)
    return await _dispatch(cmd)


def _text_result(result: dict) -> str:
    return json.dumps({k: v for k, v in result.items() if k != "_binary"}, default=str)


# =============================================================================
# Internal: search parser (Brave + Bing)
# =============================================================================


def _parse_brave(html: str) -> tuple[list[dict], dict | None]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for s in soup.select("[data-type='web']"):
        a = s.select_one("a[href]")
        if not a:
            continue
        href = str(a.get("href", ""))
        if not href.startswith("http"):
            continue
        title_el = s.select_one(".title.search-snippet-title")
        desc_el = s.select_one(".generic-snippet .content")
        results.append(
            {
                "title": (
                    title_el.get_text(strip=True)
                    if title_el
                    else a.get_text(strip=True)
                ),
                "url": href,
                "snippet": desc_el.get_text(strip=True) if desc_el else "",
            }
        )
    # AI summary
    ai_el = soup.select_one(".chatllm-content")
    ai = None
    if ai_el:
        text = ai_el.get_text(strip=True)
        if len(text) > 20:
            sources = []
            for a in ai_el.select("a[href]"):
                href = str(a.get("href", ""))
                if href.startswith("http"):
                    sources.append({"text": a.get_text(strip=True), "url": href})
            ai = {"text": text, "sources": sources}
    return results, ai


def _parse_bing(html: str) -> tuple[list[dict], dict | None]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for el in soup.select("#b_results .b_algo"):
        a = el.select_one("h2 a")
        if not a:
            continue
        href = str(a.get("href", ""))
        if not href.startswith("http"):
            continue
        p = el.select_one(".b_caption p, .b_lineclamp2")
        results.append(
            {
                "title": a.get_text(strip=True),
                "url": href,
                "snippet": p.get_text(strip=True) if p else "",
            }
        )
    # AI summary
    ai = None
    for sel in [".b_ans", ".rai_content"]:
        ai_el = soup.select_one(sel)
        if not ai_el:
            continue
        text = ai_el.get_text(strip=True)
        if len(text) <= 20:
            continue
        sources = []
        for a in ai_el.select("a[href]"):
            href = str(a.get("href", ""))
            if href.startswith("http"):
                sources.append({"text": a.get_text(strip=True), "url": href})
        ai = {"text": text, "sources": sources}
        break
    return results, ai


PARSERS = {"brave": _parse_brave, "bing": _parse_bing}


async def _search_one(engine: str, query: str) -> dict:
    url = ENGINE_URLS[engine].format(q=quote_plus(query))
    resp = await _call(
        "run_script",
        steps=[
            {"action": "goto", "url": url, "wait_until": "domcontentloaded"},
            {"action": "sleep", "duration": 2},
            {"action": "get_html", "output_id": "html"},
        ],
        name=f"search_{engine}",
    )
    if not resp.get("success"):
        return {
            "engine": engine,
            "results": [],
            "ai_summary": None,
            "error": resp.get("error", "failed"),
        }
    html = resp.get("data", {}).get("outputs", {}).get("html", {}).get("html", "")
    if not html:
        return {"engine": engine, "results": [], "ai_summary": None, "error": "no html"}
    parser = PARSERS.get(engine)
    if not parser:
        return {
            "engine": engine,
            "results": [],
            "ai_summary": None,
            "error": "no parser",
        }
    results, ai = parser(html)
    return {"engine": engine, "results": results, "ai_summary": ai}


# =============================================================================
# MCP Tools — only two
# =============================================================================


@mcp.tool
async def web_search(query: str) -> str:
    """Search Brave and Bing for the given query.

    Returns structured results with titles, URLs, snippets, and AI summaries
    when available. Internal: 30s cooldown, session cleanup, parallel search.

    Args:
        query: The search query string
    """
    global _last_search

    # Cooldown
    elapsed = time.time() - _last_search
    if elapsed < SEARCH_COOLDOWN:
        wait = SEARCH_COOLDOWN - elapsed
        log.info("Cooldown: waiting %.0fs", wait)
        await asyncio.sleep(wait)
    _last_search = time.time()

    # Delete cookies for fresh fingerprint on first search of session
    await _call("delete_cookies")

    # Search engines sequentially (can't parallelize through asyncio.Lock)
    brave_result = await _search_one("brave", query)
    bing_result = await _search_one("bing", query)

    output: dict[str, Any] = {
        "query": query,
        "results": [],
        "ai_summaries": [],
    }
    for r in [brave_result, bing_result]:
        for item in r.get("results", []):
            item["engine"] = r["engine"]
            output["results"].append(item)
        if r.get("ai_summary"):
            summary = r["ai_summary"]
            summary["engine"] = r["engine"]
            output["ai_summaries"].append(summary)

    return json.dumps(output, default=str)


@mcp.tool
async def web_fetch(
    url: str,
    include_screenshot: bool = False,
    wait_until: str = "networkidle",
) -> str:
    """Fetch a web page using Camoufox (bypasses anti-bot protection).

    Use when standard HTTP fetch is blocked by Cloudflare, bot detection,
    or JS-rendering requirements. Returns page text, HTML, and title.

    Args:
        url: The URL to fetch
        include_screenshot: Also return a screenshot (whLargest=512)
        wait_until: "domcontentloaded", "load", or "networkidle" (default)
    """
    # Delete cookies for clean session
    await _call("delete_cookies")

    steps: list[dict] = [
        {"action": "goto", "url": url, "wait_until": wait_until},
        {"action": "wait_for_network_idle", "timeout": 15},
        {"action": "get_text", "output_id": "text"},
        {"action": "get_html", "output_id": "html"},
        {"action": "eval", "expression": "document.title", "output_id": "title"},
    ]
    if include_screenshot:
        steps.append(
            {"action": "save_screenshot", "output_id": "screenshot", "whLargest": 512}
        )

    resp = await _call("run_script", steps=steps, name="web_fetch")
    if not resp.get("success"):
        return json.dumps({"error": resp.get("error", "fetch failed")})

    outputs = resp.get("data", {}).get("outputs", {})
    result: dict[str, Any] = {
        "url": url,
        "title": outputs.get("title", {}).get("result", ""),
        "text": outputs.get("text", {}).get("text", ""),
        "html": outputs.get("html", {}).get("html", ""),
    }
    if include_screenshot:
        result["screenshot_base64"] = outputs.get("screenshot", "")

    return json.dumps(result, default=str)
