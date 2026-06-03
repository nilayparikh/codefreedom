"""System-level input using PyAutoGUI."""

from __future__ import annotations

import os
import random
import time


def _get_default_resolution() -> tuple[int, int]:
    """Get default resolution from XVFB_RESOLUTION env var (WxH format)."""
    xvfb_res = os.environ.get("XVFB_RESOLUTION", "1920x1080")
    parts = xvfb_res.split("x")
    width = int(parts[0]) if parts else 1920
    height = int(parts[1]) if len(parts) > 1 else 1080
    return width, height


class System:
    """System-level mouse and keyboard input via PyAutoGUI."""

    def __init__(self) -> None:
        self._pyautogui = None
        self._window_offset = {"x": 0, "y": 0}

    @property
    def is_ready(self) -> bool:
        return self._pyautogui is not None

    @property
    def window_offset(self) -> dict:
        return self._window_offset

    @window_offset.setter
    def window_offset(self, value: dict) -> None:
        self._window_offset = value

    def init(self) -> None:
        if self._pyautogui is not None:
            return
        xauth_path = os.path.expanduser("~/.Xauthority")
        if not os.path.exists(xauth_path):
            open(xauth_path, "a", encoding="utf-8").close()
        os.environ.setdefault("XAUTHORITY", xauth_path)
        import pyautogui

        pyautogui.FAILSAFE = False
        pyautogui.PAUSE = 0
        self._pyautogui = pyautogui

    def screen_coords(self, x: int, y: int) -> tuple[int, int]:
        return (x + self._window_offset["x"], y + self._window_offset["y"])

    def move_mouse(self, x: int, y: int, duration: float | None = None) -> None:
        if not self._pyautogui:
            return
        if duration is None:
            duration = random.uniform(0.2, 0.6)
        screen_x, screen_y = self.screen_coords(x, y)
        jitter = random.randint(-3, 3)
        target_x, target_y = screen_x + jitter, screen_y + jitter
        current_x, current_y = self._pyautogui.position()
        distance = ((target_x - current_x) ** 2 + (target_y - current_y) ** 2) ** 0.5
        steps = max(int(distance / 50), 10)
        for i in range(steps + 1):
            t = 1 - (1 - i / steps) ** 2
            jx = random.uniform(-1, 1) if i < steps else 0
            jy = random.uniform(-1, 1) if i < steps else 0
            new_x = current_x + (target_x - current_x) * t + jx
            new_y = current_y + (target_y - current_y) * t + jy
            self._pyautogui.moveTo(int(new_x), int(new_y), duration=0)
            time.sleep(duration / steps)

    def click(self, x: int | None = None, y: int | None = None) -> None:
        if not self._pyautogui:
            return
        if x is None or y is None:
            self._pyautogui.click()
            return
        sx, sy = self.screen_coords(x, y)
        self._pyautogui.click(sx, sy)

    def scroll(self, amount: int, x: int | None = None, y: int | None = None) -> None:
        if not self._pyautogui:
            return
        if x is not None and y is not None:
            self.move_mouse(x, y)
        self._pyautogui.scroll(amount)

    def send_key(self, key: str) -> None:
        if not self._pyautogui:
            return
        if "+" in key:
            keys = key.split("+")
            self._pyautogui.hotkey(*keys)
            return
        self._pyautogui.press(key)

    def system_type(self, text: str, interval: float = 0.08) -> None:
        if not self._pyautogui:
            return
        for char in text:
            if len(char) == 1:
                self._pyautogui.press(char)
            else:
                self._pyautogui.typewrite(char)
            time.sleep(max(0.02, interval + random.uniform(-0.03, 0.05)))

    def get_resolution(self) -> dict:
        w, h = _get_default_resolution()
        return {"width": w, "height": h}
