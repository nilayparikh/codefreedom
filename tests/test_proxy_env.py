"""Tests for ``core.proxy_env`` — proxy compose env precedence.

Regression tests for the bug where a stray ``SUFFIX_ID`` already present in
the shell environment silently won over the user's ``override.yaml``
``vars.SUFFIX_ID`` value, producing ``codefreedom-proxy-0000`` even when
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
    proxy_container_name,
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
                    "proxy": {"bind_host": "0.0.0.0", "bind_port": 4000},
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
    assert proxy_container_name(env) == "codefreedom-proxy-windemo"


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
    assert env["PROXY_BIND_HOST"] == "0.0.0.0"
    assert env["PROXY_PORT"] == "4000"
    assert env["COMPOSE_PROJECT_NAME"] == "codefreedom-" + _DEFAULT_SUFFIX_ID


def test_cli_port_host_flags_reflected_in_proxy_url(monkeypatch, tmp_path):
    """CF_CLI_PROXY_* reflected in PROXY_PUBLIC_BASE_URL."""
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_config(cf_home)
    monkeypatch.setenv("CF_CLI_PROXY_BIND_HOST", "0.0.0.0")
    monkeypatch.setenv("CF_CLI_PROXY_PORT", "4300")

    env = build_proxy_run_env()

    assert env["PROXY_BIND_HOST"] == "0.0.0.0"
    assert env["PROXY_PORT"] == "4300"
    assert env["PROXY_PUBLIC_BASE_URL"] == "http://0.0.0.0:4300"


def test_proxy_container_name_no_double_suffix(monkeypatch, tmp_path):
    """On restart, base already carrying the suffix isn't suffixed again."""
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_config(cf_home, overrides={"vars": {"SUFFIX_ID": "windemo"}})

    env = build_proxy_run_env()
    name1 = proxy_container_name(env)
    assert name1 == "codefreedom-proxy-windemo"

    env["PROXY_CONTAINER_NAME"] = name1
    name2 = proxy_container_name(env)
    assert name2 == "codefreedom-proxy-windemo"


def test_override_yaml_vars_exported_to_compose_env(monkeypatch, tmp_path):
    """vars from override.yaml are exported so docker-compose ${VAR} sees them.

    Regression for the bug where ``cf m dr`` displayed a var (e.g.
    ``OPENCODE_SUB_ROUTING_ORDER``) but ``cf r px`` never injected it into
    the ``docker compose`` subprocess, so the proxy container used the
    hardcoded literal from docker-compose.yaml instead.
    """
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_config(
        cf_home,
        overrides={
            "vars": {
                "OPENCODE_SUB_ROUTING_ORDER": "5",
                "CLINE_SUB_ROUTING_ORDER": "7",
                "OPENROUTER_BASE_URL": "https://custom.openrouter.example/v1",
            }
        },
    )

    env = build_proxy_run_env()

    assert env["OPENCODE_SUB_ROUTING_ORDER"] == "5"
    assert env["CLINE_SUB_ROUTING_ORDER"] == "7"
    assert env["OPENROUTER_BASE_URL"] == "https://custom.openrouter.example/v1"


def test_cf_yaml_vars_exported_to_compose_env(monkeypatch, tmp_path):
    """vars from a per-folder .cf.yaml are exported to the compose env."""
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_config(cf_home)
    # Write a .cf.yaml in the cwd and point CF_CLI_CF_YAML at it.
    cf_yaml = tmp_path / ".cf.yaml"
    cf_yaml.write_text(
        yaml.safe_dump(
            {"vars": {"OPENCODE_SUB_ROUTING_ORDER": "3", "SUFFIX_ID": "cfyaml"}},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CF_CLI_CF_YAML", str(cf_yaml))
    monkeypatch.chdir(tmp_path)

    env = build_proxy_run_env()

    assert env["OPENCODE_SUB_ROUTING_ORDER"] == "3"
    # SUFFIX_ID from .cf.yaml flows through for_component -> structured field.
    assert env["SUFFIX_ID"] == "cfyaml"
    assert env["COMPOSE_PROJECT_NAME"] == "codefreedom-cfyaml"


def test_structured_proxy_fields_win_over_flat_vars(monkeypatch, tmp_path):
    """common.proxy.bind_port wins over a vars.PROXY_PORT of the same name.

    Ensures the merge order is: os.environ < vars < for_component("proxy")
    < CF_CLI_*. A flat var must not shadow the structured proxy field.
    """
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_config(
        cf_home,
        overrides={
            "vars": {"PROXY_PORT": "4000"},
            "common": {"proxy": {"bind_host": "0.0.0.0", "bind_port": 5000}},
        },
    )

    env = build_proxy_run_env()

    assert env["PROXY_PORT"] == "5000"


def test_cf_cli_var_wins_over_override_yaml_var(monkeypatch, tmp_path):
    """CF_CLI_* overrides a var set in override.yaml."""
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_config(
        cf_home,
        overrides={"vars": {"OPENCODE_SUB_ROUTING_ORDER": "5"}},
    )
    monkeypatch.setenv("CF_CLI_OPENCODE_SUB_ROUTING_ORDER", "9")

    env = build_proxy_run_env()

    assert env["OPENCODE_SUB_ROUTING_ORDER"] == "9"
