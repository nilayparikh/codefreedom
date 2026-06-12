"""Tests for docker/client.py — docker-py adapter."""

from unittest.mock import MagicMock, patch

import docker
import pytest

from codefreedom.docker.client import (
    check_docker_available,
    container_exists,
    container_is_running,
    ensure_image,
    list_containers,
    stop_and_remove,
    stop_container,
)


@pytest.fixture(autouse=True)
def _reset_lazy_client():
    import codefreedom.docker.client as mod

    mod._client._client = None


class TestCheckDockerAvailable:
    def test_returns_true_when_docker_reachable(self):
        mock_client = MagicMock()
        with patch("docker.from_env", return_value=mock_client):
            assert check_docker_available() is True

    def test_returns_false_when_docker_unreachable(self):
        with patch("docker.from_env", side_effect=docker.errors.DockerException("nope")):
            assert check_docker_available() is False


class TestContainerIsRunning:
    def test_running_container(self):
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_client.containers.get.return_value = mock_container

        with patch("docker.from_env", return_value=mock_client):
            assert container_is_running("my-container") is True

    def test_stopped_container(self):
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.status = "exited"
        mock_client.containers.get.return_value = mock_container

        with patch("docker.from_env", return_value=mock_client):
            assert container_is_running("my-container") is False

    def test_not_found(self):
        mock_client = MagicMock()
        mock_client.containers.get.side_effect = docker.errors.NotFound("nope")

        with patch("docker.from_env", return_value=mock_client):
            assert container_is_running("missing") is False


class TestContainerExists:
    def test_exists(self):
        mock_client = MagicMock()
        with patch("docker.from_env", return_value=mock_client):
            assert container_exists("my-container") is True

    def test_not_found(self):
        mock_client = MagicMock()
        mock_client.containers.get.side_effect = docker.errors.NotFound("nope")
        with patch("docker.from_env", return_value=mock_client):
            assert container_exists("missing") is False


class TestStopAndRemove:
    def test_stop_and_remove_called(self):
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_client.containers.get.return_value = mock_container

        with patch("docker.from_env", return_value=mock_client):
            stop_and_remove("my-container")
            mock_container.stop.assert_called_once()
            mock_container.remove.assert_called_once()

    def test_noop_if_not_found(self):
        mock_client = MagicMock()
        mock_client.containers.get.side_effect = docker.errors.NotFound("nope")

        with patch("docker.from_env", return_value=mock_client):
            stop_and_remove("missing")

    def test_noop_if_already_stopped(self):
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.status = "exited"
        mock_client.containers.get.return_value = mock_container

        with patch("docker.from_env", return_value=mock_client):
            stop_container("my-container")
            mock_container.stop.assert_not_called()


class TestEnsureImage:
    def test_pulls_if_not_cached(self):
        mock_client = MagicMock()
        mock_client.images.get.side_effect = docker.errors.ImageNotFound("nope")

        with patch("docker.from_env", return_value=mock_client):
            ensure_image("repo/image:tag")
            mock_client.images.pull.assert_called_once_with("repo/image:tag")

    def test_noop_if_cached(self):
        mock_client = MagicMock()
        with patch("docker.from_env", return_value=mock_client):
            ensure_image("repo/image:tag")
            mock_client.images.pull.assert_not_called()


class TestListContainers:
    def test_returns_name_and_status(self):
        mock_client = MagicMock()
        mock_c1 = MagicMock()
        mock_c1.name = "cf-chrome"
        mock_c1.status = "running"
        mock_c2 = MagicMock()
        mock_c2.name = "cf-web"
        mock_c2.status = "exited"
        mock_client.containers.list.return_value = [mock_c1, mock_c2]

        with patch("docker.from_env", return_value=mock_client):
            result = list_containers("cf-")
            assert result == [
                {"name": "cf-chrome", "status": "running"},
                {"name": "cf-web", "status": "exited"},
            ]
