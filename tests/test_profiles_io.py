"""Integration tests for config loading through the agent launch path.

Covers the full ``load_config`` → ``resolve_agent_runtime`` →
``load_profile_with_tools`` chain against a real config dir on disk.
These would have caught the PR #145 regression where residual sandbox
keys broke schema validation and the error was silently swallowed,
leaving agents with no proxy/models or a 401 from the proxy.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from codefreedom.cli.common import load_profile_with_tools
from codefreedom.config.runtime import resolve_agent_runtime

pytestmark = pytest.mark.integration


def _write(cf_dir: Path, name: str, data: dict) -> None:
    (cf_dir / "config" / name).write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )


def test_full_agent_path_with_legacy_sandbox_keys(
    monkeypatch, tmp_path: Path
) -> None:
    """End-to-end regression: legacy sandbox keys + secret resolve fully.

    Reproduces the user-reported scenario: ``profiles.yaml`` written by
    an older recipe still carries ``common.sandbox_images`` /
    ``common.sandbox_env`` / per-profile ``sandbox``. With
    ``CF_CLI_LITELLM_MASTER_KEY`` set, the agent runtime must resolve
    ``PROXY_API_KEY`` and ``PROXY_BASE_URL`` so MiMoCode can reach the
    proxy (no 401) and Claude Code loads the proxy model list.
    """
    cf_dir = tmp_path / ".codefreedom"
    (cf_dir / "config").mkdir(parents=True)
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_dir))
    monkeypatch.setenv("CF_CLI_LITELLM_MASTER_KEY", "sk-int-789")
    monkeypatch.setenv("CF_CLI_LITELLM_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("CF_CLI_LITELLM_PORT", "4000")
    _write(cf_dir, "profiles.yaml", {
        "common": {
            "sandbox_images": {
                "default": "docker.io/x:latest",
                "cuda": "docker.io/x:cuda-latest",
            },
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
            "claude-code": {
                "profiles": {
                    "default": {
                        "env": {
                            "ANTHROPIC_BASE_URL": "${PROXY_BASE_URL}",
                            "ANTHROPIC_AUTH_TOKEN": "${LITELLM_MASTER_KEY}",
                        },
                    },
                },
            },
        },
    })
    _write(cf_dir, "recipe.yaml", {
        "name": "test",
        "vars": [{"PROXY_BASE_URL": "http://${LITELLM_BIND_HOST}:${LITELLM_PORT}"}],
    })

    runtime = resolve_agent_runtime(
        "mimo-code", workspace_dir=tmp_path, profile_name="default", mode="local"
    )

    assert runtime.schema_error == ""
    assert runtime.profile_env["PROXY_API_KEY"] == "sk-int-789"
    assert runtime.profile_env["MIMOCODE_MIMO_ONLY"] == "1"

    cc = resolve_agent_runtime(
        "claude-code", workspace_dir=tmp_path, profile_name="default", mode="local"
    )
    assert cc.schema_error == ""
    assert cc.profile_env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:4000"
    assert cc.profile_env["ANTHROPIC_AUTH_TOKEN"] == "sk-int-789"

    profile_env, tools, exit_code = load_profile_with_tools(
        "default", cf_dir / "config" / "profiles.yaml", {}, "local", agent="mimo-code"
    )
    assert exit_code == 0
    assert profile_env.get("PROXY_API_KEY") == "sk-int-789"


def test_full_agent_path_schema_error_surfaces_and_degrades(
    monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Genuine schema drift surfaces loudly instead of silent empty runtime.

    Integration counterpart to the unit test: a config with a real schema
    violation (not covered by the normalizer) must surface a ``[CONFIG]``
    message and return an empty runtime rather than silently launching
    with no models.
    """
    cf_dir = tmp_path / ".codefreedom"
    (cf_dir / "config").mkdir(parents=True)
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_dir))
    _write(cf_dir, "profiles.yaml", {
        "agents": {
            "mimo-code": {
                "profiles": {
                    "default": {"env": {"X": "1"}, "bogus_field": "y"},
                },
            },
        },
    })

    runtime = resolve_agent_runtime(
        "mimo-code", workspace_dir=tmp_path, profile_name="default", mode="local"
    )

    assert runtime.schema_error != ""
    assert runtime.profile_env == {}
    assert runtime.tools == []
    err = capsys.readouterr().err
    assert "CONFIG" in err