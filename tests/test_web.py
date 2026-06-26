"""Tests for web tool CLI — restart action and run() dispatch."""

import argparse

import pytest

from tests.helpers import ToolRestartMixin, ToolRunDispatchMixin

pytestmark = pytest.mark.integration


def _settings(**overrides) -> dict:
    """Build a web settings dict for tests."""
    base = {
        "image": "codefreedom:web",
        "container_name": "codefreedom-web",
        "port": 8420,
        "data_dir": "~/.codefreedom/tools/web",
        "env": {},
        "search_engines": {},
        "parser_registry": {},
    }
    base.update(overrides)
    return base


class TestRestart(ToolRestartMixin):
    """Tests for the restart() function."""

    tool_module_path = "codefreedom.tools.web"
    settings_factory = staticmethod(_settings)
    expected_container_name = "codefreedom-web"


class TestRunDispatch(ToolRunDispatchMixin):
    """Tests for run() dispatching the 'restart' action."""

    tool_module_path = "codefreedom.tools.web"
    settings_factory = staticmethod(_settings)
    expected_container_name = "codefreedom-web"
    default_port = 8420

    @pytest.mark.parametrize("action", ["start", "stop", "status"])
    def test_run_other_actions_still_work(self, monkeypatch, action):
        """Adding restart must not break dispatch of other actions."""
        called: list[str] = []

        def make_fake(name):
            def fake(settings):
                called.append(name)
                return 0

            return fake

        from codefreedom.tools.web import run

        monkeypatch.setattr("codefreedom.tools.web._load_profile", _settings)
        monkeypatch.setattr("codefreedom.tools.web.start", make_fake("start"))
        monkeypatch.setattr("codefreedom.tools.web.stop", make_fake("stop"))
        monkeypatch.setattr("codefreedom.tools.web.status", make_fake("status"))

        args = argparse.Namespace(action=action, port=8420)
        result = run(args)
        assert result == 0
        assert called == [action]
