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
                            "tools": ["dockerhub", "context7"],
                        }
                    }
                }
            },
            "tools": {
                "dockerhub": {
                    "kind": "mcp",
                    "transport": "local",
                    "command": ["docker", "run", "-i", "--rm", "mcp/dockerhub"],
                    "environment": {"HUB_PAT_TOKEN": "secret"},
                },
                "context7": {
                    "kind": "mcp",
                    "transport": "remote",
                    "url": "https://mcp.context7.com/mcp",
                },
            },
        }
    )
    assert cfg.tools["dockerhub"]["transport"] == "local"
    assert cfg.tools["context7"]["transport"] == "remote"


def test_config_model_rejects_invalid_mcp_tool() -> None:
    with pytest.raises(Exception):
        ConfigModel.model_validate(
            {
                "agents": {
                    "open-code": {
                        "profiles": {
                            "default": {
                                "tools": ["dockerhub"],
                            }
                        }
                    }
                },
                "tools": {
                    "dockerhub": {
                        "kind": "mcp",
                        "transport": "local",
                    }
                },
            }
        )


def test_builders_render_local_and_remote_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyConfig:
        tools = {
            "dockerhub": {
                "kind": "mcp",
                "transport": "local",
                "command": ["docker", "run", "-i", "--rm", "mcp/dockerhub", "--transport=stdio", "--username=test-user"],
                "environment": {"HUB_PAT_TOKEN": "secret"},
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

    claude = build_claude_mcp_servers(["dockerhub", "context7"])
    assert claude["dockerhub"]["type"] == "stdio"
    assert claude["dockerhub"]["command"] == "docker"
    assert claude["dockerhub"]["args"] == ["run", "-i", "--rm", "mcp/dockerhub", "--transport=stdio", "--username=test-user"]
    assert claude["context7"]["type"] == "http"

    opencode = build_opencode_mcp_entries(["dockerhub", "context7"])
    assert opencode["dockerhub"]["type"] == "local"
    assert opencode["dockerhub"]["command"] == ["docker", "run", "-i", "--rm", "mcp/dockerhub", "--transport=stdio", "--username=test-user"]
    assert opencode["context7"]["type"] == "remote"

    codex = build_codex_mcp_entries(["dockerhub", "context7"])
    assert codex["dockerhub"]["command"] == "docker"
    assert codex["dockerhub"]["args"] == ["run", "-i", "--rm", "mcp/dockerhub", "--transport=stdio", "--username=test-user"]
    assert codex["context7"]["url"] == "https://mcp.context7.com/mcp"


def test_write_mcp_json_supports_local_and_remote(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "codefreedom.launcher.load_tool_mcp_endpoints",
        lambda names: {
            "mcpServers": {
                "dockerhub": {
                    "type": "stdio",
                    "command": "docker",
                    "args": ["run", "-i", "--rm", "mcp/dockerhub", "--transport=stdio", "--username=test-user"],
                    "env": {"HUB_PAT_TOKEN": "secret"},
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
    _write_mcp_json(tmp_path, ["dockerhub", "context7"])
    data = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert data["mcpServers"]["dockerhub"]["command"] == "docker"
    assert data["mcpServers"]["context7"]["url"] == "https://mcp.context7.com/mcp"


def test_full_profiles_yaml_with_dockerhub_mcp_and_interpolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_CLI_DOCKERHUB_USERNAME", "test-user")
    monkeypatch.setenv("CF_CLI_DOCKERHUB_PAT_TOKEN", "secret-token")
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
          - dockerhub
      bare:
        env: {}

tools:
  chrome:
    image: "codefreedom:chrome"
    container_name: "codefreedom-chrome"
    port: 9222
    mcp_port: 9223
    mcp_path: /mcp
  dockerhub:
    kind: mcp
    transport: local
    command:
      - docker
      - run
      - -i
      - --rm
      - mcp/dockerhub
      - --transport=stdio
      - --username=${DOCKERHUB_USERNAME}
    environment:
      HUB_PAT_TOKEN: ${DOCKERHUB_PAT_TOKEN}
    enabled: true
""",
        encoding="utf-8",
    )

    config = load_config(config_dir)
    monkeypatch.setattr("codefreedom.tools.mcp.load_config", lambda: config)
    assert "dockerhub" in config.tools
    assert config.tools["dockerhub"]["kind"] == "mcp"

    runtime = config.for_agent("open-code", profile="default")
    assert "dockerhub" in runtime.tools

    servers = build_claude_mcp_servers(["dockerhub"])
    assert servers["dockerhub"]["type"] == "stdio"
    assert servers["dockerhub"]["command"] == "docker"
    assert servers["dockerhub"]["args"] == ["run", "-i", "--rm", "mcp/dockerhub", "--transport=stdio", "--username=test-user"]

    opencode_entries = build_opencode_mcp_entries(["dockerhub"])
    assert opencode_entries["dockerhub"]["type"] == "local"
    assert opencode_entries["dockerhub"]["command"] == ["docker", "run", "-i", "--rm", "mcp/dockerhub", "--transport=stdio", "--username=test-user"]
    assert opencode_entries["dockerhub"]["environment"] == {"HUB_PAT_TOKEN": "secret-token"}


def test_npx_local_mcp_renders_correctly(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyConfig:
        tools = {
            "filesystem": {
                "kind": "mcp",
                "transport": "local",
                "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/home/user"],
            },
            "sentry": {
                "kind": "mcp",
                "transport": "remote",
                "url": "https://mcp.sentry.dev/mcp",
            },
        }

    monkeypatch.setattr("codefreedom.tools.mcp.load_config", lambda: DummyConfig())

    servers = build_claude_mcp_servers(["filesystem", "sentry"])
    assert servers["filesystem"]["type"] == "stdio"
    assert servers["filesystem"]["command"] == "npx"
    assert servers["filesystem"]["args"] == ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"]
    assert servers["sentry"]["type"] == "http"
    assert servers["sentry"]["url"] == "https://mcp.sentry.dev/mcp"
