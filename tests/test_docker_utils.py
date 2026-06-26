"""Tests for shared docker_utils module."""

import inspect

import pytest
from unittest import mock

from codefreedom.cli.docker_utils import (
    TOOL_INFO,
    accept_tool_prompt,
    check_docker_available,
    container_exists,
    container_is_running,
    print_help_section,
    print_tool_notice,
    resolve_data_dir,
    start_tool_container,
)


class TestStartToolContainer:
    def test_signature_callable(self):
        assert callable(start_tool_container)

    def test_signature_accepts_settings(self):
        sig = inspect.signature(start_tool_container)
        params = sig.parameters
        assert "settings" in params
        assert "label" in params
        assert "docker_args" in params

    def test_successful_start(self, monkeypatch):
        mock_run = mock.MagicMock()
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "abc123"
        monkeypatch.setattr(
            "codefreedom.cli.docker_utils.subprocess.run", mock_run
        )
        mock_ensure = mock.MagicMock(return_value=True)
        monkeypatch.setattr(
            "codefreedom.cli.docker_utils.start_tool_ensure_image", mock_ensure
        )

        settings = {
            "image": "test-image:latest",
            "container_name": "test-container",
            "data_dir": "/tmp/data",
            "env": {"FOO": "bar"},
        }
        docker_args = ["-p", "8080:8080", "-v", "/tmp/data:/data"]

        rc = start_tool_container(settings, "TEST", docker_args)

        assert rc == 0

        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "docker"
        assert call_args[1] == "run"
        assert "-d" in call_args
        assert "--name" in call_args
        assert "test-container" in call_args
        assert "--restart" in call_args
        assert "unless-stopped" in call_args
        assert "-e" in call_args
        assert "FOO=bar" in call_args
        assert "-p" in call_args
        assert "8080:8080" in call_args
        assert "-v" in call_args
        assert "/tmp/data:/data" in call_args
        assert call_args[-1] == "test-image:latest"

    def test_returns_1_on_timeout(self, monkeypatch):
        monkeypatch.setattr(
            "codefreedom.cli.docker_utils.container_exists", lambda _name: False
        )
        monkeypatch.setattr(
            "codefreedom.cli.docker_utils.resolve_data_dir", lambda d: __import__("pathlib").Path(d)
        )
        mock_ensure = mock.MagicMock(return_value=True)
        monkeypatch.setattr(
            "codefreedom.cli.docker_utils.start_tool_ensure_image", mock_ensure
        )
        mock_run = mock.MagicMock(side_effect=OSError("timeout"))
        monkeypatch.setattr(
            "codefreedom.cli.docker_utils.subprocess.run", mock_run
        )

        settings = {
            "image": "img",
            "container_name": "c",
            "data_dir": "/tmp/d",
            "env": {},
        }
        rc = start_tool_container(settings, "T", [])
        assert rc == 1

    def test_returns_1_on_nonzero_exit(self, monkeypatch):
        mock_run = mock.MagicMock()
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "error"
        monkeypatch.setattr(
            "codefreedom.cli.docker_utils.subprocess.run", mock_run
        )
        mock_ensure = mock.MagicMock(return_value=True)
        monkeypatch.setattr(
            "codefreedom.cli.docker_utils.start_tool_ensure_image", mock_ensure
        )

        settings = {
            "image": "img",
            "container_name": "c",
            "data_dir": "/tmp/d",
            "env": {},
        }
        rc = start_tool_container(settings, "T", [])
        assert rc == 1

    def test_returns_1_when_image_fails(self, monkeypatch):
        mock_ensure = mock.MagicMock(return_value=False)
        monkeypatch.setattr(
            "codefreedom.cli.docker_utils.start_tool_ensure_image", mock_ensure
        )

        settings = {
            "image": "img",
            "container_name": "c",
            "data_dir": "/tmp/d",
            "env": {},
        }
        rc = start_tool_container(settings, "T", [])
        assert rc == 1


class TestToolInfo:
    def test_chrome_entry(self):
        assert "chrome" in TOOL_INFO
        assert TOOL_INFO["chrome"]["name"] == "Chrome Browser (Headless)"

    def test_web_entry(self):
        assert "web" in TOOL_INFO
        assert TOOL_INFO["web"]["name"] == "Web Search (MCP)"

    def test_github_entry(self):
        assert "github" in TOOL_INFO
        assert TOOL_INFO["github"]["name"] == "GitHub MCP Server"


class TestPrintToolNotice:
    def test_importable_and_callable(self):
        assert callable(print_tool_notice)

    def test_runs_without_crash(self):
        print_tool_notice("chrome")


class TestAcceptToolPrompt:
    def test_importable_and_callable(self):
        assert callable(accept_tool_prompt)


class TestPrintHelpSection:
    def test_importable_and_callable(self):
        assert callable(print_help_section)


class TestResolveDataDir:
    def test_creates_and_resolves(self, tmp_path):
        d = tmp_path / "data" / "chrome"
        result = resolve_data_dir(str(d))
        assert result == d
        assert d.exists()

    def test_expands_home(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows expanduser
        result = resolve_data_dir("~/mydata")
        assert result == tmp_path / "mydata"


class TestContainerExists:
    def test_exists(self, monkeypatch):
        mock_run = mock.MagicMock()
        mock_run.return_value.stdout = "my-container\n"
        monkeypatch.setattr("codefreedom.cli.docker_utils.subprocess.run", mock_run)
        assert container_exists("my-container") is True

    def test_not_exists(self, monkeypatch):
        mock_run = mock.MagicMock()
        mock_run.return_value.stdout = "other-container\n"
        monkeypatch.setattr("codefreedom.cli.docker_utils.subprocess.run", mock_run)
        assert container_exists("my-container") is False

    def test_docker_not_found(self, monkeypatch):
        mock_run = mock.MagicMock(side_effect=FileNotFoundError)
        monkeypatch.setattr("codefreedom.cli.docker_utils.subprocess.run", mock_run)
        assert container_exists("any") is False


class TestContainerIsRunning:
    def test_running(self, monkeypatch):
        mock_run = mock.MagicMock()
        mock_run.return_value.stdout = "my-container\n"
        monkeypatch.setattr("codefreedom.cli.docker_utils.subprocess.run", mock_run)
        assert container_is_running("my-container") is True

    def test_not_running(self, monkeypatch):
        mock_run = mock.MagicMock()
        mock_run.return_value.stdout = ""
        monkeypatch.setattr("codefreedom.cli.docker_utils.subprocess.run", mock_run)
        assert container_is_running("my-container") is False


class TestCheckDockerAvailable:
    def test_available(self, monkeypatch):
        mock_run = mock.MagicMock()
        mock_run.return_value.returncode = 0
        monkeypatch.setattr("codefreedom.cli.docker_utils.subprocess.run", mock_run)
        assert check_docker_available() is True

    def test_not_installed(self, monkeypatch):
        mock_run = mock.MagicMock(side_effect=FileNotFoundError)
        monkeypatch.setattr("codefreedom.cli.docker_utils.subprocess.run", mock_run)
        assert check_docker_available() is False

    def test_nonzero_exit(self, monkeypatch):
        mock_run = mock.MagicMock()
        mock_run.return_value.returncode = 127
        monkeypatch.setattr("codefreedom.cli.docker_utils.subprocess.run", mock_run)
        assert check_docker_available() is False
pytestmark = pytest.mark.integration
