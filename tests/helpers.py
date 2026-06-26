"""Shared test helpers — reusable utilities for test files.

These are regular functions (not fixtures) that can be imported
directly from test files.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml


# ── Tool profile helpers ──────────────────────────────────────────────────────


def tool_home() -> Path:
    """Return the tool home directory (set by conftest.py or default)."""
    from codefreedom.core.config import get_codefreedom_dir

    override = os.environ.get("CODEFREEDOM_TOOL_HOME")
    if override:
        return Path(override)
    return get_codefreedom_dir()


def write_tool_profile(tool: str, data: dict) -> None:
    """Write tool profile to unified profiles.yaml in config directory."""
    from codefreedom.core.config import get_config_dir

    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)

    profiles_path = config_dir / "profiles.yaml"
    if profiles_path.exists():
        with open(profiles_path, encoding="utf-8") as f:
            existing = yaml.safe_load(f) or {}
    else:
        existing = {}

    if "tools" not in existing:
        existing["tools"] = {}
    existing["tools"].update(data)

    with open(profiles_path, "w", encoding="utf-8") as f:
        yaml.dump(existing, f, default_flow_style=False, sort_keys=False)


def clean_profiles() -> None:
    """Remove unified profiles.yaml to ensure clean defaults."""
    from codefreedom.core.config import get_config_dir

    config_dir = get_config_dir()
    profiles_path = config_dir / "profiles.yaml"
    if profiles_path.exists():
        profiles_path.unlink()


# ── Tool restart/run-dispatch test mixin ──────────────────────────────────────


class ToolRestartMixin:
    """Shared TestRestart tests for tools with identical restart logic.

    Subclasses must set:
        tool_module_path: e.g. "codefreedom.tools.chrome"
        settings_factory: callable returning a settings dict
        expected_container_name: the default container_name in settings
    """

    tool_module_path: str = ""
    settings_factory = staticmethod(lambda **kw: {})
    expected_container_name: str = ""

    def test_restart_existing_container(self, monkeypatch):
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

        from importlib import import_module

        mod = import_module(self.tool_module_path)
        result = mod.restart(self.settings_factory(container_name="my-tool"))
        assert result == 0
        assert len(calls) == 1
        assert calls[0] == ["docker", "restart", "my-tool"]

    def test_restart_missing_container_returns_1(self, monkeypatch):
        calls: list[list[str]] = []

        def fake_run(cmd, *args, **kwargs):
            calls.append(cmd)
            raise AssertionError("subprocess.run should not be called")

        monkeypatch.setattr(
            "codefreedom.cli.docker_utils.container_exists", lambda name: False
        )
        monkeypatch.setattr("codefreedom.cli.docker_utils.subprocess.run", fake_run)

        from importlib import import_module

        mod = import_module(self.tool_module_path)
        result = mod.restart(self.settings_factory())
        assert result == 1
        assert calls == []

    def test_restart_docker_failure_propagates(self, monkeypatch):
        def fake_run(cmd, *args, **kwargs):
            class _R:
                returncode = 1
                stderr = "docker error: container not found"

            return _R()

        monkeypatch.setattr(
            "codefreedom.cli.docker_utils.container_exists", lambda name: True
        )
        monkeypatch.setattr("codefreedom.cli.docker_utils.subprocess.run", fake_run)

        from importlib import import_module

        mod = import_module(self.tool_module_path)
        result = mod.restart(self.settings_factory())
        assert result == 1

    def test_restart_does_not_remove_container(self, monkeypatch):
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

        from importlib import import_module

        mod = import_module(self.tool_module_path)
        mod.restart(self.settings_factory())
        assert len(calls) == 1
        assert "rm" not in calls[0]
        assert "stop" not in calls[0]
        assert calls[0] == ["docker", "restart", self.expected_container_name]


class ToolRunDispatchMixin:
    """Shared TestRunDispatch tests for tools with identical run() dispatch.

    Subclasses must set the same attributes as ToolRestartMixin, plus:
        default_port: the port to use in argparse.Namespace
    """

    tool_module_path: str = ""
    settings_factory = staticmethod(lambda **kw: {})
    expected_container_name: str = ""
    default_port: int = 0

    def test_run_dispatches_restart_to_restart_function(self, monkeypatch):
        called = []

        def fake_restart(settings):
            called.append(settings)
            return 0

        monkeypatch.setattr(
            f"{self.tool_module_path}._load_profile", self.settings_factory
        )
        monkeypatch.setattr(f"{self.tool_module_path}.restart", fake_restart)

        from importlib import import_module

        mod = import_module(self.tool_module_path)
        args = argparse.Namespace(action="restart", port=self.default_port)
        result = mod.run(args)
        assert result == 0
        assert len(called) == 1
        assert called[0]["container_name"] == self.expected_container_name

    def test_run_restart_does_not_load_profile_from_disk(self, monkeypatch):
        monkeypatch.setattr(
            f"{self.tool_module_path}._load_profile", lambda: self.settings_factory()
        )
        monkeypatch.setattr(
            f"{self.tool_module_path}.restart",
            lambda settings: 0,
        )

        from importlib import import_module

        mod = import_module(self.tool_module_path)
        args = argparse.Namespace(action="restart", port=self.default_port)
        result = mod.run(args)
        assert result == 0
