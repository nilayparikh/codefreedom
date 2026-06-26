"""Tests for the Phase A typed settings seam."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from codefreedom.cli.run import proxy as proxy_module
from codefreedom.config.runtime import (
    load_codefreedom_settings,
    resolve_agent_runtime,
    resolve_config_value,
)


def test_load_codefreedom_settings_defaults(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path / ".codefreedom"))
    settings = load_codefreedom_settings(tmp_path)
    assert settings.proxy.bind_host == "127.0.0.1"
    assert settings.proxy.bind_port == 4000
    assert settings.proxy.public_base_url == "http://127.0.0.1:4000"


def test_load_codefreedom_settings_env_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path / ".codefreedom"))
    monkeypatch.setenv("CF_CLI_LITELLM_BIND_HOST", "0.0.0.0")
    monkeypatch.setenv("CF_CLI_LITELLM_PORT", "4100")
    settings = load_codefreedom_settings(tmp_path)
    assert settings.proxy.bind_host == "0.0.0.0"
    assert settings.proxy.bind_port == 4100
    assert settings.proxy.public_base_url == "http://0.0.0.0:4100"


def test_proxy_provenance_reports_env_source(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path / ".codefreedom"))
    monkeypatch.setenv("CF_CLI_LITELLM_PORT", "4200")
    settings = load_codefreedom_settings(tmp_path)
    provenance = settings.proxy_provenance()
    assert provenance["bind_port"].value == "4200"
    assert provenance["bind_port"].source == "CF_CLI_*:LITELLM_PORT"


def test_build_proxy_env_uses_canonical_proxy_settings(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path / ".codefreedom"))
    monkeypatch.setenv("CF_CLI_LITELLM_BIND_HOST", "0.0.0.0")
    monkeypatch.setenv("CF_CLI_LITELLM_PORT", "4300")
    monkeypatch.chdir(tmp_path)
    env = proxy_module._build_proxy_env()
    assert env["LITELLM_BIND_HOST"] == "0.0.0.0"
    assert env["LITELLM_PORT"] == "4300"
    assert env["PROXY_PUBLIC_BASE_URL"] == "http://0.0.0.0:4300"


def test_resolve_agent_runtime_uses_agent_component(
    monkeypatch, tmp_path: Path
) -> None:
    cf_dir = tmp_path / ".codefreedom"
    config_dir = cf_dir / "config"
    config_dir.mkdir(parents=True)
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_dir))

    monkeypatch.setenv("CF_CLI_SPECIAL_COMPONENT", "from_mimo")
    (config_dir / "profiles.yaml").write_text(
        yaml.safe_dump(
            {
                "agents": {
                    "mimo-code": {
                        "profiles": {
                            "default": {
                                "description": "default",
                                "tools": ["github"],
                                "env": {"SEEN_COMPONENT": "${SPECIAL_COMPONENT}"},
                            }
                        }
                    }
                },
                "tools": {
                    "github": {"image": "ghcr.io/github/github-mcp-server"},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    runtime = resolve_agent_runtime(
        "mimo-code", workspace_dir=tmp_path, profile_name="default", mode="local"
    )

    assert runtime.profile_env["SEEN_COMPONENT"] == "from_mimo"
    assert runtime.tools == ["github"]


def test_resolve_config_value_uses_common_precedence(
    monkeypatch, tmp_path: Path
) -> None:
    cf_dir = tmp_path / ".codefreedom"
    cf_dir.mkdir(parents=True)
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_dir))

    value, source = resolve_config_value(
        "MY_VAR",
        workspace_dir=tmp_path,
    )
    assert value is None
    assert source is None

    monkeypatch.setenv("CF_CLI_MY_VAR", "cf-cli-value")
    value, source = resolve_config_value(
        "MY_VAR",
        workspace_dir=tmp_path,
    )
    assert value == "cf-cli-value"
    assert source == "CF_CLI_* override"
pytestmark = pytest.mark.unit
