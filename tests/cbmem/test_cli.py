"""Tests for ``codebase_memory.cli`` — the 8 subcommands and their dispatch.

Tests run with ``monkeypatch.chdir`` to a temp git repo so the CWD
resolution works. All docker calls are mocked; the real bridge / image
isn't needed for CLI dispatch.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from codebase_memory import cli, manager, manifest


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


def _args(cbmem_action: str = "status", **kwargs) -> argparse.Namespace:
    base = {
        "cbmem_action": cbmem_action,
        "follow": False,
        "keep_manifest": False,
        "keep_cache": False,
        "artifact": False,
    }
    base.update(kwargs)
    return argparse.Namespace(**base)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    project = _make_repo(tmp_path / "proj")
    monkeypatch.chdir(project)
    return project


class TestInit:
    def test_creates_manifest(self, repo, capsys):
        assert not manifest.exists(repo)
        rc = cli._cmd_init(repo, _args("init"))
        assert rc == 0
        assert manifest.exists(repo)
        data = manifest.load(repo)
        assert data["id"] == "proj"

    def test_idempotent(self, repo, capsys):
        cli._cmd_init(repo, _args("init"))
        rc = cli._cmd_init(repo, _args("init"))
        assert rc == 0
        # The manifest is still the same; we didn't clobber it.
        data = manifest.load(repo)
        assert data["id"] == "proj"


class TestStart:
    def test_creates_container(self, repo, capsys):
        cli._cmd_init(repo, _args("init"))
        with patch.object(manager, "container_exists", return_value=False), \
             patch.object(manager, "_docker_run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=(), returncode=0, stdout="abc", stderr="")
            rc = cli._cmd_start(repo, _args("start"))
        assert rc == 0
        out = capsys.readouterr().err
        assert "MCP:" in out
        assert "UI:" in out

    def test_remote_url_prints_remote(self, repo, capsys):
        cli._cmd_init(repo, _args("init"))
        # Patch the manifest to set remote_url.
        data = manifest.load(repo)
        data["remote_url"] = "https://x.example/mcp"
        manifest.save(repo, data)
        rc = cli._cmd_start(repo, _args("start"))
        assert rc == 0
        out = capsys.readouterr().err
        assert "https://x.example/mcp" in out

    def test_failure_returns_1(self, repo, capsys):
        cli._cmd_init(repo, _args("init"))
        with patch.object(manager, "container_exists", return_value=False), \
             patch.object(manager, "_docker_run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=(), returncode=125, stdout="", stderr="boom")
            rc = cli._cmd_start(repo, _args("start"))
        assert rc == 1


class TestStop:
    def test_stops_running_container(self, repo, capsys):
        cli._cmd_init(repo, _args("init"))
        with patch.object(manager, "stop", return_value=True) as mock_stop:
            rc = cli._cmd_stop(repo, _args("stop"))
        assert rc == 0
        mock_stop.assert_called_once()

    def test_stop_when_no_container(self, repo, capsys):
        # No manifest, no container — silent no-op, exit 0.
        rc = cli._cmd_stop(repo, _args("stop"))
        assert rc == 0


class TestRestart:
    def test_stop_then_start(self, repo, capsys):
        cli._cmd_init(repo, _args("init"))
        with patch.object(manager, "stop", return_value=True), \
             patch.object(manager, "container_exists", return_value=False), \
             patch.object(manager, "_docker_run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=(), returncode=0, stdout="", stderr="")
            rc = cli._cmd_restart(repo, _args("restart"))
        assert rc == 0
        mock_run.assert_called_once()


class TestStatus:
    def test_no_manifest_suggests_init(self, repo, capsys):
        rc = cli._cmd_status(repo, _args("status"))
        assert rc == 0
        out = capsys.readouterr().err
        assert "No manifest" in out
        assert "init" in out

    def test_status_with_manifest(self, repo, capsys):
        cli._cmd_init(repo, _args("init"))
        data = manifest.load(repo)
        data["container_name"] = "x"
        data["mcp_port"] = 8330
        data["ui_port"] = 9749
        manifest.save(repo, data)
        with patch.object(manager, "container_exists", return_value=False):
            rc = cli._cmd_status(repo, _args("status"))
        assert rc == 0
        out = capsys.readouterr().err
        assert "project:" in out
        assert "path:" in out
        assert "MCP:" in out
        assert "UI:" in out
        assert "memory:" in out
        assert "cache:" in out
        assert "related:" in out
        assert "hybrid LSP:" in out
        assert "auto-index:" in out

    def test_status_with_related_paths(self, repo, capsys):
        cli._cmd_init(repo, _args("init"))
        data = manifest.load(repo)
        data["container_name"] = "x"
        data["related_paths"] = [{"path": "/a"}, {"path": "/b"}]
        manifest.save(repo, data)
        with patch.object(manager, "container_exists", return_value=False):
            cli._cmd_status(repo, _args("status"))
        out = capsys.readouterr().err
        assert "2 path(s)" in out


class TestReset:
    def test_reset_full(self, repo, capsys):
        cli._cmd_init(repo, _args("init"))
        with patch.object(manager, "container_exists", return_value=False), \
             patch.object(manager, "reset") as mock_reset:
            rc = cli._cmd_reset(repo, _args("reset"))
        assert rc == 0
        mock_reset.assert_called_once_with(repo, keep_manifest=False, keep_cache=False)

    def test_reset_keep_flags(self, repo, capsys):
        cli._cmd_init(repo, _args("init"))
        with patch.object(manager, "container_exists", return_value=False), \
             patch.object(manager, "reset") as mock_reset:
            cli._cmd_reset(repo, _args("reset", keep_manifest=True, keep_cache=True))
        mock_reset.assert_called_once_with(repo, keep_manifest=True, keep_cache=True)

    def test_reset_no_manifest(self, repo, capsys):
        rc = cli._cmd_reset(repo, _args("reset"))
        assert rc == 0
        out = capsys.readouterr().err
        assert "No manifest" in out


class TestLogs:
    def test_logs_calls_docker_logs(self, repo, monkeypatch):
        cli._cmd_init(repo, _args("init"))
        data = manifest.load(repo)
        data["container_name"] = "codefreedom-tools-codebase-memory-proj"
        manifest.save(repo, data)
        with patch.object(manager, "container_exists", return_value=True), \
             patch("codebase_memory.cli.subprocess.call", return_value=0) as mock_call:
            rc = cli._cmd_logs(repo, _args("logs"))
        assert rc == 0
        cmd = mock_call.call_args.args[0]
        assert cmd[0] == "docker"
        assert "logs" in cmd
        assert "codefreedom-tools-codebase-memory-proj" in cmd

    def test_logs_follow_flag(self, repo):
        cli._cmd_init(repo, _args("init"))
        data = manifest.load(repo)
        data["container_name"] = "x"
        manifest.save(repo, data)
        with patch.object(manager, "container_exists", return_value=True), \
             patch("codebase_memory.cli.subprocess.call", return_value=0) as mock_call:
            cli._cmd_logs(repo, _args("logs", follow=True))
        cmd = mock_call.call_args.args[0]
        assert "-f" in cmd

    def test_logs_no_container(self, repo, capsys):
        cli._cmd_init(repo, _args("init"))
        with patch.object(manager, "container_exists", return_value=False):
            rc = cli._cmd_logs(repo, _args("logs"))
        assert rc == 1


class TestCompact:
    def test_compact(self, repo, capsys):
        cli._cmd_init(repo, _args("init"))
        with patch("codebase_memory.cli._compact.compact") as mock_compact:
            mock_compact.return_value = type(
                "S", (), {"results": [], "cache_dir": repo, "container_was_running": False, "artifact_path": None, "artifact_bytes": 0}
            )()
            rc = cli._cmd_compact(repo, _args("compact"))
        assert rc == 0
        mock_compact.assert_called_once_with(repo, write_artifact=False)

    def test_compact_with_artifact(self, repo, capsys):
        cli._cmd_init(repo, _args("init"))
        with patch("codebase_memory.cli._compact.compact") as mock_compact:
            mock_compact.return_value = type(
                "S", (), {"results": [], "cache_dir": repo, "container_was_running": False, "artifact_path": None, "artifact_bytes": 0}
            )()
            cli._cmd_compact(repo, _args("compact", artifact=True))
        mock_compact.assert_called_once_with(repo, write_artifact=True)


class TestRunDispatch:

    def test_unknown_verb_returns_2(self, repo, capsys):
        args = _args(cbmem_action="bogus")
        rc = cli.run(args)
        assert rc == 2

    def test_status_is_default(self, repo, capsys):
        args = argparse.Namespace()  # no cbmem_action
        with patch.object(cli, "_cmd_status", return_value=0) as mock_status:
            rc = cli.run(args)
        assert rc == 0
        mock_status.assert_called_once()

    def test_not_in_git_repo_returns_1(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)  # not a git repo
        args = _args("status")
        rc = cli.run(args)
        assert rc == 1
        out = capsys.readouterr().err
        assert "git" in out.lower()


class TestAddSubparser:
    def test_subparser_added(self):
        import argparse
        p = argparse.ArgumentParser()
        sub = p.add_subparsers()
        result = cli.add_subparser(sub)
        assert result is not None
        # Help message should mention the verbs.
        help_text = result.format_help()
        assert "init" in help_text
        assert "start" in help_text
        assert "stop" in help_text
        assert "compact" in help_text
