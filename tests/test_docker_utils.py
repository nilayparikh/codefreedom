"""Tests for shared docker_utils module."""

from unittest import mock

from codefreedom.cli.docker_utils import (
    check_docker_available,
    container_exists,
    container_is_running,
    resolve_data_dir,
)


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
