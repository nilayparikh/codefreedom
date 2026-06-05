"""MCP server for CodeFreedom Camoufox — web_search + lightweight web_fetch.

Two MCP tools:
  • web_search(query) — search configured engines, return structured results + AI summaries
  • web_fetch(url)    — lightweight page fetch: HTTP first, browser fallback if blocked

Internal: web_search uses a configurable cooldown (default 10s).
web_fetch has no cooldown — it runs immediately and prefers a fast HTTP path,
falling back to the Camoufox browser only when the site blocks plain HTTP.

The cooldown between searches is configured via the SEARCH_COOLDOWN_SECONDS
environment variable (float, default 10.0).

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
import re
import time
from typing import Any, Callable, Coroutine
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup
from fastmcp import FastMCP
from logger import get_logger

log = get_logger(__name__)

_INSTRUCTIONS = (
    "CodeFreedom Camoufox — stealth browser for web search and lightweight fetch. "
    "TWO TOOLS: web_search(query) — searches configured engines, returns structured results. "
    "web_fetch(url) — fast HTTP fetch with browser fallback for anti-bot pages. "
    "web_search has a configurable cooldown; web_fetch runs immediately. "
    "Passes Cloudflare, CreepJS, BrowserScan, Pixelscan via Camoufox when needed."
)

mcp = FastMCP("codefreedom-camoufox", instructions=_INSTRUCTIONS)

_dispatch: Callable[[dict], Coroutine[Any, Any, dict]] | None = None
_lock: asyncio.Lock | None = None
_last_search: float = 0.0


def _get_search_cooldown() -> float:
    """Read the search cooldown from SEARCH_COOLDOWN_SECONDS env var.

    Defaults to 10.0 seconds. Invalid values fall back to the default.
    """
    raw = os.environ.get("SEARCH_COOLDOWN_SECONDS", "10.0")
    try:
        return float(raw)
    except (TypeError, ValueError):
        log.warning(
            "SEARCH_COOLDOWN_SECONDS=%r is not a valid float, using default 10.0", raw
        )
        return 10.0


def _get_browser_restart_every() -> int:
    """How many searches to run before triggering a full browser restart.

    Defaults to 10. The browser process accumulates rendered-page memory in its
    persistent context; restarting it periodically releases that pressure. Set
    to 0 to disable periodic restarts.
    """
    raw = os.environ.get("BROWSER_RESTART_EVERY", "10")
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 10


# Tracks how many searches have been served since the last browser restart.
# When this reaches BROWSER_RESTART_EVERY we trigger a full restart.
_searches_since_restart: int = 0

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
# Internal: post-search cleanup — keep memory pressure low
# =============================================================================


async def _release_page_memory() -> None:
    """Navigate the active page to about:blank to release rendered state.

    Camoufox's persistent context keeps every visited page's rendered DOM in
    memory until the page is closed or navigated away. After every search we
    go to about:blank so the next search starts from a clean slate. Best-effort:
    any error is logged but does not propagate.
    """
    try:
        await _call(
            "run_script",
            steps=[{"action": "goto", "url": "about:blank", "wait_until": "load"}],
            name="cleanup_blank",
        )
    except Exception as exc:
        log.warning("Page memory release failed: %s", exc)


async def _periodic_browser_restart() -> bool:
    """Restart the browser process every N searches to release accumulated state.

    Returns True if a restart was triggered by this call.
    """
    global _searches_since_restart
    _searches_since_restart += 1
    every = _get_browser_restart_every()
    if every <= 0 or _searches_since_restart < every:
        return False

    log.info(
        "Periodic browser restart (every %d searches, count=%d)",
        every,
        _searches_since_restart,
    )
    try:
        # Tell main.py to restart the browser — it owns the Browser instance
        result = await _call("restart_browser")
        if not result.get("success"):
            log.warning("Browser restart failed: %s", result.get("error"))
            return False
        _searches_since_restart = 0
        return True
    except Exception as exc:
        log.warning("Browser restart raised: %s", exc)
        return False


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
# MCP Tools — only one (web_search)
# =============================================================================


@mcp.tool
async def web_search(query: str) -> str:
    """Search configured web engines for the given query.

    Returns structured results with titles, URLs, snippets, and AI summaries
    when available. If parsing yields no results, raw HTML is included.
    Internal: configurable cooldown (SEARCH_COOLDOWN_SECONDS env var, default 10s),
    session cleanup, periodic browser restart (BROWSER_RESTART_EVERY, default 10).

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

    # Cooldown (configurable via SEARCH_COOLDOWN_SECONDS, default 10s)
    cooldown = _get_search_cooldown()
    elapsed = time.time() - _last_search
    if elapsed < cooldown:
        wait = cooldown - elapsed
        log.info("Cooldown: waiting %.0fs", wait)
        await asyncio.sleep(wait)
    _last_search = time.time()

    # Delete cookies for fresh fingerprint on first search of session
    await _call("delete_cookies")

    try:
        # Search engines sequentially (can't parallelize through asyncio.Lock)
        all_results: list[dict] = []
        for engine_name, engine_cfg in engines.items():
            result = await _search_one(engine_name, engine_cfg, query)
            all_results.append(result)
    finally:
        # Always release page memory after a search, even on failure.
        # This keeps the persistent context from accumulating rendered DOMs.
        await _release_page_memory()

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

    # Periodic full browser restart to release accumulated cache / DOM / network state
    restarted = await _periodic_browser_restart()
    if restarted:
        output["browser_restarted"] = True

    return json.dumps(output, default=str)


# =============================================================================
# MCP Tools — web_fetch (lightweight, no cooldown)
# =============================================================================


# Status codes that mean "the site rejected our plain request — use the browser"
_BLOCK_STATUS_CODES = {403, 429, 503}

# Status codes that mean "fetch failed at the transport level" — also browser
_TRANSPORT_FAILURE_STATUSES = {0}

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"
)

# Tags we keep when extracting clean visible text from a page
_DROP_TAGS = {"script", "style", "noscript", "iframe", "svg", "canvas", "video"}


def _is_probably_blocked(html: str, status: int) -> bool:
    """Heuristic check for anti-bot challenges in plain HTTP responses.

    Returns True if the response looks like a Cloudflare / Akamai / DataDome
    challenge page (empty body, "checking your browser", etc.) — even when the
    HTTP status code is 200.
    """
    if status in _BLOCK_STATUS_CODES:
        return True
    if not html:
        return True
    head = html[:4096].lower()
    markers = (
        "checking your browser before accessing",
        "attention required! | cloudflare",
        "please complete the security check",
        "access denied",
        "verify you are human",
    )
    return any(m in head for m in markers)


def _extract_text_from_html(html: str, max_chars: int = 50000) -> str:
    """Strip scripts/styles and return clean visible text from HTML.

    Lightweight — no browser, no JS. Just BeautifulSoup get_text + collapse
    whitespace. Returns up to max_chars characters.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in _DROP_TAGS:
        for el in soup.find_all(tag):
            el.decompose()
    text = soup.get_text(separator="\n", strip=True)
    # Collapse runs of 3+ blank lines into a single blank line
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) > max_chars:
        text = text[:max_chars]
    return text


def _extract_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return ""


async def _http_fetch(url: str, timeout: float) -> dict | None:
    """Plain HTTP fetch via requests. Returns a dict or None on transport failure.

    The caller decides whether the response was actually usable (e.g. looks like
    an anti-bot challenge) and whether to fall back to the browser.
    """
    try:
        resp = await asyncio.to_thread(
            requests.get,
            url,
            headers={"User-Agent": _DEFAULT_USER_AGENT, "Accept": "*/*"},
            timeout=timeout,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        log.warning("HTTP fetch failed for %s: %s", url, exc)
        return None

    return {
        "url": resp.url,
        "status": resp.status_code,
        "html": resp.text,
    }


async def _browser_fetch(url: str, timeout: float) -> dict:
    """Browser-based fetch via the existing dispatcher. Last-resort fallback.

    Uses the same persistent browser context (no extra launches) but throws
    away the page state after the fetch to keep memory pressure low.
    """
    steps: list[dict] = [
        {"action": "goto", "url": url, "wait_until": "domcontentloaded"},
        {"action": "wait_for_network_idle", "timeout": int(timeout * 1000)},
        {"action": "get_text", "output_id": "text"},
        {"action": "get_html", "output_id": "html"},
        {"action": "eval", "expression": "document.title", "output_id": "title"},
    ]

    resp = await _call("run_script", steps=steps, name="web_fetch_browser")
    if not resp.get("success"):
        return {
            "url": url,
            "method": "browser",
            "error": resp.get("error", "browser fetch failed"),
        }

    outputs = resp.get("data", {}).get("outputs", {})
    text = outputs.get("text", {}).get("text", "")
    html = outputs.get("html", {}).get("html", "")
    title = outputs.get("title", {}).get("result", "")

    # Free the page memory — go to about:blank so Camoufox releases rendered state
    try:
        await _call(
            "run_script",
            steps=[{"action": "goto", "url": "about:blank", "wait_until": "load"}],
            name="web_fetch_cleanup",
        )
    except Exception:
        pass

    return {
        "url": url,
        "method": "browser",
        "title": title,
        "text": text[:50000],
        "text_truncated": len(text) > 50000,
        "html_length": len(html),
    }


@mcp.tool
async def web_fetch(
    url: str,
    timeout: float = 15.0,
    use_browser: bool | None = None,
    _include_screenshot: bool = False,
    _wait_until: str = "domcontentloaded",
) -> str:
    """Fetch a web page and return its text content. No cooldown.

    Tries a fast plain-HTTP fetch first. If the server blocks the request
    (Cloudflare, Akamai, JS-only pages, etc.) it falls back to a single-page
    Camoufox browser load, extracts the visible text, then releases the page
    back to about:blank to keep memory usage low.

    Use this for quick page reads. For full search, use web_search.

    Args:
        url: The URL to fetch
        timeout: Per-attempt timeout in seconds (default 15)
        use_browser: Force browser mode (True), force HTTP only (False),
                     or auto (default None = try HTTP first, fallback to browser)
        include_screenshot: (deprecated) Ignored — screenshots are no longer
                            captured. Use a separate screenshot tool if needed.
        wait_until: (deprecated) Ignored — page load strategy is now always
                    "domcontentloaded" with a network-idle grace period.
    """
    if not url or not urlparse(url).scheme.startswith("http"):
        return json.dumps({"url": url, "error": "Invalid URL — must be http(s)"})

    log.info("web_fetch: %s (timeout=%.0fs, use_browser=%s)", url, timeout, use_browser)

    if use_browser is not True:
        # Fast path: plain HTTP
        http_resp = await _http_fetch(url, timeout)
        if http_resp is not None and not _is_probably_blocked(
            http_resp["html"], http_resp["status"]
        ):
            html = http_resp["html"]
            text = _extract_text_from_html(html)
            return json.dumps(
                {
                    "url": http_resp["url"],
                    "method": "http",
                    "status": http_resp["status"],
                    "title": _extract_title(html),
                    "text": text,
                    "text_truncated": len(text) >= 50000,
                },
                default=str,
            )

        if use_browser is False:
            return json.dumps(
                {
                    "url": url,
                    "method": "http",
                    "error": "HTTP fetch blocked or empty; use_browser=False",
                }
            )

        log.info("web_fetch: HTTP blocked, falling back to browser for %s", url)

    # Slow path: browser (only when HTTP is blocked or browser is forced)
    result = await _browser_fetch(url, timeout)
    return json.dumps(result, default=str)
