"""Tests for codebase_memory tool CLI — start, restart, run() dispatch, schema."""

import argparse

import pytest

from codefreedom.tools.codebase_memory import (
    _DEFAULT_CONTAINER_NAME,
    _DEFAULT_PORT,
    start,
    status,
    restart,
    run,
)
from codefreedom.tools.schemas.codebase_memory import CodebaseMemorySettings


def _settings(**overrides) -> dict:
    base = {
        "image": "codefreedom:codebase-memory",
        "container_name": "codefreedom-tools-codebase-memory",
        "port": 8330,
        "ui_port": 9749,
        "data_dir": "~/.codefreedom/tools/codebase-memory",
        "bind_host": "0.0.0.0",
        "remote_url": "",
        "enable_ui": True,
        "log_level": "info",
        "auto_index": False,
        "env": {},
    }
    base.update(overrides)
    return base


class _R:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestStart:

    def test_start_running_container_is_noop(self, monkeypatch):
        calls = []

        def fake_eprint(msg=""):
            calls.append(msg)

        monkeypatch.setattr("codefreedom.tools.codebase_memory.start_tool_init_gate", lambda label: True)
        monkeypatch.setattr("codefreedom.tools.codebase_memory.print_tool_notice", lambda name: None)
        monkeypatch.setattr("codefreedom.tools.codebase_memory.container_is_running", lambda n: True)
        monkeypatch.setattr("codefreedom.tools.codebase_memory.eprint", fake_eprint)

        assert start(_settings()) == 0
        joined = "\n".join(calls)
        assert "already running" in joined

    def test_start_without_docker_returns_1(self, monkeypatch):
        monkeypatch.setattr("codefreedom.tools.codebase_memory.start_tool_init_gate", lambda label: True)
        monkeypatch.setattr("codefreedom.tools.codebase_memory.print_tool_notice", lambda name: None)
        monkeypatch.setattr("codefreedom.tools.codebase_memory.container_is_running", lambda n: False)
        monkeypatch.setattr("codefreedom.tools.codebase_memory.start_tool_docker_guard", lambda label: False)
        assert start(_settings()) == 1

    def test_start_succeeds_and_exposes_mcp_endpoint(self, monkeypatch):
        captured = {}

        def fake_start_container(settings, label, docker_args):
            captured["settings"] = settings
            captured["label"] = label
            captured["docker_args"] = docker_args
            return 0

        monkeypatch.setattr("codefreedom.tools.codebase_memory.start_tool_init_gate", lambda label: True)
        monkeypatch.setattr("codefreedom.tools.codebase_memory.print_tool_notice", lambda name: None)
        monkeypatch.setattr("codefreedom.tools.codebase_memory.container_is_running", lambda n: False)
        monkeypatch.setattr("codefreedom.tools.codebase_memory.start_tool_docker_guard", lambda label: True)
        monkeypatch.setattr("codefreedom.tools.codebase_memory.start_tool_container", fake_start_container)
        monkeypatch.setattr("codefreedom.tools.codebase_memory.resolve_data_dir", lambda d: d)

        rc = start(_settings())
        assert rc == 0
        assert captured["label"] == "CODEBASE-MEMORY"
        args = captured["docker_args"]
        assert "0.0.0.0:8330:8330" in args
        assert any(a.endswith(":/cache") for a in args)
        assert captured["settings"]["env"]["CBM_LOG_LEVEL"] == "info"
        assert captured["settings"]["env"]["CBM_CACHE_DIR"] == "/cache"

    def test_start_with_enable_ui_adds_ui_port(self, monkeypatch):
        captured = {}

        def fake_start_container(settings, label, docker_args):
            captured["docker_args"] = docker_args
            return 0

        monkeypatch.setattr("codefreedom.tools.codebase_memory.start_tool_init_gate", lambda label: True)
        monkeypatch.setattr("codefreedom.tools.codebase_memory.print_tool_notice", lambda name: None)
        monkeypatch.setattr("codefreedom.tools.codebase_memory.container_is_running", lambda n: False)
        monkeypatch.setattr("codefreedom.tools.codebase_memory.start_tool_docker_guard", lambda label: True)
        monkeypatch.setattr("codefreedom.tools.codebase_memory.start_tool_container", fake_start_container)
        monkeypatch.setattr("codefreedom.tools.codebase_memory.resolve_data_dir", lambda d: d)

        rc = start(_settings(enable_ui=True, ui_port=9749))
        assert rc == 0
        assert "0.0.0.0:9749:9749" in captured["docker_args"]

    def test_start_with_auto_index_sets_env(self, monkeypatch):
        captured = {}

        def fake_start_container(settings, label, docker_args):
            captured["settings"] = settings
            return 0

        monkeypatch.setattr("codefreedom.tools.codebase_memory.start_tool_init_gate", lambda label: True)
        monkeypatch.setattr("codefreedom.tools.codebase_memory.print_tool_notice", lambda name: None)
        monkeypatch.setattr("codefreedom.tools.codebase_memory.container_is_running", lambda n: False)
        monkeypatch.setattr("codefreedom.tools.codebase_memory.start_tool_docker_guard", lambda label: True)
        monkeypatch.setattr("codefreedom.tools.codebase_memory.start_tool_container", fake_start_container)
        monkeypatch.setattr("codefreedom.tools.codebase_memory.resolve_data_dir", lambda d: d)

        rc = start(_settings(auto_index=True))
        assert rc == 0
        assert captured["settings"]["env"]["CBM_AUTO_INDEX"] == "true"


class TestRestart:

    def test_restart_existing_container(self, monkeypatch):
        calls = []

        def fake_restart(settings, label):
            calls.append((settings, label))
            return 0

        monkeypatch.setattr("codefreedom.tools.codebase_memory.restart_tool_container", fake_restart)

        assert restart(_settings(container_name="cbm")) == 0
        assert calls[0][0]["container_name"] == "cbm"
        assert calls[0][1] == "CODEBASE-MEMORY"

    def test_restart_missing_container_returns_1(self, monkeypatch):
        monkeypatch.setattr("codefreedom.tools.codebase_memory.restart_tool_container", lambda s, label: 1)
        assert restart(_settings()) == 1


class TestStatus:

    def test_status_uses_status_tool_container(self, monkeypatch):
        calls = []

        def fake_status_tool_container(settings, label, extra_info=""):
            calls.append((settings, label, extra_info))
            return 0

        monkeypatch.setattr("codefreedom.cli.docker_utils.status_tool_container", fake_status_tool_container)

        rc = status(_settings())
        assert rc == 0
        assert calls[0][1] == "CODEBASE-MEMORY"
        assert "MCP endpoint" in calls[0][2]


class TestRunDispatch:

    def test_run_dispatches_start(self, monkeypatch):
        called = []

        def fake_start(s):
            called.append(s)
            return 0

        monkeypatch.setattr("codefreedom.tools.codebase_memory._load_profile", _settings)
        monkeypatch.setattr("codefreedom.tools.codebase_memory.start", fake_start)

        assert run(argparse.Namespace(action="start", port=0)) == 0
        assert len(called) == 1
        assert called[0]["container_name"] == _DEFAULT_CONTAINER_NAME
        assert called[0]["port"] == _DEFAULT_PORT

    def test_run_dispatches_status_default(self, monkeypatch):
        called = []

        def fake_status(s):
            called.append(s)
            return 0

        monkeypatch.setattr("codefreedom.tools.codebase_memory._load_profile", _settings)
        monkeypatch.setattr("codefreedom.tools.codebase_memory.status", fake_status)

        assert run(argparse.Namespace(action=None, port=0)) == 0
        assert len(called) == 1


class TestSchema:

    def test_settings_default_image_only_required(self):
        s = CodebaseMemorySettings(image="x:latest")
        assert s.image == "x:latest"
        assert s.port is None
        assert s.enable_ui is True
        assert s.log_level is None

    def test_log_level_validated(self):
        with pytest.raises(ValueError):
            CodebaseMemorySettings(image="x", log_level="trace")

    def test_log_level_normalized(self):
        s = CodebaseMemorySettings(image="x", log_level="WARN")
        assert s.log_level == "warn"

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValueError):
            CodebaseMemorySettings(image="x", bogus=1)


pytestmark = pytest.mark.integration
