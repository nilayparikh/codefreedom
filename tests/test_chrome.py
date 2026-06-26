"""Tests for chrome tool CLI — restart action and run() dispatch."""

import argparse

import pytest

from tests.helpers import ToolRestartMixin, ToolRunDispatchMixin

pytestmark = pytest.mark.integration


def _settings(**overrides) -> dict:
    """Build a chrome settings dict for tests."""
    base = {
        "image": "codefreedom:chrome",
        "container_name": "codefreedom-chrome",
        "port": 9222,
        "data_dir": "~/.codefreedom/tools/chrome",
        "env": {},
    }
    base.update(overrides)
    return base


class TestRestart(ToolRestartMixin):
    """Tests for the restart() function."""

    tool_module_path = "codefreedom.tools.chrome"
    settings_factory = staticmethod(_settings)
    expected_container_name = "codefreedom-chrome"


class TestRunDispatch(ToolRunDispatchMixin):
    """Tests for run() dispatching the 'restart' action."""

    tool_module_path = "codefreedom.tools.chrome"
    settings_factory = staticmethod(_settings)
    expected_container_name = "codefreedom-chrome"
    default_port = 9222

    @pytest.mark.parametrize("action", ["start", "stop", "status", "url"])
    def test_run_other_actions_still_work(self, monkeypatch, action):
        """Adding restart must not break dispatch of other actions."""
        called: list[str] = []

        def make_fake(name):
            def fake(settings):
                called.append(name)
                return 0

            return fake

        from codefreedom.tools.chrome import run

        monkeypatch.setattr("codefreedom.tools.chrome._load_profile", _settings)
        monkeypatch.setattr("codefreedom.tools.chrome.start", make_fake("start"))
        monkeypatch.setattr("codefreedom.tools.chrome.stop", make_fake("stop"))
        monkeypatch.setattr("codefreedom.tools.chrome.status", make_fake("status"))
        monkeypatch.setattr("codefreedom.tools.chrome.url", make_fake("url"))

        args = argparse.Namespace(action=action, port=9222)
        result = run(args)
        assert result == 0
        assert called == [action]
