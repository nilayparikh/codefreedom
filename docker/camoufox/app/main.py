#!/usr/bin/env python3
# pylint: disable=global-statement,broad-exception-caught,protected-access
"""
CodeFreedom Camoufox — Stealth browser with MCP-only server (Streamable HTTP).

Camoufox (custom Firefox fork) with zero CDP exposure. Supports both
Playwright (DOM-level) clicks and PyAutoGUI (OS-level) clicks.
PyAutoGUI clicks are undetectable by behavioral analysis.

Endpoints:
    POST/GET /mcp           - MCP Streamable HTTP (AI agent interface)
                              Tools: web_search, web_fetch
"""

from __future__ import annotations

import asyncio
import io
import os
import sys
import time
from typing import Any

import uvicorn
from browser import Browser
from fastapi import FastAPI
from PIL import Image
from script_runner import load_script, run_script
from system import System

from logger import get_logger

log = get_logger(__name__)


def log_request(action: str, params: dict | None = None) -> None:
    if params:
        log.info(">> %s %s", action, params)
    else:
        log.info(">> %s", action)


def log_response(success: bool, msg: str = "") -> None:
    if success:
        log.info("<< OK %s", msg)
    else:
        log.warning("<< FAIL %s", msg)


# =============================================================================
# GLOBALS
# =============================================================================

system = System()
browser: Browser | None = None
loaders_dir: str = "/loaders"

_last_dialog: dict | None = None
_next_dialog_action: dict | None = None

_DIALOG_BUTTONS: dict[str, list[str]] = {
    "alert": ["ok"],
    "confirm": ["ok", "cancel"],
    "prompt": ["ok", "cancel"],
    "beforeunload": ["leave", "stay"],
}

_active_page: Any = None
_last_download: dict | None = None

_network_log: list[dict] = []
_network_logging: bool = False
_network_handler_pages: set[int] = set()

_console_log: list[dict] = []
_console_logging: bool = False
_console_handler_pages: set[int] = set()

HTTP_LISTEN_HOST = os.environ.get("HTTP_LISTEN_HOST", "0.0.0.0")
HTTP_LISTEN_PORT = int(os.environ.get("HTTP_LISTEN_PORT", "8420"))
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "").strip() or None

SCRIPT_PATH: str | None = None
_args = sys.argv[1:]
if len(_args) >= 2 and _args[0] == "--script":
    SCRIPT_PATH = _args[1]

# =============================================================================
# EVENT HANDLERS
# =============================================================================


async def _on_dialog(dialog: Any) -> None:
    global _last_dialog, _next_dialog_action
    _last_dialog = {
        "type": dialog.type,
        "message": dialog.message,
        "default_value": dialog.default_value,
        "buttons": _DIALOG_BUTTONS.get(dialog.type, ["ok"]),
    }
    log.info("Dialog [%s]: %s", dialog.type, dialog.message)
    action = _next_dialog_action
    _next_dialog_action = None
    if action and not action.get("accept", True):
        await dialog.dismiss()
        return
    prompt_text = action.get("text") if action else None
    if prompt_text is not None:
        await dialog.accept(prompt_text)
        return
    await dialog.accept()


async def _on_download(download: Any) -> None:
    global _last_download
    try:
        path = await download.path()
        _last_download = {
            "url": download.url,
            "filename": download.suggested_filename,
            "path": str(path) if path else None,
        }
    except Exception:
        _last_download = {
            "url": download.url,
            "filename": download.suggested_filename,
            "path": None,
        }
    log.info("Download: %s", download.suggested_filename)


def _on_request(request: Any) -> None:
    if not _network_logging:
        return
    _network_log.append(
        {
            "type": "request",
            "url": request.url,
            "method": request.method,
            "resource_type": request.resource_type,
            "timestamp": time.time(),
        }
    )


def _on_response(response: Any) -> None:
    if not _network_logging:
        return
    _network_log.append(
        {
            "type": "response",
            "url": response.url,
            "status": response.status,
            "timestamp": time.time(),
        }
    )


def _on_console(message: Any) -> None:
    if not _console_logging:
        return
    _console_log.append(
        {
            "type": message.type,
            "text": message.text,
            "location": message.location,
            "timestamp": time.time(),
        }
    )


def _setup_page_handlers(page: Any) -> None:
    page.on("dialog", _on_dialog)
    page.on("download", _on_download)
    page_id = id(page)
    if page_id not in _network_handler_pages:
        page.on("request", _on_request)
        page.on("response", _on_response)
        _network_handler_pages.add(page_id)
    if page_id not in _console_handler_pages:
        page.on("console", _on_console)
        _console_handler_pages.add(page_id)


def get_active_page() -> Any:
    global _active_page
    ctx = browser._context if browser else None
    if not ctx:
        return None
    pages = ctx.pages
    if not pages:
        _active_page = None
        return None
    if _active_page is None or _active_page not in pages:
        _active_page = pages[-1]
    return _active_page


async def get_window_offset_js(page) -> dict:
    try:
        return await page.evaluate(
            """() => ({ x: Math.round(window.mozInnerScreenX), y: Math.round(window.mozInnerScreenY) })"""
        )
    except Exception:
        return {"x": 0, "y": 0}


def make_response(
    success: bool, data: dict | None = None, error: str | None = None
) -> dict:
    resp: dict = {"success": success, "timestamp": time.time()}
    if data:
        resp["data"] = data
    if error:
        resp["error"] = error
    return resp


# =============================================================================
# PAGE LOADER EXECUTOR
# =============================================================================


async def execute_loader(loader, url: str) -> dict:
    log.info("Running loader: %s", loader.name)
    loader_data = {
        "name": f"loader:{loader.name}",
        "on_error": "stop",
        "steps": loader.steps,
    }

    async def _loader_dispatch(cmd: dict) -> dict:
        cmd = substitute_url(cmd, url)
        cmd["_from_loader"] = True
        return await dispatch_action(cmd)

    result = await run_script(loader_data, _loader_dispatch, stdout=io.StringIO())
    result.pop("_binary", None)
    return make_response(True, {"loader": loader.name, "url": url, "result": result})


# =============================================================================
# ACTION DISPATCH
# =============================================================================


async def dispatch_action(cmd: dict) -> dict:
    global _next_dialog_action, _active_page, _network_logging, _console_logging
    action = cmd.get("action", "")

    # ── No-page actions ──
    if action == "ping":
        url = browser.state.url if browser else ""
        return make_response(True, {"message": "pong", "url": url})

    if action == "close":
        log.info("Shutting down...")
        asyncio.get_event_loop().call_soon(lambda: sys.exit(0))
        return make_response(True, {"message": "closing"})

    if action == "sleep":
        duration = cmd.get("duration", 1)
        await asyncio.sleep(float(duration))
        return make_response(True, {"slept": duration})

    if action == "run_script":
        steps = cmd.get("steps")
        yaml_content = cmd.get("yaml")
        if yaml_content:
            script_data = yaml.safe_load(yaml_content)
            if not script_data or not isinstance(script_data, dict):
                return make_response(False, error="invalid YAML")
            if "steps" not in script_data:
                return make_response(False, error="YAML missing steps")
        elif steps:
            script_data = {
                "name": cmd.get("name", "api_script"),
                "on_error": cmd.get("on_error", "stop"),
                "steps": steps,
            }
        else:
            return make_response(False, error="steps or yaml required")
        result = await run_script(script_data, dispatch_action, stdout=io.StringIO())
        result.pop("_binary", None)
        return make_response(True, result)

    if action == "handle_dialog":
        _next_dialog_action = {
            "accept": cmd.get("accept", True),
            "text": cmd.get("text"),
        }
        return make_response(True, {"configured": _next_dialog_action})

    if action == "get_last_dialog":
        if not _last_dialog:
            return make_response(True, {"dialog": None})
        return make_response(True, {"dialog": _last_dialog})

    # ── Tab management ──
    if action == "list_tabs":
        ctx = browser._context if browser else None
        pages = ctx.pages if ctx else []
        tabs, active = [], get_active_page()
        for i, p in enumerate(pages):
            tabs.append({"index": i, "url": p.url, "active": p is active})
        return make_response(True, {"tabs": tabs, "count": len(tabs)})

    if action == "new_tab":
        ctx = browser._context if browser else None
        if not ctx:
            return make_response(False, error="No browser context")
        new_page = await ctx.new_page()
        _setup_page_handlers(new_page)
        _active_page = new_page
        tab_url: str | None = cmd.get("url")
        if tab_url:
            await new_page.goto(
                tab_url, wait_until=cmd.get("wait_until", "domcontentloaded")
            )
        return make_response(True, {"index": len(ctx.pages) - 1, "url": new_page.url})

    if action == "switch_tab":
        index = cmd.get("index")
        if index is None:
            return make_response(False, error="index required")
        ctx = browser._context if browser else None
        pages = ctx.pages if ctx else []
        if index < 0 or index >= len(pages):
            return make_response(False, error=f"Invalid tab index: {index}")
        _active_page = pages[index]
        return make_response(True, {"index": index, "url": _active_page.url})

    if action == "close_tab":
        index = cmd.get("index")
        ctx = browser._context if browser else None
        pages = ctx.pages if ctx else []
        if not pages:
            return make_response(False, error="No tabs open")
        if index is not None:
            if index < 0 or index >= len(pages):
                return make_response(False, error=f"Invalid tab index: {index}")
            target = pages[index]
        else:
            target = get_active_page() or pages[-1]
        await target.close()
        ctx2 = browser._context if browser else None
        pages2 = ctx2.pages if ctx2 else []
        _active_page = pages2[-1] if pages2 else None
        return make_response(True, {"closed": True, "remaining": len(pages2)})

    # ── Cookies ──
    if action == "get_cookies":
        ctx = browser._context if browser else None
        if not ctx:
            return make_response(False, error="No browser context")
        urls = cmd.get("urls")
        cookies = await ctx.cookies(urls)
        return make_response(True, {"cookies": cookies, "count": len(cookies)})

    if action == "set_cookie":
        ctx = browser._context if browser else None
        if not ctx:
            return make_response(False, error="No browser context")
        cookie = {k: v for k, v in cmd.items() if k != "action"}
        await ctx.add_cookies([cookie])
        return make_response(True, {"set": cookie.get("name")})

    if action == "delete_cookies":
        ctx = browser._context if browser else None
        if not ctx:
            return make_response(False, error="No browser context")
        await ctx.clear_cookies()
        return make_response(True, {"cleared": True})

    # ── Downloads ──
    if action == "get_last_download":
        return make_response(True, {"download": _last_download})

    # ── Network logging ──
    if action == "enable_network_log":
        _network_logging = True
        page = get_active_page()
        if page:
            _setup_page_handlers(page)
        return make_response(True, {"enabled": True})
    if action == "disable_network_log":
        _network_logging = False
        return make_response(True, {"enabled": False})
    if action == "get_network_log":
        return make_response(
            True, {"log": list(_network_log), "count": len(_network_log)}
        )
    if action == "clear_network_log":
        _network_log.clear()
        return make_response(True, {"cleared": True})
    if action == "getclear_network_log":
        result = make_response(
            True, {"log": list(_network_log), "count": len(_network_log)}
        )
        _network_log.clear()
        return result

    # ── Console logging ──
    if action == "enable_console_log":
        _console_logging = True
        page = get_active_page()
        if page:
            _setup_page_handlers(page)
        return make_response(True, {"enabled": True})
    if action == "disable_console_log":
        _console_logging = False
        return make_response(True, {"enabled": False})
    if action == "get_console_log":
        return make_response(
            True, {"log": list(_console_log), "count": len(_console_log)}
        )
    if action == "clear_console_log":
        _console_log.clear()
        return make_response(True, {"cleared": True})
    if action == "getclear_console_log":
        result = make_response(
            True, {"log": list(_console_log), "count": len(_console_log)}
        )
        _console_log.clear()
        return result

    # ── Save screenshot ──
    if action == "save_screenshot":
        ss_type = cmd.get("type", "browser")
        if ss_type == "desktop":
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
            scrot_result = subprocess.run(
                ["scrot", "-o", tmp_path], capture_output=True, text=True, check=False
            )
            if scrot_result.returncode != 0:
                os.unlink(tmp_path)
                return make_response(
                    False, error="scrot failed: %s" % scrot_result.stderr
                )
            with open(tmp_path, "rb") as f:
                data = f.read()
            os.unlink(tmp_path)
        else:
            page = get_active_page()
            if not page:
                return make_response(False, error="No active page")
            data = await page.screenshot(type="png")

        w = cmd.get("width")
        h = cmd.get("height")
        largest = cmd.get("whLargest")
        if w or h or largest:
            img = Image.open(io.BytesIO(data))
            orig_w, orig_h = img.size
            if largest:
                largest_int = int(largest)
                if orig_w >= orig_h:
                    new_w, new_h = largest_int, int(orig_h * largest_int / orig_w)
                else:
                    new_h, new_w = largest_int, int(orig_w * largest_int / orig_h)
            elif w and h:
                new_w, new_h = int(w), int(h)
            elif w:
                new_w_int = int(w)
                new_w, new_h = new_w_int, int(orig_h * new_w_int / orig_w)
            else:
                new_h_int = int(h)  # type: ignore[arg-type]
                new_h, new_w = new_h_int, int(orig_w * new_h_int / orig_h)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            data = buf.getvalue()

        path = cmd.get("path", "")
        if path:
            parent = os.path.dirname(os.path.abspath(path))
            os.makedirs(parent, exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)

        resp = make_response(True, {"type": ss_type, "size": len(data)})
        if path:
            resp["data"]["path"] = path
        resp["_binary"] = data
        return resp

    # ── Page-required actions ──
    page = get_active_page()
    if not page:
        return make_response(False, error="No active page")

    if action == "goto":
        url = cmd.get("url", "")
        if not url:
            return make_response(False, error="No URL")
        if not cmd.get("_from_loader"):
            loader = find_loader(loaders_dir, url)
            if loader:
                log.info("Loader matched: %s", loader.name)
                return await execute_loader(loader, url)
        goto_kwargs: dict[str, Any] = {
            "wait_until": cmd.get("wait_until", "domcontentloaded")
        }
        if cmd.get("referer"):
            goto_kwargs["referer"] = cmd["referer"]
        await page.goto(url, **goto_kwargs)
        return make_response(True, {"url": page.url, "title": await page.title()})

    if action == "refresh":
        await page.goto(page.url, wait_until=cmd.get("wait_until", "domcontentloaded"))
        return make_response(True, {"url": page.url, "title": await page.title()})

    if action == "click":
        selector = cmd.get("selector", "")
        if not selector:
            return make_response(False, error="No selector")
        await page.click(selector)
        await asyncio.sleep(0.5)
        return make_response(True, {"clicked": selector})

    if action == "mouse_move":
        x, y = cmd.get("x"), cmd.get("y")
        if x is None or y is None:
            return make_response(False, error="x,y required")
        system.move_mouse(int(x), int(y), cmd.get("duration"))
        return make_response(True, {"moved_to": {"x": x, "y": y}})

    if action == "mouse_click":
        x, y = cmd.get("x"), cmd.get("y")
        system.click(int(x) if x else None, int(y) if y else None)
        if x is None or y is None:
            return make_response(True, {"clicked_at": "current"})
        return make_response(True, {"clicked_at": {"x": x, "y": y}})

    if action == "system_click":
        x, y = cmd.get("x"), cmd.get("y")
        if x is None or y is None:
            return make_response(False, error="x,y required")
        system.move_mouse(int(x), int(y), cmd.get("duration"))
        system.click()
        return make_response(True, {"system_clicked": {"x": x, "y": y}})

    if action == "scroll":
        amount = cmd.get("amount", -3)
        x, y = cmd.get("x"), cmd.get("y")
        system.scroll(
            int(amount),
            int(x) if x is not None else None,
            int(y) if y is not None else None,
        )
        return make_response(True, {"scrolled": amount})

    if action == "scroll_to_bottom":
        delay = cmd.get("delay", 0.4)
        delay_ms = int(float(delay) * 1000)
        await page.evaluate(f"""(async () => {{
            let prev = -1;
            while (window.scrollY !== prev) {{
                prev = window.scrollY;
                window.scrollBy(0, window.innerHeight);
                await new Promise(r => setTimeout(r, {delay_ms}));
            }}
            window.scrollTo(0, 0);
        }})()""")
        return make_response(True, {"scrolled": "bottom"})

    if action == "scroll_to_bottom_humanized":
        min_clicks = int(cmd.get("min_clicks", 2))
        max_clicks = int(cmd.get("max_clicks", 6))
        delay = float(cmd.get("delay", 0.5))
        while True:
            prev = await page.evaluate("window.scrollY")
            clicks = random.randint(min_clicks, max_clicks)
            system.scroll(-clicks)
            jittered = delay * random.uniform(0.7, 1.3)
            await asyncio.sleep(jittered)
            curr = await page.evaluate("window.scrollY")
            if curr == prev:
                break
        await page.evaluate("window.scrollTo(0, 0)")
        return make_response(True, {"scrolled": "bottom_humanized"})

    if action == "calibrate":
        system.window_offset = await get_window_offset_js(page)
        return make_response(True, {"window_offset": system.window_offset})

    if action == "enter_fullscreen":
        is_fullscreen = await page.evaluate("!!document.fullscreenElement")
        if not is_fullscreen:
            await page.evaluate("document.documentElement.requestFullscreen()")
        return make_response(True, {"fullscreen": True, "changed": not is_fullscreen})

    if action == "exit_fullscreen":
        is_fullscreen = await page.evaluate("!!document.fullscreenElement")
        if is_fullscreen:
            await page.evaluate("document.exitFullscreen()")
        return make_response(True, {"fullscreen": False, "changed": is_fullscreen})

    if action == "get_resolution":
        result = system.get_resolution()
        return make_response(True, result)

    if action == "system_type":
        text = cmd.get("text", "")
        interval = cmd.get("interval", 0.08)
        if not text:
            return make_response(False, error="No text")
        system.system_type(text, interval)
        return make_response(True, {"typed_len": len(text)})

    if action == "send_key":
        key = cmd.get("key", "")
        if not key:
            return make_response(False, error="No key")
        system.send_key(key)
        return make_response(True, {"send_key": key})

    if action == "fill":
        selector, value = cmd.get("selector", ""), cmd.get("value", "")
        await page.fill(selector, value)
        return make_response(True, {"filled": selector})

    if action == "type":
        selector = cmd.get("selector", "")
        text = cmd.get("text", "")
        delay = cmd.get("delay", 0.05)
        await page.type(selector, text, delay=int(delay * 1000))
        return make_response(True, {"typed": selector})

    if action == "eval":
        expr = cmd.get("expression", "")
        result = await page.evaluate(expr)
        return make_response(True, {"result": result})

    if action == "get_interactive_elements":
        assert browser is not None
        visible_only = cmd.get("visible_only", True)
        browser._page = page
        elements = await browser.get_interactive_elements(visible_only)
        return make_response(True, {"elements": elements, "count": len(elements)})

    if action == "get_text":
        text = await page.evaluate("document.body ? document.body.innerText : ''")
        truncated = text[:10000]
        return make_response(
            True,
            {"text": truncated, "truncated": len(text) > 10000, "length": len(text)},
        )

    if action == "get_html":
        html = await page.evaluate("document.documentElement.outerHTML")
        return make_response(True, {"html": html, "length": len(html)})

    if action == "wait_for_element":
        selector = cmd.get("selector", "")
        state = cmd.get("state", "visible")
        timeout = cmd.get("timeout", 30000)
        await page.wait_for_selector(selector, state=state, timeout=timeout)
        return make_response(True, {"selector": selector, "found": True})

    if action == "wait_for_text":
        text = cmd.get("text", "")
        timeout = cmd.get("timeout", 30000)
        await page.wait_for_function(
            f"document.body && document.body.innerText.includes({text!r})",
            timeout=timeout,
        )
        return make_response(True, {"text": text, "found": True})

    if action == "wait_for_url":
        url = cmd.get("url", "")
        timeout = cmd.get("timeout", 30000)
        await page.wait_for_url(url, timeout=timeout)
        return make_response(True, {"url": page.url})

    if action == "wait_for_network_idle":
        timeout = cmd.get("timeout", 30000)
        await page.wait_for_load_state("networkidle", timeout=timeout)
        return make_response(True, {"state": "networkidle"})

    if action == "get_storage":
        storage_type = cmd.get("type", "local")
        expr = (
            "JSON.stringify(localStorage)"
            if storage_type == "local"
            else "JSON.stringify(sessionStorage)"
        )
        raw: Any = await page.evaluate(expr)
        storage_data: dict[str, Any] = yaml.safe_load(raw) if raw else {}  # type: ignore[assignment]
        return make_response(True, {"storage": storage_data, "type": storage_type})

    if action == "set_storage":
        storage_type = cmd.get("type", "local")
        key = cmd.get("key", "")
        value = cmd.get("value", "")
        ns = "localStorage" if storage_type == "local" else "sessionStorage"
        await page.evaluate(f"{ns}.setItem({key!r}, {value!r})")
        return make_response(True, {"set": key})

    if action == "clear_storage":
        storage_type = cmd.get("type", "local")
        ns = "localStorage" if storage_type == "local" else "sessionStorage"
        await page.evaluate(f"{ns}.clear()")
        return make_response(True, {"cleared": storage_type})

    if action == "upload_file":
        selector = cmd.get("selector", "")
        file_path = cmd.get("file_path", "")
        if not selector or not file_path:
            return make_response(False, error="selector and file_path required")
        await page.set_input_files(selector, file_path)
        return make_response(True, {"uploaded": file_path})

    return make_response(False, error=f"Unknown action: {action}")


# =============================================================================
# FASTAPI APP
# =============================================================================

_request_lock = asyncio.Lock()


# =============================================================================
# MCP INTEGRATION — Streamable HTTP (MCP only, no HTTP API)
# =============================================================================

from mcp_server import mcp, set_dispatcher

set_dispatcher(dispatch_action, _request_lock)

# Build the MCP Starlette app and mount it at root so its internal `/mcp`
# route is reachable at `POST /mcp`. Since the MCP app only has a `/mcp`
# route, all other paths naturally return 404.
mcp_http_app = mcp.http_app(transport="streamable-http")
app = FastAPI(
    title="CodeFreedom Camoufox",
    version="0.1.0",
    lifespan=mcp_http_app.lifespan,
    redirect_slashes=False,
)
app.mount("/", mcp_http_app)

# =============================================================================
# ENTRY POINT
# =============================================================================


async def main() -> None:
    global browser
    system.init()
    log.info("Starting CodeFreedom Camoufox browser...")
    browser = Browser()
    await browser.start()
    log.info("Browser ready")

    if SCRIPT_PATH:
        log.info("Script mode: %s", SCRIPT_PATH)
        try:
            script_data = load_script(SCRIPT_PATH)
            await run_script(script_data, dispatch_action)
            sys.exit(0)
        except (OSError, ValueError, RuntimeError) as e:
            log.error("Script failed: %s", e)
            sys.exit(1)

    config = uvicorn.Config(
        app,
        host=HTTP_LISTEN_HOST,
        port=HTTP_LISTEN_PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
