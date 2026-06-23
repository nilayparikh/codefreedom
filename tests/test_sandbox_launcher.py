"""Tests for codefreedom.sandbox.launcher module."""

from __future__ import annotations

import pytest

import signal
import subprocess
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.integration



class TestRunSandbox:
    @patch("subprocess.run")
    @patch("subprocess.Popen")
    def test_success_returns_zero(self, mock_popen, mock_run):
        from codefreedom.sandbox.launcher import run_sandbox

        inspect_result = MagicMock()
        inspect_result.returncode = 0
        create_result = MagicMock()
        create_result.returncode = 0
        stop_result = MagicMock()
        rm_result = MagicMock()

        mock_run.side_effect = [
            inspect_result,
            create_result,
            stop_result,
            rm_result,
        ]

        proc = MagicMock()
        proc.wait.return_value = None
        proc.returncode = 0
        proc.poll.return_value = None
        mock_popen.return_value = proc

        result = run_sandbox(
            image="test:latest",
            container_name="test-container",
            base_opts=[],
            env_flags=[],
            exec_image_cmd=["docker", "exec", "-it", "test-container", "echo"],
        )
        assert result == 0

    @patch("subprocess.run")
    @patch("subprocess.Popen")
    def test_pulls_image_when_not_cached(self, mock_popen, mock_run):
        from codefreedom.sandbox.launcher import run_sandbox

        inspect_result = MagicMock()
        inspect_result.returncode = 1
        pull_result = MagicMock()
        pull_result.returncode = 0
        create_result = MagicMock()
        create_result.returncode = 0
        stop_result = MagicMock()
        rm_result = MagicMock()

        mock_run.side_effect = [
            inspect_result,
            pull_result,
            create_result,
            stop_result,
            rm_result,
        ]

        proc = MagicMock()
        proc.wait.return_value = None
        proc.returncode = 0
        proc.poll.return_value = None
        mock_popen.return_value = proc

        result = run_sandbox(
            image="test:latest",
            container_name="test-container",
            base_opts=[],
            env_flags=[],
            exec_image_cmd=["docker", "exec", "-it", "test-container", "echo"],
        )
        assert result == 0
        pull_call = mock_run.call_args_list[1]
        assert "docker" in pull_call[0][0]
        assert "pull" in pull_call[0][0]

    @patch("subprocess.run")
    def test_returns_1_on_pull_failure(self, mock_run):
        from codefreedom.sandbox.launcher import run_sandbox

        inspect_result = MagicMock()
        inspect_result.returncode = 1
        pull_result = MagicMock()
        pull_result.returncode = 1
        pull_result.stderr = "pull error"

        mock_run.side_effect = [inspect_result, pull_result]

        result = run_sandbox(
            image="bad:image",
            container_name="test-container",
            base_opts=[],
            env_flags=[],
            exec_image_cmd=["docker", "exec", "test-container", "echo"],
        )
        assert result == 1

    @patch("subprocess.run")
    def test_returns_1_on_create_failure(self, mock_run):
        from codefreedom.sandbox.launcher import run_sandbox

        inspect_result = MagicMock()
        inspect_result.returncode = 0
        create_result = MagicMock()
        create_result.returncode = 1
        create_result.stderr = "container create error"

        mock_run.side_effect = [inspect_result, create_result]

        result = run_sandbox(
            image="test:latest",
            container_name="test-container",
            base_opts=[],
            env_flags=[],
            exec_image_cmd=["docker", "exec", "test-container", "echo"],
        )
        assert result == 1


class TestSandboxStatus:
    @patch("subprocess.run")
    def test_shows_containers(self, mock_run):
        from codefreedom.sandbox.launcher import sandbox_status

        result_mock = MagicMock()
        result_mock.stdout = "NAMES\tSTATUS\ncodefreedom-abcd\tUp 5 minutes"
        result_mock.returncode = 0
        mock_run.return_value = result_mock

        exit_code = sandbox_status("codefreedom-")
        assert exit_code == 0

    @patch("subprocess.run")
    def test_handles_no_containers(self, mock_run):
        from codefreedom.sandbox.launcher import sandbox_status

        result_mock = MagicMock()
        result_mock.stdout = ""
        result_mock.returncode = 0
        mock_run.return_value = result_mock

        exit_code = sandbox_status("codefreedom-")
        assert exit_code == 0

    @patch(
        "subprocess.run",
        side_effect=subprocess.SubprocessError("docker not found"),
    )
    def test_handles_subprocess_error(self, _mock_run):
        from codefreedom.sandbox.launcher import sandbox_status

        exit_code = sandbox_status("codefreedom-")
        assert exit_code == 1


class TestSandboxStop:
    @patch("subprocess.run")
    def test_stops_containers(self, mock_run):
        from codefreedom.sandbox.launcher import sandbox_stop

        find_result = MagicMock()
        find_result.stdout = "abc123\ndef456"
        stop_result = MagicMock()
        rm_result = MagicMock()

        mock_run.side_effect = [
            find_result,
            stop_result,
            rm_result,
            stop_result,
            rm_result,
        ]

        exit_code = sandbox_stop("codefreedom-")
        assert exit_code == 0

    @patch("subprocess.run")
    def test_handles_no_containers(self, mock_run):
        from codefreedom.sandbox.launcher import sandbox_stop

        find_result = MagicMock()
        find_result.stdout = ""
        mock_run.return_value = find_result

        exit_code = sandbox_stop("codefreedom-")
        assert exit_code == 0


class TestSignalForwarding:
    def test_forward_signal_sends_to_proc(self):
        from codefreedom.sandbox.signals import forward_signal

        proc = MagicMock()
        proc.poll.return_value = None

        forward_signal(proc, signal.SIGTERM, None)
        proc.send_signal.assert_called_once_with(signal.SIGTERM)

    def test_forward_signal_noop_when_proc_ended(self):
        from codefreedom.sandbox.signals import forward_signal

        proc = MagicMock()
        proc.poll.return_value = 0

        forward_signal(proc, signal.SIGTERM, None)
        proc.send_signal.assert_not_called()

