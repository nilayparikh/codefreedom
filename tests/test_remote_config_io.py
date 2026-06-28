from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from codefreedom.cli.setup.config import handle_args
from codefreedom.cli.run.proxy import _configured_remote_proxy_url
from codefreedom.cli.run.tools import _remote_tools
from codefreedom.tools.registry import load_tool_mcp_endpoints

pytestmark = pytest.mark.integration


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def _base_profiles() -> dict:
    return {
        "common": {
            "bind_address": "0.0.0.0",
            "proxy": {"bind_host": "${common.bind_address}", "bind_port": 4000},
            "suffix_id": "${SUFFIX_ID:-0000}",
        },
        "agents": {"claude-code": {"profiles": {"default": {"tools": ["chrome", "web"]}}}},
        "tools": {
            "chrome": {"port": 9222, "mcp_port": 9223, "mcp_path": "/mcp"},
            "web": {"port": 8420, "mcp_path": "/mcp"},
            "github": {},
            "web-bridge": {},
            "git": {},
        },
    }


def test_setup_config_proxy_remote_updates_override(monkeypatch, tmp_path):
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_yaml(cf_home / "config" / "profiles.yaml", _base_profiles())

    class Args:
        config_target = "proxy"
        remote_url = "http://m1.local:4000"
        local = False
        bind = None

    assert handle_args(Args()) == 0
    assert _configured_remote_proxy_url() == "http://m1.local:4000"


def test_setup_config_tool_remote_updates_override(monkeypatch, tmp_path):
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_yaml(cf_home / "config" / "profiles.yaml", _base_profiles())

    class Args:
        config_target = "tools"
        tool = "chrome"
        remote_url = "http://m1.local:9223/mcp"
        local = False
        bind = None

    assert handle_args(Args()) == 0
    assert _remote_tools({"chrome"}) == {"chrome": "http://m1.local:9223/mcp"}
    endpoints = load_tool_mcp_endpoints(["chrome"])
    assert endpoints["mcpServers"]["chrome-devtools"]["url"] == "http://m1.local:9223/mcp"


def test_setup_config_bind_updates_common_bind_address(monkeypatch, tmp_path):
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_yaml(cf_home / "config" / "profiles.yaml", _base_profiles())

    class Args:
        config_target = "bind"
        address = "127.0.0.1"

    assert handle_args(Args()) == 0

    with open(cf_home / "config" / "override.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert data["common"]["bind_address"] == "127.0.0.1"
