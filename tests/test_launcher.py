"""Tests for codefreedom.launcher module."""

from __future__ import annotations
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.integration
@pytest.fixture()
def workspace_dir(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws
class TestGenerateContainerName:
    def test_returns_codefreedom_prefix(self):
        from codefreedom.launcher import _generate_container_name

        name = _generate_container_name()
        assert name.startswith("codefreedom-")

    def test_suffix_is_six_hex_chars(self):
        from codefreedom.launcher import _generate_container_name

        name = _generate_container_name()
        suffix = name.removeprefix("codefreedom-")
        assert len(suffix) == 6
        int(suffix, 16)

    def test_names_are_unique(self):
        from codefreedom.launcher import _generate_container_name

        names = {_generate_container_name() for _ in range(50)}
        assert len(names) == 50
class TestFindClaudeBinary:
    @patch("shutil.which", return_value="/usr/local/bin/claude")
    def test_returns_path_when_found(self, mock_which):
        from codefreedom.launcher import find_claude_binary

        result = find_claude_binary()
        assert result == "/usr/local/bin/claude"
        mock_which.assert_called_once_with("claude")

    @patch("shutil.which", return_value=None)
    def test_returns_none_when_not_found(self, mock_which):
        from codefreedom.launcher import find_claude_binary

        result = find_claude_binary()
        assert result is None
class TestWriteMcpJson:
    def test_creates_mcp_json(self, workspace_dir: Path):
        from codefreedom.launcher import _write_mcp_json

        with patch("codefreedom.launcher.load_tool_mcp_endpoints") as mock_load:
            mock_load.return_value = {
                "mcpServers": {
                    "chrome-devtools": {
                        "type": "http",
                        "url": "http://127.0.0.1:9223/mcp",
                    }
                }
            }
            _write_mcp_json(workspace_dir, ["chrome"])

        mcp_path = workspace_dir / ".mcp.json"
        assert mcp_path.exists()
        data = json.loads(mcp_path.read_text())
        assert "chrome-devtools" in data["mcpServers"]

    def test_preserves_existing_servers(self, workspace_dir: Path):
        from codefreedom.launcher import _write_mcp_json

        mcp_path = workspace_dir / ".mcp.json"
        mcp_path.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "existing": {
                            "type": "http",
                            "url": "http://localhost:9999",
                        }
                    }
                }
            )
        )

        with patch("codefreedom.launcher.load_tool_mcp_endpoints") as mock_load:
            mock_load.return_value = {
                "mcpServers": {
                    "chrome-devtools": {
                        "type": "http",
                        "url": "http://127.0.0.1:9223/mcp",
                    }
                }
            }
            _write_mcp_json(workspace_dir, ["chrome"])

        data = json.loads(mcp_path.read_text())
        assert "existing" in data["mcpServers"]
        assert "chrome-devtools" in data["mcpServers"]

    def test_noop_when_no_endpoints(self, workspace_dir: Path):
        from codefreedom.launcher import _write_mcp_json

        with patch("codefreedom.launcher.load_tool_mcp_endpoints") as mock_load:
            mock_load.return_value = {"mcpServers": {}}
            _write_mcp_json(workspace_dir, [])

        mcp_path = workspace_dir / ".mcp.json"
        assert not mcp_path.exists()
class TestRegisterClaudeMcpServers:
    def test_registers_project_scoped_http_servers(self, workspace_dir: Path):
        from codefreedom.launcher import _register_claude_mcp_servers

        with patch("codefreedom.launcher.load_tool_mcp_endpoints") as mock_load:
            with patch("codefreedom.launcher.find_claude_binary", return_value="/usr/bin/claude"):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = subprocess.CompletedProcess([], 0, "", "")
                    mock_load.return_value = {
                        "mcpServers": {
                            "chrome-devtools": {
                                "type": "http",
                                "url": "http://127.0.0.1:9223/mcp",
                            },
                            "web": {
                                "type": "http",
                                "url": "http://127.0.0.1:8420/mcp",
                            },
                        }
                    }

                    _register_claude_mcp_servers(workspace_dir, ["chrome", "web"])

        assert mock_run.call_count == 2
        commands = [call.args[0] for call in mock_run.call_args_list]
        assert commands[0] == [
            "/usr/bin/claude",
            "mcp",
            "add",
            "--transport",
            "http",
            "--scope",
            "project",
            "chrome-devtools",
            "http://127.0.0.1:9223/mcp",
        ]
        assert commands[1] == [
            "/usr/bin/claude",
            "mcp",
            "add",
            "--transport",
            "http",
            "--scope",
            "project",
            "web",
            "http://127.0.0.1:8420/mcp",
        ]

    def test_noop_when_claude_missing(self, workspace_dir: Path):
        from codefreedom.launcher import _register_claude_mcp_servers

        with patch("codefreedom.launcher.find_claude_binary", return_value=None):
            with patch("subprocess.run") as mock_run:
                _register_claude_mcp_servers(workspace_dir, ["chrome"])

        mock_run.assert_not_called()


class TestEnsureCodefreedomDir:
    def test_creates_sandbox_dirs(self):
        from codefreedom.launcher import ensure_codefreedom_dir

        claude_dir, claude_json = ensure_codefreedom_dir("test-profile")
        assert claude_dir.exists()
        assert claude_json.exists()
        assert json.loads(claude_json.read_text()) == {}

    def test_reuses_existing_json(self):
        from codefreedom.launcher import ensure_codefreedom_dir

        _, claude_json = ensure_codefreedom_dir("test-profile")
        claude_json.write_text('{"key": "value"}')

        _, claude_json2 = ensure_codefreedom_dir("test-profile")
        data = json.loads(claude_json2.read_text())
        assert data == {"key": "value"}
class TestRunLocal:
    @patch("codefreedom.launcher.find_claude_binary", return_value=None)
    def test_returns_1_when_binary_not_found(self, _mock):
        from codefreedom.launcher import run_local

        result = run_local({}, [])
        assert result == 1

    @patch("codefreedom.launcher.find_claude_binary", return_value="/usr/bin/claude")
    @patch("subprocess.Popen")
    def test_runs_claude_with_env(self, mock_popen, _mock_binary):
        from codefreedom.launcher import run_local

        proc = MagicMock()
        proc.wait.return_value = None
        proc.returncode = 0
        mock_popen.return_value = proc

        result = run_local({"ANTHROPIC_API_KEY": "sk-test"}, [])
        assert result == 0
        cmd = mock_popen.call_args[0][0]
        assert cmd[0] == "/usr/bin/claude"

    @patch("codefreedom.launcher.find_claude_binary", return_value="/usr/bin/claude")
    @patch("subprocess.Popen")
    def test_dangerously_skip_permissions_flag(self, mock_popen, _mock_binary):
        from codefreedom.launcher import run_local

        proc = MagicMock()
        proc.wait.return_value = None
        proc.returncode = 0
        mock_popen.return_value = proc

        run_local({}, [], dangerously_skip=True)
        cmd = mock_popen.call_args[0][0]
        assert "--dangerously-skip-permissions" in cmd
class TestStatusAndStop:
    @patch("codefreedom.sandbox.launcher.sandbox_status", return_value=0)
    def test_status_delegates_to_sandbox(self, mock_status):
        from codefreedom.launcher import status

        result = status()
        assert result == 0
        mock_status.assert_called_once()

    @patch("codefreedom.sandbox.launcher.sandbox_stop", return_value=0)
    def test_stop_delegates_to_sandbox(self, mock_stop):
        from codefreedom.launcher import stop

        result = stop()
        assert result == 0
        mock_stop.assert_called_once()
class TestFailurePaths:
    @patch("subprocess.Popen", side_effect=FileNotFoundError("No such file"))
    @patch("codefreedom.launcher.find_claude_binary", return_value="/usr/bin/claude")
    def test_run_local_handles_file_not_found(self, _mock_binary, _mock_popen):
        from codefreedom.launcher import run_local

        result = run_local({}, [])
        assert result == 1

    @patch("subprocess.Popen", side_effect=KeyboardInterrupt())
    @patch("codefreedom.launcher.find_claude_binary", return_value="/usr/bin/claude")
    def test_run_local_returns_130_on_keyboard_interrupt(
        self, _mock_binary, _mock_popen
    ):
        from codefreedom.launcher import run_local

        result = run_local({}, [])
        assert result == 130
class TestMcpJsonEdgeCases:
    def test_handles_corrupt_existing_mcp_json(self, workspace_dir: Path):
        from codefreedom.launcher import _write_mcp_json

        mcp_path = workspace_dir / ".mcp.json"
        mcp_path.write_text("not valid json{")

        with patch("codefreedom.launcher.load_tool_mcp_endpoints") as mock_load:
            mock_load.return_value = {
                "mcpServers": {
                    "web": {"type": "http", "url": "http://127.0.0.1:8420/mcp"}
                }
            }
            _write_mcp_json(workspace_dir, ["web"])

        data = json.loads(mcp_path.read_text())
        assert "web" in data["mcpServers"]
