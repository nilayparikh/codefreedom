from __future__ import annotations

import json
from pathlib import Path

import pytest

from codefreedom.config import load_config
from codefreedom.config.models import ConfigModel
from codefreedom.launcher import _write_mcp_json
from codefreedom.tools.mcp import (
    build_claude_mcp_servers,
    build_codex_mcp_entries,
    build_opencode_mcp_entries,
)

pytestmark = pytest.mark.unit


def test_config_model_accepts_local_and_remote_mcp_tools() -> None:
    cfg = ConfigModel.model_validate(
        {
            "agents": {
                "open-code": {
                    "profiles": {
                        "default": {
                            "tools": ["docker-mcp", "context7"],
                        }
                    }
                }
            },
            "tools": {
                "docker-mcp": {
                    "kind": "mcp",
                    "transport": "local",
                    "command": ["docker", "mcp", "gateway", "run"],
                },
                "context7": {
                    "kind": "mcp",
                    "transport": "remote",
                    "url": "https://mcp.context7.com/mcp",
                },
            },
        }
    )
    assert cfg.tools["docker-mcp"]["transport"] == "local"
    assert cfg.tools["context7"]["transport"] == "remote"


def test_config_model_rejects_invalid_mcp_tool() -> None:
    with pytest.raises(Exception):
        ConfigModel.model_validate(
            {
                "agents": {
                    "open-code": {
                        "profiles": {
                            "default": {
                                "tools": ["docker-mcp"],
                            }
                        }
                    }
                },
                "tools": {
                    "docker-mcp": {
                        "kind": "mcp",
                        "transport": "local",
                    }
                },
            }
        )


def test_builders_render_local_and_remote_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyConfig:
        tools = {
            "docker-mcp": {
                "kind": "mcp",
                "transport": "local",
                "command": ["docker", "mcp", "gateway", "run"],
                "environment": {"A": "B"},
                "timeout": 5000,
            },
            "context7": {
                "kind": "mcp",
                "transport": "remote",
                "url": "https://mcp.context7.com/mcp",
                "headers": {"X": "Y"},
            },
        }

    monkeypatch.setattr("codefreedom.tools.mcp.load_config", lambda: DummyConfig())

    claude = build_claude_mcp_servers(["docker-mcp", "context7"])
    assert claude["docker-mcp"]["type"] == "stdio"
    assert claude["docker-mcp"]["command"] == "docker"
    assert claude["docker-mcp"]["args"] == ["mcp", "gateway", "run"]
    assert claude["context7"]["type"] == "http"

    opencode = build_opencode_mcp_entries(["docker-mcp", "context7"])
    assert opencode["docker-mcp"]["type"] == "local"
    assert opencode["docker-mcp"]["command"] == ["docker", "mcp", "gateway", "run"]
    assert opencode["context7"]["type"] == "remote"

    codex = build_codex_mcp_entries(["docker-mcp", "context7"])
    assert codex["docker-mcp"]["command"] == "docker"
    assert codex["docker-mcp"]["args"] == ["mcp", "gateway", "run"]
    assert codex["context7"]["url"] == "https://mcp.context7.com/mcp"


def test_write_mcp_json_supports_local_and_remote(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "codefreedom.launcher.load_tool_mcp_endpoints",
        lambda names: {
            "mcpServers": {
                "docker-mcp": {
                    "type": "stdio",
                    "command": "docker",
                    "args": ["mcp", "gateway", "run"],
                },
                "context7": {
                    "type": "http",
                    "url": "https://mcp.context7.com/mcp",
                },
            }
        },
    )
    monkeypatch.setattr(
        "codefreedom.launcher.validate_remote_tools_or_raise",
        lambda names: None,
    )
    _write_mcp_json(tmp_path, ["docker-mcp", "context7"])
    data = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert data["mcpServers"]["docker-mcp"]["command"] == "docker"
    assert data["mcpServers"]["context7"]["url"] == "https://mcp.context7.com/mcp"


def test_full_profiles_yaml_with_docker_mcp(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "profiles.yaml").write_text(
        """
common:
  suffix_id: "0000"

agents:
  open-code:
    profiles:
      default:
        env: {}
        tools:
          - chrome
          - docker-mcp
      bare:
        env: {}

tools:
  chrome:
    image: "codefreedom:chrome"
    container_name: "codefreedom-chrome"
    port: 9222
    mcp_port: 9223
    mcp_path: /mcp
  docker-mcp:
    kind: mcp
    transport: local
    command:
      - docker
      - mcp
      - gateway
      - run
    enabled: true
""",
        encoding="utf-8",
    )

    config = load_config(config_dir)
    assert "docker-mcp" in config.tools
    assert config.tools["docker-mcp"]["kind"] == "mcp"

    runtime = config.for_agent("open-code", profile="default")
    assert "docker-mcp" in runtime.tools

    servers = build_claude_mcp_servers(["docker-mcp"])
    assert servers["docker-mcp"]["type"] == "stdio"
    assert servers["docker-mcp"]["command"] == "docker"
    assert servers["docker-mcp"]["args"] == ["mcp", "gateway", "run"]

    opencode_entries = build_opencode_mcp_entries(["docker-mcp"])
    assert opencode_entries["docker-mcp"]["type"] == "local"
    assert opencode_entries["docker-mcp"]["command"] == ["docker", "mcp", "gateway", "run"]
