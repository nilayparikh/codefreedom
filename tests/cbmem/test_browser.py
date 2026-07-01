"""Tests for ``codebase_memory.browser`` — never raises, returns bool."""
from __future__ import annotations

from unittest.mock import patch

from codebase_memory import browser


class TestOpenUi:

    def test_returns_true_when_webbrowser_succeeds(self):
        with patch("codebase_memory.browser.webbrowser.open", return_value=True):
            assert browser.open_ui("http://127.0.0.1:9749/") is True

    def test_returns_false_when_webbrowser_returns_false(self):
        with patch("codebase_memory.browser.webbrowser.open", return_value=False):
            assert browser.open_ui("http://127.0.0.1:9749/") is False

    def test_returns_false_when_webbrowser_raises(self):
        def boom(*_a, **_k):
            raise RuntimeError("no browser installed")

        with patch("codebase_memory.browser.webbrowser.open", boom):
            assert browser.open_ui("http://127.0.0.1:9749/") is False

    def test_returns_false_on_os_error(self):
        with patch("codebase_memory.browser.webbrowser.open", side_effect=OSError("no display")):
            assert browser.open_ui("http://127.0.0.1:9749/") is False

    def test_passes_url_unchanged(self):
        with patch("codebase_memory.browser.webbrowser.open", return_value=True) as mock:
            browser.open_ui("http://example.com/x?y=1")
        assert mock.call_args.args[0] == "http://example.com/x?y=1"

    def test_uses_new_tab_argument(self):
        """new=2 opens in a new tab when a browser is already open."""
        with patch("codebase_memory.browser.webbrowser.open", return_value=True) as mock:
            browser.open_ui("http://127.0.0.1:9749/")
        assert mock.call_args.kwargs.get("new") == 2


class TestSafeUrl:
    def test_default_path(self):
        assert browser.safe_url("127.0.0.1", 8330) == "http://127.0.0.1:8330/"

    def test_custom_path(self):
        assert browser.safe_url("127.0.0.1", 9749, "/index.html") == "http://127.0.0.1:9749/index.html"
