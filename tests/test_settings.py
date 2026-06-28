"""Tests for the Phase A typed settings seam."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from codefreedom.cli.run import proxy as proxy_module
from codefreedom.config.runtime import (
    CodeFreedomSettings,
    load_codefreedom_settings,
    resolve_agent_runtime,
    resolve_config_value,
)


def test_load_codefreedom_settings_defaults(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path / ".codefreedom"))
    settings = load_codefreedom_settings(tmp_path)
    assert settings.proxy.bind_host == "0.0.0.0"
    assert settings.proxy.bind_port == 4000
    assert settings.proxy.public_base_url == "http://0.0.0.0:4000"


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


def _write_profiles(cf_dir: Path, data: dict) -> None:
    (cf_dir / "config" / "profiles.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )


def test_resolve_agent_runtime_surfaces_schema_error_loudly(
    monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Genuine schema errors are now surfaced, not silently swallowed.

    Regression: ``resolve_agent_runtime`` used to ``except ConfigError:``
    and return an empty runtime without any diagnostic, so config drift
    degraded silently — agents launched with no proxy/models and the
    user saw an opaque 401 from the proxy. The fix surfaces a
    ``[CONFIG]`` message and records ``schema_error``.
    """
    cf_dir = tmp_path / ".codefreedom"
    (cf_dir / "config").mkdir(parents=True)
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_dir))
    _write_profiles(cf_dir, {
        "agents": {
            "claude-code": {
                "profiles": {
                    "default": {
                        "env": {"KEY": "val"},
                        "bogus_field": "x",
                    },
                },
            },
        },
    })

    runtime = resolve_agent_runtime(
        "claude-code", workspace_dir=tmp_path, profile_name="default", mode="local"
    )

    assert runtime.profile_env == {}
    assert runtime.tools == []
    assert runtime.schema_error != ""
    out = capsys.readouterr().err
    assert "[CONFIG]" in out or "CONFIG" in out


def test_resolve_agent_runtime_proxy_api_key_fallback_from_cf_cli(
    monkeypatch, tmp_path: Path
) -> None:
    """PROXY_API_KEY falls back to ``CF_CLI_LITELLM_MASTER_KEY``.

    When the profile env lacks ``PROXY_API_KEY`` (e.g. legacy config
    without the ``common.proxy.env`` block), the safety net must inject
    it from ``CF_CLI_LITELLM_MASTER_KEY`` so the agent can authenticate
    to the proxy. Without this, MiMoCode hit the proxy with an empty
    key and got a 401.
    """
    cf_dir = tmp_path / ".codefreedom"
    (cf_dir / "config").mkdir(parents=True)
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_dir))
    monkeypatch.setenv("CF_CLI_LITELLM_MASTER_KEY", "sk-fallback-123")
    _write_profiles(cf_dir, {
        "agents": {"mimo-code": {"profiles": {"default": {"env": {"X": "1"}}}}},
    })

    runtime = resolve_agent_runtime(
        "mimo-code", workspace_dir=tmp_path, profile_name="default", mode="local"
    )

    assert runtime.schema_error == ""
    assert runtime.profile_env["PROXY_API_KEY"] == "sk-fallback-123"


def test_resolve_agent_runtime_with_legacy_sandbox_keys_loads_full_env(
    monkeypatch, tmp_path: Path
) -> None:
    """The exact regression scenario: legacy sandbox keys + secret.

    Before the fix, ``profiles.yaml`` carrying residual ``sandbox_*``
    keys made ``load_config`` raise, the error was swallowed, and
    ``resolve_agent_runtime`` returned an empty runtime. This left
    ``PROXY_API_KEY`` unset and agents launched with no models.
    Now the keys are stripped and the full profile resolves.
    """
    cf_dir = tmp_path / ".codefreedom"
    (cf_dir / "config").mkdir(parents=True)
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_dir))
    monkeypatch.setenv("CF_CLI_LITELLM_MASTER_KEY", "sk-test-456")
    _write_profiles(cf_dir, {
        "common": {
            "sandbox_images": {"default": "docker.io/x:latest"},
            "sandbox_env": {"IS_SANDBOX": "1"},
            "proxy": {
                "bind_host": "${LITELLM_BIND_HOST:-127.0.0.1}",
                "bind_port": "${LITELLM_PORT:-4000}",
                "env": {
                    "PROXY_BASE_URL": "${PROXY_BASE_URL}",
                    "PROXY_API_KEY": "${LITELLM_MASTER_KEY}",
                },
            },
        },
        "agents": {
            "mimo-code": {
                "profiles": {
                    "default": {
                        "env": {"MIMOCODE_MIMO_ONLY": "1"},
                        "sandbox": {"env": {"MIMOCODE_DISABLE_GIT": "0"}},
                        "sandbox_images": {"default": "docker.io/x:latest"},
                    },
                },
            },
        },
    })

    runtime = resolve_agent_runtime(
        "mimo-code", workspace_dir=tmp_path, profile_name="default", mode="local"
    )

    assert runtime.schema_error == ""
    assert runtime.profile_env["MIMOCODE_MIMO_ONLY"] == "1"
    assert runtime.profile_env["PROXY_API_KEY"] == "sk-test-456"


def test_codefreedom_settings_surfaces_schema_error(
    monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CodeFreedomSettings also surfaces config errors instead of silent pass."""
    cf_dir = tmp_path / ".codefreedom"
    (cf_dir / "config").mkdir(parents=True)
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_dir))
    _write_profiles(cf_dir, {
        "agents": {
            "claude-code": {
                "profiles": {"default": {"env": {}, "bogus_field": "x"}},
            },
        },
    })

    settings = CodeFreedomSettings()

    assert settings.proxy_bind_host == "0.0.0.0"
    assert settings.proxy_bind_port == 4000
    assert "[CONFIG]" in capsys.readouterr().err


pytestmark = pytest.mark.unit
