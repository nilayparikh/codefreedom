"""Tests for chrome tool CLI — restart action and run() dispatch."""

import argparse

import pytest

from codefreedom.cli.chrome import restart, run


def _settings(**overrides) -> dict:
    """Build a chrome settings dict for tests."""
    base = {
        "image": "codefreedom:chrome",
        "container_name": "codefreedom-chrome",
        "port": 9222,
        "data_dir": "~/.codefreedom/sandbox/tools/chrome",
        "env": {},
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

        monkeypatch.setattr(
            "codefreedom.cli.docker_utils.container_exists", lambda name: True
        )
        monkeypatch.setattr("codefreedom.cli.docker_utils.subprocess.run", fake_run)

        result = restart(_settings(container_name="my-chrome"))
        assert result == 0
        assert len(calls) == 1
        assert calls[0] == ["docker", "restart", "my-chrome"]

    def test_restart_missing_container_returns_1(self, monkeypatch):
        """restart() returns 1 and does not call docker when container is absent."""
        calls: list[list[str]] = []

        def fake_run(cmd, *args, **kwargs):
            calls.append(cmd)
            raise AssertionError("subprocess.run should not be called")

        monkeypatch.setattr(
            "codefreedom.cli.docker_utils.container_exists", lambda name: False
        )
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

        monkeypatch.setattr(
            "codefreedom.cli.docker_utils.container_exists", lambda name: True
        )
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

        monkeypatch.setattr(
            "codefreedom.cli.docker_utils.container_exists", lambda name: True
        )
        monkeypatch.setattr("codefreedom.cli.docker_utils.subprocess.run", fake_run)

        restart(_settings())
        # Exactly one subprocess call, and it must be `docker restart`
        assert len(calls) == 1
        assert "rm" not in calls[0]
        assert "stop" not in calls[0]
        assert calls[0] == ["docker", "restart", "codefreedom-chrome"]


class TestRunDispatch:
    """Tests for run() dispatching the 'restart' action."""

    def test_run_dispatches_restart_to_restart_function(self, monkeypatch):
        """run(action='restart') must call the restart() function."""
        called = []

        def fake_restart(settings):
            called.append(settings)
            return 0

        # Bypass profile loading — return a minimal settings dict
        monkeypatch.setattr("codefreedom.cli.chrome._load_profile", _settings)
        monkeypatch.setattr("codefreedom.cli.chrome.restart", fake_restart)

        args = argparse.Namespace(action="restart", port=9222)
        result = run(args)
        assert result == 0
        assert len(called) == 1
        assert called[0]["container_name"] == "codefreedom-chrome"

    def test_run_restart_does_not_load_profile_from_disk(self, monkeypatch):
        """run(action='restart') must not require profile to exist on disk.

        The profile loader falls back to defaults if the file is missing,
        so restart should work even without a prior `init`.
        """

        def fake_load():
            return _settings()

        monkeypatch.setattr("codefreedom.cli.chrome._load_profile", fake_load)
        monkeypatch.setattr(
            "codefreedom.cli.chrome.restart",
            lambda settings: 0,
        )

        args = argparse.Namespace(action="restart", port=9222)
        result = run(args)
        assert result == 0

    @pytest.mark.parametrize("action", ["start", "stop", "status", "url"])
    def test_run_other_actions_still_work(self, monkeypatch, action):
        """Adding restart must not break dispatch of other actions."""
        called: list[str] = []

        def make_fake(name):
            def fake(settings):
                called.append(name)
                return 0

            return fake

        monkeypatch.setattr("codefreedom.cli.chrome._load_profile", _settings)
        monkeypatch.setattr("codefreedom.cli.chrome.start", make_fake("start"))
        monkeypatch.setattr("codefreedom.cli.chrome.stop", make_fake("stop"))
        monkeypatch.setattr("codefreedom.cli.chrome.status", make_fake("status"))
        monkeypatch.setattr("codefreedom.cli.chrome.url", make_fake("url"))

        args = argparse.Namespace(action=action, port=9222)
        result = run(args)
        assert result == 0
        assert called == [action]
