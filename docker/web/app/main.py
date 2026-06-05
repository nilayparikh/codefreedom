#!/usr/bin/env python3
# pylint: disable=global-statement,broad-exception-caught,protected-access
"""
CodeFreedom Camoufox — Stealth browser with MCP-only server (Streamable HTTP).

Endpoints:
    POST/GET /mcp  — MCP Streamable HTTP (web_search, web_fetch)
"""

from __future__ import annotations

import asyncio
import io
import os
import subprocess
import sys
import tempfile
import time
from typing import Any

import uvicorn
import yaml
from browser import Browser
from fastapi import FastAPI
from PIL import Image
from script_runner import load_script, run_script
from logger import get_logger

log = get_logger(__name__)


def make_response(
    success: bool, data: dict | None = None, error: str | None = None
) -> dict:
    resp: dict = {"success": success, "timestamp": time.time()}
    if data:
        resp["data"] = data
    if error:
        resp["error"] = error
    return resp


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


browser: Browser | None = None
_active_page: Any = None

HTTP_LISTEN_HOST = os.environ.get("HTTP_LISTEN_HOST", "0.0.0.0")
HTTP_LISTEN_PORT = int(os.environ.get("HTTP_LISTEN_PORT", "8420"))

SCRIPT_PATH: str | None = None
_args = sys.argv[1:]
if len(_args) >= 2 and _args[0] == "--script":
    SCRIPT_PATH = _args[1]


_BROWSER_CONNECTION_ERRORS = (
    "Connection closed",
    "Target closed",
    "Browser closed",
    "Protocol error",
)


def _is_connection_error(error: Exception) -> bool:
    """Check if an error indicates the browser connection is dead."""
    msg = str(error)
    return any(marker in msg for marker in _BROWSER_CONNECTION_ERRORS)


_recovery_failures: int = 0
_MAX_RECOVERY_ATTEMPTS: int = 3


async def _recover_browser() -> bool:
    """Attempt to restart the browser after a connection failure.

    Returns True if the browser was successfully restarted.  After
    ``_MAX_RECOVERY_ATTEMPTS`` consecutive failures the browser is left
    stopped and the caller should signal the container to restart.
    """
    global _active_page, _recovery_failures
    if not browser:
        return False

    _recovery_failures += 1
    if _recovery_failures > _MAX_RECOVERY_ATTEMPTS:
        log.error(
            "Browser recovery failed %d times — giving up. "
            "Restart the container to recover.",
            _MAX_RECOVERY_ATTEMPTS,
        )
        return False

    log.warning(
        "Browser connection lost, attempting restart (attempt %d/%d)...",
        _recovery_failures,
        _MAX_RECOVERY_ATTEMPTS,
    )
    try:
        await browser.stop()
    except Exception as exc:
        log.warning("Error stopping crashed browser: %s", exc)
    _active_page = None
    try:
        await browser.start()
        log.info("Browser restarted successfully")
        _recovery_failures = 0
        return True
    except Exception as exc:
        log.error("Failed to restart browser: %s", exc)
        return False


async def dispatch_action(cmd: dict) -> dict:
    action = cmd.get("action", "")

    try:
        return await _dispatch_action_inner(cmd, action)
    except Exception as exc:
        if _is_connection_error(exc):
            recovered = await _recover_browser()
            if recovered:
                return make_response(
                    False, error=f"Browser connection lost (recovered): {exc}"
                )
            return make_response(
                False, error=f"Browser connection lost (restart failed): {exc}"
            )
        # Don't eat arbitrary exceptions — only connection errors get the
        # auto-recovery path.  Everything else (programming errors,
        # type errors, etc.) propagates to the MCP caller.
        raise


async def _dispatch_action_inner(cmd: dict, action: str) -> dict:
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

    if action == "delete_cookies":
        ctx = browser._context if browser else None
        if not ctx:
            return make_response(False, error="No browser context")
        await ctx.clear_cookies()
        return make_response(True, {"cleared": True})

    if action == "restart_browser":
        # Periodic housekeeping triggered by mcp_server after N searches.
        # Stops the persistent context, then starts a fresh one. This releases
        # all accumulated rendered DOMs, cookies, network cache, and JS heap.
        if not browser:
            return make_response(False, error="No browser instance")
        global _active_page
        try:
            await browser.stop()
        except Exception as exc:
            log.warning("Error stopping browser for restart: %s", exc)
        _active_page = None
        try:
            await browser.start()
            return make_response(True, {"restarted": True})
        except Exception as exc:
            return make_response(False, error=f"Failed to restart browser: {exc}")

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
            elif h is not None:
                new_h_int = int(h)
                new_h, new_w = new_h_int, int(orig_w * new_h_int / orig_h)
            else:
                new_w, new_h = orig_w, orig_h
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

    page = get_active_page()
    if not page:
        return make_response(False, error="No active page")

    if action == "goto":
        url = cmd.get("url", "")
        if not url:
            return make_response(False, error="No URL")
        try:
            await page.goto(
                url,
                wait_until=cmd.get("wait_until", "domcontentloaded"),
                timeout=cmd.get("timeout", 15000),
            )
        except Exception as e:
            return make_response(False, error=f"Navigation failed: {e}")
        return make_response(True, {"url": page.url, "title": await page.title()})

    if action == "eval":
        expr = cmd.get("expression", "")
        result = await page.evaluate(expr)
        return make_response(True, {"result": result})

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

    if action == "wait_for_network_idle":
        timeout = cmd.get("timeout", 15000)
        try:
            await page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception as e:
            return make_response(False, error=f"Network idle timeout: {e}")
        return make_response(True, {"state": "networkidle"})

    return make_response(False, error=f"Unknown action: {action}")


_request_lock = asyncio.Lock()

from mcp_server import mcp, set_dispatcher  # noqa: E402

set_dispatcher(dispatch_action, _request_lock)

mcp_http_app = mcp.http_app(transport="streamable-http")

from starlette.responses import JSONResponse  # noqa: E402


async def _oauth_metadata(_request):
    return JSONResponse({"issuer": None}, status_code=200)


mcp_http_app.add_route(
    "/.well-known/oauth-authorization-server",
    _oauth_metadata,
    methods=["GET"],
)

app = FastAPI(
    title="CodeFreedom Camoufox",
    version="0.1.0",
    lifespan=mcp_http_app.lifespan,
    redirect_slashes=False,
)
app.mount("/", mcp_http_app)


async def main() -> None:
    global browser
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
