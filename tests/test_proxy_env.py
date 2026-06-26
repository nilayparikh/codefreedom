"""Tests for ``core.proxy_env`` — proxy compose env precedence.

Regression tests for the bug where a stray ``SUFFIX_ID`` already present in
the shell environment silently won over the user's ``override.yaml``
``vars.SUFFIX_ID`` value, producing ``litellm-codefreedom-0000`` even when
``SUFFIX_ID: "windemo"`` was configured.

Marker: integration (writes YAML to ``tmp_path``-scoped ``CODEFREEDOM_HOME``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from codefreedom.core.proxy_env import (
    _DEFAULT_SUFFIX_ID,
    build_proxy_run_env,
    litellm_container_name,
)

pytestmark = pytest.mark.integration


def _write_config(cf_home: Path, overrides: dict | None = None) -> None:
    """Write a minimal profiles.yaml + optional override.yaml into cf_home/config."""
    config_dir = cf_home / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "profiles.yaml").write_text(
        yaml.safe_dump(
            {
                "agents": {"claude-code": {"profiles": {"default": {"env": {}}}}},
                "tools": {"chrome": {}, "web": {}, "github": {}, "web-bridge": {}, "git": {}},
                "common": {
                    "proxy": {"bind_host": "127.0.0.1", "bind_port": 4000},
                    "suffix_id": "${SUFFIX_ID:-0000}",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    if overrides is not None:
        (config_dir / "override.yaml").write_text(
            yaml.safe_dump(overrides, sort_keys=False), encoding="utf-8"
        )


def test_override_yaml_suffix_id_wins_over_bare_os_environ(monkeypatch, tmp_path):
    """The reported bug: override.yaml SUFFIX_ID=windemo, stray SUFFIX_ID=0000 in shell."""
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_config(cf_home, overrides={"vars": {"SUFFIX_ID": "windemo"}})
    # Leak a stale SUFFIX_ID from a previous session (this reproduces the report).
    monkeypatch.setenv("SUFFIX_ID", "0000")

    env = build_proxy_run_env()

    assert env["SUFFIX_ID"] == "windemo"
    assert env["COMPOSE_PROJECT_NAME"] == "codefreedom-windemo"
    assert litellm_container_name(env) == "litellm-codefreedom-windemo"


def test_cf_cli_suffix_id_wins_over_override_yaml(monkeypatch, tmp_path):
    """CF_CLI_* is the absolute highest precedence."""
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_config(cf_home, overrides={"vars": {"SUFFIX_ID": "override-sfx"}})
    monkeypatch.setenv("SUFFIX_ID", "leaked-shell")
    monkeypatch.setenv("CF_CLI_SUFFIX_ID", "cli-sfx")

    env = build_proxy_run_env()

    assert env["SUFFIX_ID"] == "cli-sfx"
    assert env["COMPOSE_PROJECT_NAME"] == "codefreedom-cli-sfx"


def test_falls_back_to_default_and_warns_on_config_error(monkeypatch, tmp_path):
    """ConfigError no longer silently masks as '0000' — defaults are documented."""
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    # No config files written — load_config will raise (required profiles.yaml missing).

    env = build_proxy_run_env()

    assert env["SUFFIX_ID"] == _DEFAULT_SUFFIX_ID
    assert env["LITELLM_BIND_HOST"] == "127.0.0.1"
    assert env["LITELLM_PORT"] == "4000"
    assert env["COMPOSE_PROJECT_NAME"] == "codefreedom-" + _DEFAULT_SUFFIX_ID


def test_cli_port_host_flags_reflected_in_proxy_url(monkeypatch, tmp_path):
    """CF_CLI_LITELLM_* reflected in PROXY_PUBLIC_BASE_URL."""
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_config(cf_home)
    monkeypatch.setenv("CF_CLI_LITELLM_BIND_HOST", "0.0.0.0")
    monkeypatch.setenv("CF_CLI_LITELLM_PORT", "4300")

    env = build_proxy_run_env()

    assert env["LITELLM_BIND_HOST"] == "0.0.0.0"
    assert env["LITELLM_PORT"] == "4300"
    assert env["PROXY_PUBLIC_BASE_URL"] == "http://0.0.0.0:4300"


def test_litellm_container_name_no_double_suffix(monkeypatch, tmp_path):
    """On restart, base already carrying the suffix isn't suffixed again."""
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_config(cf_home, overrides={"vars": {"SUFFIX_ID": "windemo"}})

    env = build_proxy_run_env()
    name1 = litellm_container_name(env)
    assert name1 == "litellm-codefreedom-windemo"

    env["LITELLM_CONTAINER_NAME"] = name1
    name2 = litellm_container_name(env)
    assert name2 == "litellm-codefreedom-windemo"