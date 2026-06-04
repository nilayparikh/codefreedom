"""MCP server for CodeFreedom Camoufox — web_search + web_fetch.

Only two MCP tools:
  • web_search(query) — search configured engines, return structured results + AI summaries
  • web_fetch(url)    — fetch a page, return text + HTML + optional screenshot

Internal: rate limiting (30s cooldown), session cleanup, parallel search.
Mounted at /mcp on the main HTTP server.

Search engines are configured via the SEARCH_ENGINES environment variable
(a JSON object where each key maps to {url, parser}).
Example:
  {"example": {"url": "https://s.example.com/search?q={q}", "parser": "standard"}}

Parser names resolve to CSS-selector configurations in PARSER_REGISTRY.
If parsing yields no results, raw HTML is returned as a fallback.
"""

# pylint: disable=global-statement,broad-exception-caught

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Callable, Coroutine
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from fastmcp import FastMCP
from logger import get_logger

log = get_logger(__name__)

_INSTRUCTIONS = (
    "CodeFreedom Camoufox — stealth browser for web search and scraping. "
    "TWO TOOLS: web_search(query) — searches configured engines, returns structured results. "
    "web_fetch(url) — fetches a page blocked by standard HTTP, returns text+HTML. "
    "Internal: 30s cooldown between searches, session cleanup, Camoufox fingerprinting. "
    "Passes Cloudflare, CreepJS, BrowserScan, Pixelscan."
)

mcp = FastMCP("codefreedom-camoufox", instructions=_INSTRUCTIONS)

_dispatch: Callable[[dict], Coroutine[Any, Any, dict]] | None = None
_lock: asyncio.Lock | None = None
_last_search: float = 0.0
SEARCH_COOLDOWN = 30.0

# =============================================================================
# Parser registry — loaded from PARSER_REGISTRY env var at startup.
# Each parser entry maps to CSS-selector config: result_selectors, link_selector,
# snippet_selectors, ai_selectors.  No selectors are hardcoded — the profile
# supplies everything.  If unconfigured, the parser falls back to generic
# DOM traversal.
# =============================================================================

_parser_registry: dict[str, dict] | None = None


def _load_parser_registry() -> dict[str, dict]:
    """Load parser configurations from PARSER_REGISTRY env var.

    Expects a JSON object: {"parser_name": {"result_selectors": "...", ...}}
    Returns an empty dict if not configured — the parser will use generic fallbacks.
    """
    raw = os.environ.get("PARSER_REGISTRY", "")
    if not raw:
        return {}
    try:
        registry = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("PARSER_REGISTRY env var is not valid JSON, ignoring")
        return {}
    if not isinstance(registry, dict):
        log.warning("PARSER_REGISTRY must be a JSON object, ignoring")
        return {}
    # Validate each entry is a dict with string keys
    valid: dict[str, dict] = {}
    for name, cfg in registry.items():
        if not isinstance(name, str) or not isinstance(cfg, dict):
            log.warning(
                "PARSER_REGISTRY entry %s is not string->object, skipping", name
            )
            continue
        valid[name] = cfg
    return valid


def _get_parser_registry() -> dict[str, dict]:
    global _parser_registry
    if _parser_registry is None:
        _parser_registry = _load_parser_registry()
    return _parser_registry


def _load_search_engines() -> dict[str, dict]:
    """Load search engine configs from SEARCH_ENGINES env var.

    Supports two formats:
      New:  {"name": {"url": "...", "parser": "standard"}}
      Old:  {"name": "https://s.example.com/search?q={q}"}  → parser defaults to "standard"

    Returns a dict of {engine_name: {url, parser}}.
    """
    raw = os.environ.get("SEARCH_ENGINES", "")
    if not raw:
        return {}
    try:
        raw_engines = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("SEARCH_ENGINES env var is not valid JSON, ignoring")
        return {}
    if not isinstance(raw_engines, dict):
        log.warning("SEARCH_ENGINES must be a JSON object, ignoring")
        return {}

    valid: dict[str, dict] = {}
    for name, value in raw_engines.items():
        if not isinstance(name, str):
            continue

        if isinstance(value, str):
            # Old format: plain URL string
            if "{q}" not in value:
                log.warning(
                    "SEARCH_ENGINES entry %s missing {q} placeholder, skipping", name
                )
                continue
            valid[name] = {"url": value, "parser": "standard"}
        elif isinstance(value, dict):
            url = value.get("url", "")
            if not isinstance(url, str) or "{q}" not in url:
                log.warning(
                    "SEARCH_ENGINES entry %s has invalid or missing url, skipping", name
                )
                continue
            parser = value.get("parser", "standard")
            if not isinstance(parser, str):
                parser = "standard"
            if parser not in _get_parser_registry():
                log.warning(
                    "SEARCH_ENGINES entry %s: parser '%s' not in registry, "
                    "will use generic fallback",
                    name,
                    parser,
                )
            valid[name] = {"url": url, "parser": parser}
        else:
            log.warning(
                "SEARCH_ENGINES entry %s is not a string or object, skipping", name
            )

    return valid


# Lazily loaded and cached — engines don't change during container lifetime
_search_engines: dict[str, dict] | None = None


def _get_search_engines() -> dict[str, dict]:
    global _search_engines
    if _search_engines is None:
        _search_engines = _load_search_engines()
    return _search_engines


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
# Internal: parser-driven search result extraction
# =============================================================================


def _parse_search_results(
    html: str, parser_name: str = "standard"
) -> tuple[list[dict], dict | None]:
    """Parse search results using the named parser configuration.

    Looks up parser_name in the configured parser registry (from PARSER_REGISTRY
    env var).  Falls back to generic DOM traversal if no config is found.

    Returns (results, ai_summary).  If no results are found, results will be
    empty — the caller should include raw HTML as fallback output.
    """
    registry = _get_parser_registry()
    parser_cfg = registry.get(parser_name, registry.get("standard", {}))
    if not parser_cfg:
        return [], None

    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []
    seen_urls: set[str] = set()

    result_containers = soup.select(parser_cfg.get("result_selectors", ""))
    if not result_containers:
        result_containers = soup.select("a[href]")

    for container in result_containers:
        if container.name == "a":
            a = container
        else:
            elem = container.select_one(parser_cfg.get("link_selector", "a[href]"))
            a = elem if elem is not None else container
        if not a:
            continue
        href = str(a.get("href", ""))
        if not href.startswith("http"):
            continue
        if href in seen_urls:
            continue
        seen_urls.add(href)

        title = a.get_text(strip=True)

        snippet = ""
        if container.name != "a":
            snippet_el = container.select_one(parser_cfg.get("snippet_selectors", ""))
            if snippet_el:
                snippet = snippet_el.get_text(strip=True)
            elif container.name in ("li", "div"):
                full = container.get_text(strip=True)
                if title and full.startswith(title):
                    snippet = full[len(title) :].strip()
                elif len(full) > len(title):
                    snippet = full

        results.append({"title": title, "url": href, "snippet": snippet})

    # AI summary
    ai: dict | None = None
    for sel in parser_cfg.get("ai_selectors", []):
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


async def _search_one(engine: str, engine_cfg: dict, query: str) -> dict:
    """Search a single engine and parse results.

    engine_cfg must have 'url' and optionally 'parser' keys.
    If parsing yields no results, raw HTML is included in the output.
    """
    url_template = engine_cfg["url"]
    parser_name = engine_cfg.get("parser", "standard")

    url = url_template.format(q=quote_plus(query))
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

    results, ai = _parse_search_results(html, parser_name)

    entry: dict = {
        "engine": engine,
        "results": results,
        "ai_summary": ai,
    }

    # Fallback: if no results were extracted, include raw HTML
    if not results:
        entry["raw_html"] = html[:50000]  # truncate to avoid huge payloads
        entry["raw_html_truncated"] = len(html) > 50000

    return entry


# =============================================================================
# MCP Tools — only two
# =============================================================================


@mcp.tool
async def web_search(query: str) -> str:
    """Search configured web engines for the given query.

    Returns structured results with titles, URLs, snippets, and AI summaries
    when available. If parsing yields no results, raw HTML is included.
    Internal: 30s cooldown, session cleanup.

    Engines are configured via the SEARCH_ENGINES environment variable.

    Args:
        query: The search query string
    """
    global _last_search

    engines = _get_search_engines()
    if not engines:
        return json.dumps(
            {
                "query": query,
                "results": [],
                "ai_summaries": [],
                "error": "No search engines configured. Set SEARCH_ENGINES env var.",
            }
        )

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
    all_results: list[dict] = []
    for engine_name, engine_cfg in engines.items():
        result = await _search_one(engine_name, engine_cfg, query)
        all_results.append(result)

    output: dict[str, Any] = {
        "query": query,
        "results": [],
        "ai_summaries": [],
    }
    raw_html_blocks: list[dict] = []
    for r in all_results:
        for item in r.get("results", []):
            item["engine"] = r["engine"]
            output["results"].append(item)
        if r.get("ai_summary"):
            summary = r["ai_summary"]
            summary["engine"] = r["engine"]
            output["ai_summaries"].append(summary)
        if r.get("raw_html"):
            raw_html_blocks.append(
                {
                    "engine": r["engine"],
                    "html": r["raw_html"],
                    "truncated": r.get("raw_html_truncated", False),
                }
            )
    if raw_html_blocks:
        output["raw_html"] = raw_html_blocks

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
