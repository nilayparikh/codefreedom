"""Tests for github tool CLI — restart action and run() dispatch."""

import argparse

from codefreedom.cli.github import restart, run


def _settings(**overrides) -> dict:
    base = {
        "image": "codefreedom:github",
        "container_name": "codefreedom-tools-github",
        "port": 0,
        "data_dir": "~/.codefreedom/sandbox/tools/github",
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_test123"},
    }
    base.update(overrides)
    return base


class _R:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestRestart:

    def test_restart_existing_container(self, monkeypatch):
        """restart() calls docker restart, then docker port."""
        calls = []

        def fake_run(cmd, *a, **kw):
            calls.append(cmd)
            return _R()

        monkeypatch.setattr("codefreedom.cli.github.container_exists", lambda n: True)
        monkeypatch.setattr("codefreedom.cli.github.subprocess.run", fake_run)

        assert restart(_settings(container_name="gh")) == 0
        assert calls[0] == ["docker", "restart", "gh"]
        assert calls[1][:2] == ["docker", "port"]

    def test_restart_missing_container_returns_1(self, monkeypatch):
        monkeypatch.setattr("codefreedom.cli.github.container_exists", lambda n: False)
        assert restart(_settings()) == 1

    def test_restart_docker_failure_propagates(self, monkeypatch):
        def fake_run(cmd, *a, **kw):
            return _R(returncode=1, stderr="err")

        monkeypatch.setattr("codefreedom.cli.github.container_exists", lambda n: True)
        monkeypatch.setattr("codefreedom.cli.github.subprocess.run", fake_run)
        assert restart(_settings()) == 1


class TestRunDispatch:

    def test_run_dispatches_restart(self, monkeypatch):
        called = []

        def fake_restart(s):
            called.append(s)
            return 0

        monkeypatch.setattr("codefreedom.cli.github._load_profile", _settings)
        monkeypatch.setattr("codefreedom.cli.github.restart", fake_restart)

        assert run(argparse.Namespace(action="restart", port=0)) == 0
        assert len(called) == 1
        assert called[0]["container_name"] == "codefreedom-tools-github"
