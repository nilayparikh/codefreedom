from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from codefreedom.cli.setup.config import handle_args
from codefreedom.cli.run.proxy import _configured_remote_proxy_url, run as run_proxy
from codefreedom.cli.run.tools import _remote_tools
from codefreedom.core.agent_runtime import PROXY_OK, PROXY_UNREACHABLE
from codefreedom.launcher import _write_mcp_json
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

    monkeypatch.setattr(
        "codefreedom.cli.setup.config._probe_remote_proxy",
        lambda url, api_key="": PROXY_OK,
    )
    assert handle_args(Args()) == 0

    with open(cf_home / "config" / "override.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert data["common"]["proxy"]["remote_url"] == "http://m1.local:4000"
    assert _configured_remote_proxy_url() == "http://m1.local:4000"


def test_proxy_start_stop_disabled_when_remote_configured(monkeypatch, tmp_path):
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_yaml(cf_home / "config" / "profiles.yaml", _base_profiles())
    _write_yaml(
        cf_home / "config" / "override.yaml",
        {"common": {"proxy": {"remote_url": "http://m1.local:4000"}}},
    )

    class Args:
        action = "start"
        host = None
        port = None

    assert run_proxy(Args()) == 1

    class StopArgs:
        action = "stop"

    assert run_proxy(StopArgs()) == 1


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

    monkeypatch.setattr(
        "codefreedom.cli.setup.config._validate_remote_tool_url",
        lambda tool, url: True,
    )

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


def test_setup_config_proxy_remote_refuses_unreachable(monkeypatch, tmp_path):
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_yaml(cf_home / "config" / "profiles.yaml", _base_profiles())
    monkeypatch.setattr(
        "codefreedom.cli.setup.config._probe_remote_proxy",
        lambda url, api_key="": PROXY_UNREACHABLE,
    )

    class Args:
        config_target = "proxy"
        remote_url = "http://bad.local:4000"
        local = False
        bind = None

    assert handle_args(Args()) == 1
    assert not (cf_home / "config" / "override.yaml").exists()


def test_setup_config_tool_remote_refuses_unreachable(monkeypatch, tmp_path):
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_yaml(cf_home / "config" / "profiles.yaml", _base_profiles())
    monkeypatch.setattr(
        "codefreedom.cli.setup.config._validate_remote_tool_url",
        lambda tool, url: False,
    )

    class Args:
        config_target = "tools"
        tool = "chrome"
        remote_url = "http://bad.local:9223/mcp"
        local = False
        bind = None

    assert handle_args(Args()) == 1
    assert not (cf_home / "config" / "override.yaml").exists()


def test_setup_config_proxy_remote_accepts_localhost_portforward(monkeypatch, tmp_path):
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_yaml(cf_home / "config" / "profiles.yaml", _base_profiles())

    monkeypatch.setattr(
        "codefreedom.cli.setup.config._probe_remote_proxy",
        lambda url, api_key="": PROXY_OK,
    )

    class Args:
        config_target = "proxy"
        remote_url = "http://127.0.0.1:4000"
        local = False
        bind = None

    assert handle_args(Args()) == 0

    with open(cf_home / "config" / "override.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert data["common"]["proxy"]["remote_url"] == "http://127.0.0.1:4000"
    assert _configured_remote_proxy_url() == "http://127.0.0.1:4000"


def test_setup_config_tool_remote_accepts_localhost_portforward(monkeypatch, tmp_path):
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_yaml(cf_home / "config" / "profiles.yaml", _base_profiles())

    monkeypatch.setattr(
        "codefreedom.cli.setup.config._validate_remote_tool_url",
        lambda tool, url: True,
    )

    class Args:
        config_target = "tools"
        tool = "chrome"
        remote_url = "http://127.0.0.1:9223/mcp"
        local = False
        bind = None

    assert handle_args(Args()) == 0
    assert _remote_tools({"chrome"}) == {"chrome": "http://127.0.0.1:9223/mcp"}


def test_write_mcp_json_uses_remote_tool_url(monkeypatch, tmp_path):
    cf_home = tmp_path / ".codefreedom"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_yaml(cf_home / "config" / "profiles.yaml", _base_profiles())
    _write_yaml(
        cf_home / "config" / "override.yaml",
        {"tools": {"chrome": {"remote_url": "http://m1.local:9223/mcp"}}},
    )

    monkeypatch.setattr(
        "codefreedom.launcher.validate_remote_tools_or_raise",
        lambda tools: None,
    )

    _write_mcp_json(workspace, ["chrome"])
    data = yaml.safe_load((workspace / ".mcp.json").read_text(encoding="utf-8"))
    assert data["mcpServers"]["chrome-devtools"]["url"] == "http://m1.local:9223/mcp"


def test_agent_launch_fails_fast_when_remote_tools_invalid(monkeypatch, tmp_path):
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_yaml(cf_home / "config" / "profiles.yaml", _base_profiles())
    _write_yaml(
        cf_home / "config" / "override.yaml",
        {
            "tools": {"chrome": {"remote_url": "http://bad.local:9223/mcp"}},
            "common": {"proxy": {"remote_url": "http://m1.local:4000"}},
        },
    )
    monkeypatch.setattr("codefreedom.launcher.find_claude_binary", lambda: "/bin/true")
    monkeypatch.setattr("codefreedom.launcher.run_local", lambda *args, **kwargs: 0)
    monkeypatch.setattr("codefreedom.cli.common.acquire_and_run", lambda *args, **kwargs: kwargs["runner"](["chrome"]) if "runner" in kwargs else args[3](["chrome"]))
    from codefreedom.core.remote_validation import RemoteValidationError
    monkeypatch.setattr(
        "codefreedom.launcher.validate_remote_tools_or_raise",
        lambda tools: (_ for _ in ()).throw(RemoteValidationError("bad remote tool")),
    )

    from codefreedom.cli.claude import run

    args = SimpleNamespace(
        list_profiles=False,
        profile=None,
        native_models=False,
        dangerously_skip_permissions=False,
        agent_args=[],
    )
    assert run(args) == 1


def test_setup_config_proxy_remote_401_saves_key_from_env(monkeypatch, tmp_path):
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_yaml(cf_home / "config" / "profiles.yaml", _base_profiles())
    monkeypatch.setenv("CF_CLI_LITELLM_MASTER_KEY", "sk-test-123")

    from codefreedom.core.agent_runtime import PROXY_AUTH_REQUIRED, PROXY_OK

    probes = iter([PROXY_AUTH_REQUIRED, PROXY_OK])

    def _probe(url, api_key=""):
        return next(probes)

    monkeypatch.setattr("codefreedom.cli.setup.config._probe_remote_proxy", _probe)

    class Args:
        config_target = "proxy"
        remote_url = "http://localhost:4000"
        local = False
        bind = None

    assert handle_args(Args()) == 0

    with open(cf_home / "config" / "override.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert data["common"]["proxy"]["remote_url"] == "http://localhost:4000"
    assert data["common"]["proxy"]["env"]["LITELLM_MASTER_KEY"] == "${LITELLM_MASTER_KEY}"


def test_setup_config_proxy_remote_401_saves_key_from_prompt(monkeypatch, tmp_path):
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_yaml(cf_home / "config" / "profiles.yaml", _base_profiles())
    monkeypatch.delenv("CF_CLI_LITELLM_MASTER_KEY", raising=False)

    from codefreedom.core.agent_runtime import PROXY_AUTH_REQUIRED, PROXY_OK

    probes = iter([PROXY_AUTH_REQUIRED, PROXY_OK])

    monkeypatch.setattr(
        "codefreedom.cli.setup.config._probe_remote_proxy",
        lambda url, api_key="": next(probes),
    )
    monkeypatch.setattr(
        "codefreedom.cli.setup.config._resolve_proxy_master_key", lambda: "sk-from-prompt"
    )

    class Args:
        config_target = "proxy"
        remote_url = "http://localhost:4000"
        local = False
        bind = None

    assert handle_args(Args()) == 0

    with open(cf_home / "config" / "override.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert data["common"]["proxy"]["env"]["LITELLM_MASTER_KEY"] == "${LITELLM_MASTER_KEY}"


def test_setup_config_proxy_remote_401_rejected_key_fails(monkeypatch, tmp_path):
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_yaml(cf_home / "config" / "profiles.yaml", _base_profiles())
    monkeypatch.setenv("CF_CLI_LITELLM_MASTER_KEY", "sk-wrong")

    from codefreedom.core.agent_runtime import PROXY_AUTH_REQUIRED

    monkeypatch.setattr(
        "codefreedom.cli.setup.config._probe_remote_proxy",
        lambda url, api_key="": PROXY_AUTH_REQUIRED,
    )

    class Args:
        config_target = "proxy"
        remote_url = "http://localhost:4000"
        local = False
        bind = None

    assert handle_args(Args()) == 1
    assert not (cf_home / "config" / "override.yaml").exists()


def test_setup_config_proxy_remote_401_no_key_fails(monkeypatch, tmp_path):
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_yaml(cf_home / "config" / "profiles.yaml", _base_profiles())
    monkeypatch.delenv("CF_CLI_LITELLM_MASTER_KEY", raising=False)

    from codefreedom.core.agent_runtime import PROXY_AUTH_REQUIRED

    monkeypatch.setattr(
        "codefreedom.cli.setup.config._probe_remote_proxy",
        lambda url, api_key="": PROXY_AUTH_REQUIRED,
    )
    monkeypatch.setattr("codefreedom.cli.setup.config._resolve_proxy_master_key", lambda: None)

    class Args:
        config_target = "proxy"
        remote_url = "http://localhost:4000"
        local = False
        bind = None

    assert handle_args(Args()) == 1
    assert not (cf_home / "config" / "override.yaml").exists()


def test_setup_config_proxy_local_removes_key_marker(monkeypatch, tmp_path):
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_yaml(cf_home / "config" / "profiles.yaml", _base_profiles())
    _write_yaml(
        cf_home / "config" / "override.yaml",
        {
            "common": {
                "proxy": {
                    "remote_url": "http://localhost:4000",
                    "env": {"LITELLM_MASTER_KEY": "${LITELLM_MASTER_KEY}"},
                }
            }
        },
    )

    class Args:
        config_target = "proxy"
        remote_url = None
        local = True
        bind = None

    assert handle_args(Args()) == 0

    with open(cf_home / "config" / "override.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert "remote_url" not in data["common"]["proxy"]
    assert "LITELLM_MASTER_KEY" not in data["common"]["proxy"].get("env", {})
    assert "env" not in data["common"]["proxy"]


def test_setup_config_proxy_local_preserves_user_key(monkeypatch, tmp_path):
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    _write_yaml(cf_home / "config" / "profiles.yaml", _base_profiles())
    _write_yaml(
        cf_home / "config" / "override.yaml",
        {
            "common": {
                "proxy": {
                    "remote_url": "http://localhost:4000",
                    "env": {"LITELLM_MASTER_KEY": "sk-user-literal", "OTHER": "x"},
                }
            }
        },
    )

    class Args:
        config_target = "proxy"
        remote_url = None
        local = True
        bind = None

    assert handle_args(Args()) == 0

    with open(cf_home / "config" / "override.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert data["common"]["proxy"]["env"]["LITELLM_MASTER_KEY"] == "sk-user-literal"
    assert data["common"]["proxy"]["env"]["OTHER"] == "x"
