"""Tests for web tool CLI — restart action and run() dispatch."""

import argparse

import pytest

from codefreedom.tools.web import restart, run


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


class TestRestart:
    """Tests for the restart() function."""

    def test_restart_existing_container(self, monkeypatch):
        """restart() calls `docker restart <name>` when container exists."""
        calls: list[list[str]] = []

        def fake_run(cmd, *args, **kwargs):
            calls.append(cmd)

            class _R:
                returncode = 0
                stderr = ""

            return _R()

        monkeypatch.setattr("codefreedom.cli.docker_utils.container_exists", lambda name: True)
        monkeypatch.setattr("codefreedom.cli.docker_utils.subprocess.run", fake_run)

        result = restart(_settings(container_name="my-web"))
        assert result == 0
        assert len(calls) == 1
        assert calls[0] == ["docker", "restart", "my-web"]

    def test_restart_missing_container_returns_1(self, monkeypatch):
        """restart() returns 1 and does not call docker when container is absent."""
        calls: list[list[str]] = []

        def fake_run(cmd, *args, **kwargs):
            calls.append(cmd)
            raise AssertionError("subprocess.run should not be called")

        monkeypatch.setattr("codefreedom.cli.docker_utils.container_exists", lambda name: False)
        monkeypatch.setattr("codefreedom.cli.docker_utils.subprocess.run", fake_run)

        result = restart(_settings())
        assert result == 1
        assert calls == []

    def test_restart_docker_failure_propagates(self, monkeypatch):
        """restart() returns 1 when docker restart returns non-zero."""

        def fake_run(cmd, *args, **kwargs):
            class _R:
                returncode = 1
                stderr = "docker error: container not found"

            return _R()

        monkeypatch.setattr("codefreedom.cli.docker_utils.container_exists", lambda name: True)
        monkeypatch.setattr("codefreedom.cli.docker_utils.subprocess.run", fake_run)

        result = restart(_settings())
        assert result == 1

    def test_restart_does_not_remove_container(self, monkeypatch):
        """restart() must NOT call `docker rm` — only `docker restart`."""
        calls: list[list[str]] = []

        def fake_run(cmd, *args, **kwargs):
            calls.append(cmd)

            class _R:
                returncode = 0
                stderr = ""

            return _R()

        monkeypatch.setattr("codefreedom.cli.docker_utils.container_exists", lambda name: True)
        monkeypatch.setattr("codefreedom.cli.docker_utils.subprocess.run", fake_run)

        restart(_settings())
        # Exactly one subprocess call, and it must be `docker restart`
        assert len(calls) == 1
        assert "rm" not in calls[0]
        assert "stop" not in calls[0]
        assert calls[0] == ["docker", "restart", "codefreedom-web"]


class TestRunDispatch:
    """Tests for run() dispatching the 'restart' action."""

    def test_run_dispatches_restart_to_restart_function(self, monkeypatch):
        """run(action='restart') must call the restart() function."""
        called = []

        def fake_restart(settings):
            called.append(settings)
            return 0

        monkeypatch.setattr("codefreedom.tools.web._load_profile", _settings)
        monkeypatch.setattr("codefreedom.tools.web.restart", fake_restart)

        args = argparse.Namespace(action="restart", port=8420)
        result = run(args)
        assert result == 0
        assert len(called) == 1
        assert called[0]["container_name"] == "codefreedom-web"

    def test_run_restart_does_not_load_profile_from_disk(self, monkeypatch):
        """run(action='restart') must not require profile to exist on disk.

        The profile loader falls back to defaults if the file is missing,
        so restart should work even without a prior `init`.
        """
        monkeypatch.setattr("codefreedom.tools.web._load_profile", lambda: _settings())
        monkeypatch.setattr(
            "codefreedom.tools.web.restart",
            lambda settings: 0,
        )

        args = argparse.Namespace(action="restart", port=8420)
        result = run(args)
        assert result == 0

    @pytest.mark.parametrize("action", ["start", "stop", "status"])
    def test_run_other_actions_still_work(self, monkeypatch, action):
        """Adding restart must not break dispatch of other actions."""
        called: list[str] = []

        def make_fake(name):
            def fake(settings):
                called.append(name)
                return 0

            return fake

        monkeypatch.setattr("codefreedom.tools.web._load_profile", _settings)
        monkeypatch.setattr("codefreedom.tools.web.start", make_fake("start"))
        monkeypatch.setattr("codefreedom.tools.web.stop", make_fake("stop"))
        monkeypatch.setattr("codefreedom.tools.web.status", make_fake("status"))

        args = argparse.Namespace(action=action, port=8420)
        result = run(args)
        assert result == 0
        assert called == [action]
pytestmark = pytest.mark.integration
