"""End-to-end test of the shim at ``src/codefreedom/tools/codebase_memory.py``.

Verifies that the codefreedom tool registry can resolve the cbmem tool
class, call ``start``/``stop`` on it, and read ``mcp_endpoint`` —
without the cbmem package touching any docker / git state.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch



def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def _make_repo(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    _git(directory, "init", "-q")
    _git(directory, "config", "user.email", "t@t")
    _git(directory, "config", "user.name", "t")
    (directory / "README.md").write_text("hi")
    _git(directory, "add", "README.md")
    _git(directory, "commit", "-q", "-m", "init")
    return directory


class TestShimImports:
    """The shim must expose every symbol codefreedom's registry needs."""

    def test_load_profile(self):
        from codefreedom.tools.codebase_memory import _load_profile
        d = _load_profile()
        assert "image" in d
        assert "container_name" in d
        assert "port" in d

    def test_start_stop(self):
        from codefreedom.tools.codebase_memory import start, stop
        assert callable(start)
        assert callable(stop)

    def test_codebase_memory_tool(self):
        from codefreedom.tools.codebase_memory import CodebaseMemoryTool
        assert CodebaseMemoryTool().mcp_server_name == "codebase-memory"


class TestRegistryIntegration:
    def test_registry_includes_codebase_memory(self):
        from codefreedom.tools.registry import _KNOWN_TOOLS, _MCP_TOOLS
        assert "codebase-memory" in _KNOWN_TOOLS
        assert "codebase-memory" in _MCP_TOOLS

    def test_known_tools_tuple_shape(self):
        from codefreedom.tools.registry import _KNOWN_TOOLS
        load, start_fn, stop_fn = _KNOWN_TOOLS["codebase-memory"]
        assert callable(load)
        assert callable(start_fn)
        assert callable(stop_fn)


class TestStartStopBehavior:
    def test_start_outside_git_repo_returns_1(self, tmp_path, monkeypatch, capsys):
        from codefreedom.tools.codebase_memory import start
        monkeypatch.chdir(tmp_path)  # not a git repo
        rc = start({})
        assert rc == 1
        out = capsys.readouterr().err
        assert "git" in out.lower()

    def test_stop_outside_git_repo_returns_0(self, tmp_path, monkeypatch):
        from codefreedom.tools.codebase_memory import stop
        monkeypatch.chdir(tmp_path)
        rc = stop({})
        assert rc == 0  # not an error — nothing to stop

    def test_start_in_git_repo_invokes_manager(self, tmp_path, monkeypatch):
        repo = _make_repo(tmp_path / "proj")
        monkeypatch.chdir(repo)
        from codefreedom.tools.codebase_memory import start
        with patch("codefreedom.tools.codebase_memory.manager.ensure_running") as mock_ensure:
            mock_ensure.return_value = (None, {"container_name": "x", "mcp_port": 8330, "ui_port": 9749})
            rc = start({})
        assert rc == 0
        mock_ensure.assert_called_once()

    def test_start_runtime_error_returns_1(self, tmp_path, monkeypatch, capsys):
        repo = _make_repo(tmp_path / "proj")
        monkeypatch.chdir(repo)
        from codefreedom.tools.codebase_memory import start
        with patch("codefreedom.tools.codebase_memory.manager.ensure_running", side_effect=RuntimeError("no ports free")):
            rc = start({})
        assert rc == 1
        out = capsys.readouterr().err
        assert "no ports free" in out


class TestMcpEndpoint:
    def test_endpoint_in_git_repo_with_manifest(self, tmp_path, monkeypatch):
        repo = _make_repo(tmp_path / "proj")
        monkeypatch.chdir(repo)
        # Init a manifest with a custom port.
        import sys
        sys.path.insert(0, "/home/nilayparikh/.sources/codefreedom/docker/codebase-memory/src")
        from codebase_memory import manifest as _manifest
        data = _manifest.init_defaults(repo)
        data["mcp_port"] = 9100
        data["ui_port"] = 9100 + 1419
        data["container_name"] = "x"
        _manifest.save(repo, data)

        # Force the shim to re-read the manifest by re-importing.
        from codefreedom.tools.codebase_memory import CodebaseMemoryTool
        port, path = CodebaseMemoryTool().mcp_endpoint
        assert port == 9100
        assert path == "/mcp"

    def test_endpoint_no_manifest_returns_default(self, tmp_path, monkeypatch):
        repo = _make_repo(tmp_path / "proj")
        monkeypatch.chdir(repo)
        # No manifest init — just a fresh repo.
        from codefreedom.tools.codebase_memory import CodebaseMemoryTool
        port, path = CodebaseMemoryTool().mcp_endpoint
        # The shim auto-inits on first call, then returns the default 8330.
        # (After init the port is whatever _ensure_ports picks — likely 8330
        # if free in the test env, else the first free one. We just check
        # the path is /mcp.)
        assert path == "/mcp"
        assert isinstance(port, int)
