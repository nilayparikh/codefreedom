"""Tests for proxy CLI — path resolution, validation, compose discovery."""

import argparse
from pathlib import Path

import yaml

from codefreedom.cli.proxy import (
    _find_compose_file,
    _find_config_file,
    _validate,
    _validate_basic,
    _env_is_set,
    run,
)

_FAKE_CF_DIR = Path("/nonexistent/.codefreedom")


class TestFindComposeFile:
    """Tests for _find_compose_file — only ~/.codefreedom/proxy/."""

    def test_finds_in_codefreedom_dir(self, monkeypatch, tmp_path):
        compose = tmp_path / "proxy" / "docker-compose.yaml"
        compose.parent.mkdir(parents=True)
        compose.write_text("")
        monkeypatch.setattr(
            "codefreedom.cli.proxy.get_codefreedom_dir", lambda: tmp_path
        )
        result = _find_compose_file()
        assert result == compose

    def test_returns_none_when_not_found(self, monkeypatch):
        monkeypatch.setattr(
            "codefreedom.cli.proxy.get_codefreedom_dir", lambda: Path("/nonexistent")
        )
        result = _find_compose_file()
        assert result is None


class TestFindConfigFile:
    """Tests for _find_config_file — only ~/.codefreedom/proxy/config/."""

    def test_finds_in_codefreedom_dir(self, monkeypatch, tmp_path):
        config = tmp_path / "proxy" / "config" / "config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text("")
        monkeypatch.setattr(
            "codefreedom.cli.proxy.get_codefreedom_dir", lambda: tmp_path
        )
        result = _find_config_file()
        assert result == config

    def test_returns_none_when_not_found(self, monkeypatch):
        monkeypatch.setattr(
            "codefreedom.cli.proxy.get_codefreedom_dir", lambda: Path("/nonexistent")
        )
        result = _find_config_file()
        assert result is None


class TestValidate:
    """Tests for _validate — config validation."""

    def test_valid_config_passes(self, monkeypatch, tmp_path):
        _write_proxy_config(
            tmp_path,
            {
                "include": [],
                "general_settings": {},
                "router_settings": {"model_group_alias": {}},
                "litellm_settings": {},
            },
        )
        monkeypatch.setattr(
            "codefreedom.cli.proxy.get_codefreedom_dir", lambda: tmp_path
        )
        result = _validate()
        assert result == 0

    def test_missing_config_file(self, monkeypatch):
        monkeypatch.setattr(
            "codefreedom.cli.proxy.get_codefreedom_dir", lambda: Path("/nonexistent")
        )
        result = _validate()
        assert result == 1

    def test_yaml_parse_error(self, monkeypatch, tmp_path):
        _write_proxy_config(tmp_path, {})
        config_path = tmp_path / "proxy" / "config" / "config.yaml"
        config_path.write_text(": invalid yaml : :")
        monkeypatch.setattr(
            "codefreedom.cli.proxy.get_codefreedom_dir", lambda: tmp_path
        )
        result = _validate()
        assert result == 1

    def test_missing_provider_file_reported(self, monkeypatch, tmp_path):
        _write_proxy_config(
            tmp_path,
            {
                "include": ["providers/missing.yaml"],
                "general_settings": {},
                "router_settings": {},
                "litellm_settings": {},
            },
        )
        monkeypatch.setattr(
            "codefreedom.cli.proxy.get_codefreedom_dir", lambda: tmp_path
        )
        result = _validate()
        assert result == 1  # missing provider = validation failure


class TestValidateBasic:
    """Tests for _validate_basic (no PyYAML fallback)."""

    def test_finds_required_sections(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "include:\ngeneral_settings:\nrouter_settings:\nlitellm_settings:\nmodel_group_alias:\n"
        )
        errors = []
        _validate_basic(config, errors)
        assert len(errors) == 0

    def test_reports_missing_sections(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text("")
        errors = []
        _validate_basic(config, errors)
        assert len(errors) > 0


class TestEnvIsSet:
    """Tests for _env_is_set."""

    def test_set_var(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "value")
        assert _env_is_set("TEST_VAR") is True

    def test_unset_var(self):
        assert _env_is_set("NONEXISTENT_VAR") is False

    def test_empty_var(self, monkeypatch):
        monkeypatch.setenv("EMPTY_VAR", "")
        assert _env_is_set("EMPTY_VAR") is True


class TestRun:
    """Tests for the run() entry point."""

    def test_no_action_shows_help(self):
        args = argparse.Namespace(
            action="invalid",
            reset=False,
            docker=False,
            port=4000,
            host="0.0.0.0",
        )
        result = run(args)
        assert result == 1

    def test_start_docker_compose_not_found(self, monkeypatch):
        args = argparse.Namespace(
            action="start",
            reset=False,
            docker=True,
            port=4000,
            host="0.0.0.0",
        )
        monkeypatch.setattr("codefreedom.cli.proxy._find_compose_file", lambda: None)
        result = run(args)
        assert result == 1  # docker compose file not found

    def test_start_native_config_not_found(self, monkeypatch):
        args = argparse.Namespace(
            action="start",
            reset=False,
            docker=False,
            port=4000,
            host="0.0.0.0",
        )
        monkeypatch.setattr("codefreedom.cli.proxy._find_config_file", lambda: None)
        result = run(args)
        assert result == 1  # config file not found (native mode)


# ── helpers ──────────────────────────────────────────────────────────────────


def _write_proxy_config(tmp_path: Path, data: dict) -> Path:
    config_dir = tmp_path / "proxy" / "config"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "config.yaml"
    config_file.write_text(yaml.dump(data))
    return config_file
