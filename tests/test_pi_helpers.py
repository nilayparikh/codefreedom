"""Tests for pi-code launcher helpers."""
from __future__ import annotations

import argparse
import json
import pytest
from pathlib import Path

pytestmark = pytest.mark.unit


class TestReadImageRouterModels:
    """Tests for _read_image_router_models()."""

    def test_returns_empty_list_when_no_config(self, tmp_path: Path) -> None:
        from codefreedom.cli.pi import _read_image_router_models

        result = _read_image_router_models(tmp_path)
        assert result == []

    def test_parses_image_router_config(self, tmp_path: Path) -> None:
        from codefreedom.cli.pi import _read_image_router_models

        plugin_dir = tmp_path / "proxy" / "config" / "plugins" / "image-router"
        plugin_dir.mkdir(parents=True)
        config = {
            "image-router-for-text-only": {
                "enabled": True,
                "models": ["MiMo-V2.5", "DeepSeek-V4-Flash"],
            }
        }
        (plugin_dir / "image-router.yaml").write_text(
            json.dumps(config), encoding="utf-8"
        )

        result = _read_image_router_models(tmp_path)
        assert sorted(result) == ["DeepSeek-V4-Flash", "MiMo-V2.5"]

    def test_returns_empty_when_disabled(self, tmp_path: Path) -> None:
        from codefreedom.cli.pi import _read_image_router_models

        plugin_dir = tmp_path / "proxy" / "config" / "plugins" / "image-router"
        plugin_dir.mkdir(parents=True)
        config = {
            "image-router-for-text-only": {
                "enabled": False,
                "models": ["MiMo-V2.5"],
            }
        }
        (plugin_dir / "image-router.yaml").write_text(
            json.dumps(config), encoding="utf-8"
        )

        result = _read_image_router_models(tmp_path)
        assert result == []


class TestGenerateCodefreedomExtension:
    """Tests for _generate_codefreedom_extension()."""

    def test_creates_extension_file(self, tmp_path: Path) -> None:
        from codefreedom.cli.pi import _generate_codefreedom_extension

        _generate_codefreedom_extension(tmp_path)

        ext_path = tmp_path / "extensions" / "codefreedom.ts"
        assert ext_path.exists()
        content = ext_path.read_text(encoding="utf-8")
        assert "registerProvider" in content
        assert "codefreedom" in content
        assert "PROXY_BASE_URL" in content

    def test_extension_contains_image_router_env(self, tmp_path: Path) -> None:
        from codefreedom.cli.pi import _generate_codefreedom_extension

        _generate_codefreedom_extension(tmp_path)

        ext_path = tmp_path / "extensions" / "codefreedom.ts"
        content = ext_path.read_text(encoding="utf-8")
        assert "IMAGE_ROUTER_MODELS" in content

    def test_extension_uses_model_info_endpoint(self, tmp_path: Path) -> None:
        from codefreedom.cli.pi import _generate_codefreedom_extension

        _generate_codefreedom_extension(tmp_path)

        ext_path = tmp_path / "extensions" / "codefreedom.ts"
        content = ext_path.read_text(encoding="utf-8")
        assert "/v1/model/info" in content
        assert "supports_vision" in content
        assert "supports_reasoning" in content


class TestWriteMinimalSettings:
    """Tests for _write_minimal_settings()."""

    def test_writes_settings_json(self, tmp_path: Path) -> None:
        from codefreedom.cli.pi import _write_minimal_settings

        _write_minimal_settings(tmp_path)

        settings_path = tmp_path / "settings.json"
        assert settings_path.exists()
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        assert data["defaultProvider"] == "codefreedom"
        assert data["defaultProjectTrust"] == "always"

    def test_extensions_get_npm_prefix(self, tmp_path: Path) -> None:
        from codefreedom.cli.pi import _write_minimal_settings

        _write_minimal_settings(tmp_path, extensions=["pi-mcp-adapter", "@tintinweb/pi-subagents"])
        data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert data["packages"] == ["npm:pi-mcp-adapter", "npm:@tintinweb/pi-subagents"]

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        from codefreedom.cli.pi import _write_minimal_settings

        deep_dir = tmp_path / "a" / "b" / "c"
        _write_minimal_settings(deep_dir)

        assert (deep_dir / "settings.json").exists()


class TestEnsureLeanCtx:
    """Tests for _ensure_lean_ctx()."""

    def test_skips_npm_install_when_binary_on_path(self, tmp_path: Path) -> None:
        from codefreedom.cli.pi import _ensure_lean_ctx
        from unittest.mock import patch

        with patch("shutil.which", return_value="/usr/local/bin/lean-ctx"):
            with patch("subprocess.run") as mock_run:
                _ensure_lean_ctx(tmp_path)
                mock_run.assert_not_called()

    def test_runs_npm_install_when_binary_missing(self, tmp_path: Path) -> None:
        from codefreedom.cli.pi import _ensure_lean_ctx
        from unittest.mock import patch

        with patch("shutil.which", side_effect=lambda cmd: None if cmd == "lean-ctx" else "/usr/bin/npm"):
            with patch("subprocess.run") as mock_run:
                _ensure_lean_ctx(tmp_path)
                # Should call npm install -g lean-ctx-bin
                mock_run.assert_any_call(
                    ["npm", "install", "-g", "lean-ctx-bin"],
                    check=True,
                    capture_output=True,
                    timeout=120,
                )


class TestEnsureLspServers:
    """Verify LSP server detection handles package/binary mismatches."""

    def test_pylsp_not_reinstalled_when_present(self, monkeypatch):
        """python-lsp-server[all] should check for 'pylsp', not 'python-lsp-server'."""
        import codefreedom.cli.pi as pi_mod

        installed = {"pylsp", "typescript-language-server"}

        def fake_which(name):
            return "/usr/bin/" + name if name in installed else None

        monkeypatch.setattr("shutil.which", fake_which)

        npm_calls = []
        pip_calls = []

        def fake_subprocess_run(cmd, **kwargs):
            if cmd[0] == "npm":
                npm_calls.append(cmd)
            elif cmd[0] == "pip":
                pip_calls.append(cmd)

        monkeypatch.setattr("subprocess.run", fake_subprocess_run)

        lsp_servers = {
            "npm": ["typescript-language-server"],
            "pip": ["python-lsp-server[all]"],
        }
        pi_mod._ensure_lsp_servers(lsp_servers)

        assert pip_calls == [], f"Expected no pip install, got {pip_calls}"

    def test_vscode_langservers_not_reinstalled(self, monkeypatch):
        """vscode-langservers-extracted installs multiple binaries, not one matching the package name."""
        import codefreedom.cli.pi as pi_mod

        installed = {"vscode-langservers-extracted"}

        def fake_which(name):
            return "/usr/bin/" + name if name in installed else None

        monkeypatch.setattr("shutil.which", fake_which)

        npm_calls = []

        def fake_subprocess_run(cmd, **kwargs):
            if cmd[0] == "npm":
                npm_calls.append(cmd)

        monkeypatch.setattr("subprocess.run", fake_subprocess_run)

        lsp_servers = {"npm": ["vscode-langservers-extracted"]}
        pi_mod._ensure_lsp_servers(lsp_servers)

        assert npm_calls == [], f"Expected no npm install, got {npm_calls}"


class TestPiEnvLoading:
    """Verify pi-code loads its own component env files."""

    def test_cmd_config_uses_pi_component(self, tmp_path, monkeypatch):
        """cmd_config must load component='pi', not 'claude'."""
        import codefreedom.cli.pi as pi_mod

        calls = []

        def fake_load_env_chain(workspace_dir, *, component=None, verbose=True):
            calls.append(component)
            return {}

        monkeypatch.setattr(pi_mod, "load_env_chain", fake_load_env_chain)
        monkeypatch.setattr(
            pi_mod, "_detect_proxy_url", lambda env: "http://localhost:4000"
        )

        ns = argparse.Namespace(profile="default")
        pi_mod.cmd_config(ns)
        assert calls == ["pi"], f"Expected component='pi', got {calls}"

    def test_run_uses_pi_component(self, tmp_path, monkeypatch):
        """run() must load component='pi', not 'claude'."""
        import codefreedom.cli.pi as pi_mod

        calls = []

        def fake_load_env_chain(workspace_dir, *, component=None, verbose=True):
            calls.append(component)
            return {}

        monkeypatch.setattr(pi_mod, "load_env_chain", fake_load_env_chain)
        monkeypatch.setattr(pi_mod, "find_pi_binary", lambda: "/usr/bin/pi")
        monkeypatch.setattr(
            pi_mod, "_detect_proxy_url", lambda env: "http://localhost:4000"
        )

        import codefreedom.cli.common as common_mod
        monkeypatch.setattr(
            common_mod,
            "load_profile_with_tools",
            lambda name, path, env, mode: ({}, [], [], 0),
        )
        monkeypatch.setattr(
            common_mod,
            "acquire_and_run",
            lambda sid, tools, name, fn: 0,
        )

        ns = argparse.Namespace(
            list_profiles=False, profile="default", pi_action=None, agent_args=[]
        )
        pi_mod.run(ns)
        assert calls == ["pi"], f"Expected component='pi', got {calls}"
