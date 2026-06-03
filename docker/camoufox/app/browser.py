"""Stealth browser module using Camoufox."""

# pylint: disable=broad-exception-caught

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse as _urlparse

# Path to JS files
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Default user data directory
DEFAULT_USER_DATA_DIR = "/userdata"

# Persisted browser properties file
BROWSER_PROPS_FILE = Path(DEFAULT_USER_DATA_DIR) / "codefreedom-camoufox-props.json"


def _get_default_viewport() -> tuple[int, int]:
    xvfb_res = os.environ.get("XVFB_RESOLUTION", "1920x1080")
    parts = xvfb_res.split("x")
    width = int(parts[0]) if parts else 1920
    height = int(parts[1]) if len(parts) > 1 else 1080
    return width, height


def _load_persisted_config() -> dict[str, Any] | None:
    if not BROWSER_PROPS_FILE.exists():
        return None
    try:
        with open(BROWSER_PROPS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_config(config: dict[str, Any]) -> None:
    BROWSER_PROPS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(BROWSER_PROPS_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def _update_config_screen(config: dict[str, Any], width: int, height: int) -> None:
    config["screen.width"] = width
    config["screen.height"] = height
    config["screen.availWidth"] = width
    config["screen.availHeight"] = height
    config["window.outerWidth"] = width
    config["window.outerHeight"] = height
    config["window.innerWidth"] = width
    config["window.innerHeight"] = height - 80
    config["window.screenX"] = 0
    config["window.screenY"] = 0
    config["screen.availLeft"] = 0
    config["screen.availTop"] = 0


def _generate_camoufox_config(screen_width: int, screen_height: int) -> dict[str, Any]:
    from browserforge.fingerprints import FingerprintGenerator
    from camoufox.fingerprints import from_browserforge
    from camoufox.pkgman import installed_verstr

    fp_gen = FingerprintGenerator(browser="firefox", os="linux")
    fp = fp_gen.generate()

    fp.screen.width = screen_width
    fp.screen.height = screen_height
    fp.screen.availWidth = screen_width
    fp.screen.availHeight = screen_height
    fp.screen.outerWidth = screen_width
    fp.screen.outerHeight = screen_height
    fp.screen.innerWidth = screen_width
    fp.screen.innerHeight = screen_height - 80
    fp.screen.screenX = 0
    fp.screen.availTop = 0
    fp.screen.availLeft = 0

    ff_version = installed_verstr().split(".", 1)[0]
    return from_browserforge(fp, ff_version)


class BrowserError(Exception):
    """Browser error."""


@dataclass
class BrowserState:
    url: str = ""
    title: str = ""
    content: str = ""
    screenshot_b64: str = ""


@dataclass
class BrowserConfig:
    timeout: float = 30.0


class Browser:
    """Stealth browser using Camoufox (Firefox-based, no CDP)."""

    def __init__(self, config: BrowserConfig | None = None) -> None:
        self.config = config or BrowserConfig()
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._state = BrowserState()

    @property
    def state(self) -> BrowserState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._browser is not None

    @property
    def page(self) -> Any:
        return self._page

    async def start(self) -> None:
        if self.is_running:
            return
        await self._launch_browser()

    async def stop(self) -> None:
        if self._page:
            try:
                await self._page.close()
            except Exception:
                pass
            self._page = None

        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None

        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

        self._state = BrowserState()

    async def goto(self, url: str, wait_until: str = "networkidle") -> BrowserState:
        if not self.is_running:
            await self.start()
        page = await self._get_page()
        timeout_ms = int(self.config.timeout * 1000)
        await page.goto(url, timeout=timeout_ms, wait_until=wait_until)
        await self._update_state()
        return self._state

    async def screenshot(self, full_page: bool = False, quality: int = 80) -> str:
        if not self._page:
            return ""
        try:
            data = await self._page.screenshot(
                type="jpeg", quality=quality, full_page=full_page
            )
            b64 = base64.b64encode(data).decode()
            self._state.screenshot_b64 = b64
            return b64
        except Exception:
            return ""

    async def refresh(self) -> BrowserState:
        if not self._page:
            return self._state
        await self._page.reload()
        await self._update_state()
        return self._state

    async def back(self) -> BrowserState:
        if not self._page:
            return self._state
        await self._page.go_back()
        await self._update_state()
        return self._state

    async def forward(self) -> BrowserState:
        if not self._page:
            return self._state
        await self._page.go_forward()
        await self._update_state()
        return self._state

    async def click(self, selector: str) -> None:
        if not self._page:
            return
        await self._page.click(selector)
        await self._update_state()

    async def fill(self, selector: str, value: str) -> None:
        if not self._page:
            return
        await self._page.fill(selector, value)

    async def type(self, selector: str, text: str, delay: float = 0.05) -> None:
        if not self._page:
            return
        await self._page.type(selector, text, delay=int(delay * 1000))

    async def wait_for(self, selector: str, state: str = "visible") -> None:
        if not self._page:
            return
        timeout_ms = int(self.config.timeout * 1000)
        await self._page.wait_for_selector(selector, state=state, timeout=timeout_ms)

    async def evaluate(self, expression: str) -> Any:
        if not self._page:
            return None
        return await self._page.evaluate(expression)

    async def get_interactive_elements(self, visible_only: bool = True) -> list[dict]:
        if not self._page:
            return []
        js_path = os.path.join(_SCRIPT_DIR, "get_elements.js")
        with open(js_path, encoding="utf-8") as f:
            js_code = f.read()
        return await self._page.evaluate(js_code, visible_only)

    async def _launch_browser(self) -> None:
        from browserforge.fingerprints import Screen
        from camoufox.utils import launch_options
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        width, height = _get_default_viewport()

        config = _load_persisted_config()
        if config is None:
            config = _generate_camoufox_config(width, height)
        else:
            _update_config_screen(config, width, height)
        _save_config(config)

        locale = os.environ.get("LANG", "en_US.UTF-8").split(".")[0].replace("_", "-")
        if locale == "C" or not locale:
            locale = "en-US"

        timezone_id = os.environ.get("TZ")

        try:
            screen = Screen(
                min_width=1024, max_width=1920, min_height=768, max_height=1080
            )
            opts = launch_options(
                config=config,
                screen=screen,
                os="linux",
                headless=False,
                locale=locale,
                humanize=True,
                i_know_what_im_doing=True,
            )

            opts["user_data_dir"] = DEFAULT_USER_DATA_DIR

            use_viewport = os.environ.get("USE_VIEWPORT", "").lower() == "true"
            if use_viewport:
                opts["viewport"] = {"width": width, "height": height}
            else:
                opts["no_viewport"] = True

            if timezone_id and timezone_id != "UTC":
                opts["timezone_id"] = timezone_id

            proxy_url = os.environ.get("PROXY_URL", "")
            if proxy_url:
                p = _urlparse(proxy_url)
                proxy: dict[str, str] = {
                    "server": f"{p.scheme}://{p.hostname}:{p.port}"
                }
                if p.username:
                    proxy["username"] = p.username
                if p.password:
                    proxy["password"] = p.password
                opts["proxy"] = proxy

            opts["accept_downloads"] = True

            self._context = await self._playwright.firefox.launch_persistent_context(
                **opts
            )
            self._browser = self._context

            await asyncio.sleep(1)
            result = subprocess.run(
                ["xdotool", "search", "--onlyvisible", "--name", "Camoufox"],
                capture_output=True,
                text=True,
                check=False,
            )
            for wid in result.stdout.strip().split("\n"):
                if not wid:
                    continue
                subprocess.run(["xdotool", "windowmove", wid, "0", "0"], check=False)
                subprocess.run(
                    ["xdotool", "windowsize", wid, str(width), str(height)], check=False
                )
        except Exception as e:
            await self.stop()
            raise BrowserError(f"Failed to launch browser: {e}") from e

    async def _get_page(self) -> Any:
        if self._page:
            return self._page
        pages = self._context.pages
        if pages:
            self._page = pages[0]
            return self._page
        self._page = await self._context.new_page()
        return self._page

    async def _update_state(self) -> None:
        if not self._page:
            return
        try:
            self._state.url = self._page.url
            self._state.title = await self._page.title()
            self._state.content = await self._page.inner_text("body")
        except Exception:
            pass

    async def __aenter__(self) -> "Browser":
        await self.start()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.stop()
