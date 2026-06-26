"""CLI command tests for ``cf setup config vscode``.

Tests the full command flow with mocked network and filesystem.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from codefreedom.core.http_client import HTTPError, HTTPStatusError

from codefreedom.cli.vscode import (
    _VSCODE_APIKEY_PLACEHOLDER,
    cmd_vscode_proxy_config,
)

pytestmark = pytest.mark.integration


def _args(
    host: str = "localhost",
    port: int = 4000,
    name: str = "CodeFreedom",
    out: Any = None,
    keep_alias: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        host=host, port=port, name=name, out=out, keep_alias=keep_alias
    )


class TestCmdVscodeGenerate:
    def test_proxy_down_returns_1(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
        monkeypatch.setattr(
            "codefreedom.agents.vscode.proxy_models._check_proxy_live",
            lambda h, p: False,
        )
        result = cmd_vscode_proxy_config(_args())
        assert result == 1

    def test_missing_master_key_returns_1(self, monkeypatch, tmp_path: Path, capsys):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
        monkeypatch.delenv("CF_CLI_LITELLM_MASTER_KEY", raising=False)
        monkeypatch.setattr(
            "codefreedom.agents.vscode.proxy_models._check_proxy_live",
            lambda h, p: True,
        )
        result = cmd_vscode_proxy_config(_args())
        assert result == 1
        captured = capsys.readouterr()
        assert "LITELLM_MASTER_KEY" in captured.err

    def test_401_from_proxy_returns_1(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
        monkeypatch.setattr(
            "codefreedom.agents.vscode.proxy_models._check_proxy_live",
            lambda h, p: True,
        )

        def boom(h, p, k, *, timeout=10.0):
            raise HTTPStatusError("Unauthorized", status_code=401, url="")

        monkeypatch.setattr(
            "codefreedom.agents.vscode.proxy_models._fetch_model_info", boom
        )
        result = cmd_vscode_proxy_config(_args())
        assert result == 1

    def test_500_from_proxy_returns_1(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
        monkeypatch.setattr(
            "codefreedom.agents.vscode.proxy_models._check_proxy_live",
            lambda h, p: True,
        )

        def boom(h, p, k, *, timeout=10.0):
            raise HTTPStatusError("Server Error", status_code=500, url="")

        monkeypatch.setattr(
            "codefreedom.agents.vscode.proxy_models._fetch_model_info", boom
        )
        result = cmd_vscode_proxy_config(_args())
        assert result == 1

    def test_network_failure_returns_1(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
        monkeypatch.setattr(
            "codefreedom.agents.vscode.proxy_models._check_proxy_live",
            lambda h, p: True,
        )

        def boom(h, p, k, *, timeout=10.0):
            raise HTTPError("connection refused")

        monkeypatch.setattr(
            "codefreedom.agents.vscode.proxy_models._fetch_model_info", boom
        )
        result = cmd_vscode_proxy_config(_args())
        assert result == 1

    def test_invalid_json_returns_1(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
        monkeypatch.setattr(
            "codefreedom.agents.vscode.proxy_models._check_proxy_live",
            lambda h, p: True,
        )

        def boom(h, p, k, *, timeout=10.0):
            raise ValueError("bad response")

        monkeypatch.setattr(
            "codefreedom.agents.vscode.proxy_models._fetch_model_info", boom
        )
        result = cmd_vscode_proxy_config(_args())
        assert result == 1

    def test_happy_path_prints_to_stdout(self, monkeypatch, tmp_path: Path, capsys):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
        monkeypatch.setattr(
            "codefreedom.agents.vscode.proxy_models._check_proxy_live",
            lambda h, p: True,
        )
        monkeypatch.setattr(
            "codefreedom.agents.vscode.proxy_models._fetch_model_info",
            lambda h, p, k, *, timeout=10.0: [
                {
                    "model_name": "model-a",
                    "model_info": {
                        "supports_vision": True,
                        "supported_openai_params": ["tools"],
                        "max_input_tokens": 32000,
                        "max_output_tokens": 4000,
                    },
                },
                {"model_name": "model-b"},
            ],
        )

        result = cmd_vscode_proxy_config(
            _args(host="example.lan", port=5000, name="MyCo")
        )
        assert result == 0

        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["name"] == "MyCo"
        assert payload["vendor"] == "customendpoint"
        assert payload["apiKey"] == _VSCODE_APIKEY_PLACEHOLDER
        assert payload["apiType"] == "chat-completions"
        assert len(payload["models"]) == 2
        assert payload["models"][0]["id"] == "model-a"
        assert payload["models"][0]["url"] == "http://example.lan:5000/v1"
        assert payload["models"][0]["toolCalling"] is True
        assert payload["models"][0]["vision"] is True
        assert payload["models"][0]["maxInputTokens"] == 32000
        assert payload["models"][0]["maxOutputTokens"] == 4000
        assert payload["models"][1]["toolCalling"] is True
        assert payload["models"][1]["vision"] is False
        assert payload["models"][1]["maxInputTokens"] == 128000
        assert payload["models"][1]["maxOutputTokens"] == 16000

    def test_happy_path_writes_to_out_file(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
        monkeypatch.setattr(
            "codefreedom.agents.vscode.proxy_models._check_proxy_live",
            lambda h, p: True,
        )
        monkeypatch.setattr(
            "codefreedom.agents.vscode.proxy_models._fetch_model_info",
            lambda h, p, k, *, timeout=10.0: [{"model_name": "m1"}],
        )

        out_file = tmp_path / "out.json"
        result = cmd_vscode_proxy_config(
            _args(host="h", port=4000, name="X", out=str(out_file))
        )
        assert result == 0
        assert out_file.exists()
        payload = json.loads(out_file.read_text())
        assert payload["name"] == "X"
        assert payload["models"][0]["id"] == "m1"

    def test_empty_models_succeeds(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
        monkeypatch.setattr(
            "codefreedom.agents.vscode.proxy_models._check_proxy_live",
            lambda h, p: True,
        )
        monkeypatch.setattr(
            "codefreedom.agents.vscode.proxy_models._fetch_model_info",
            lambda h, p, k, *, timeout=10.0: [],
        )

        result = cmd_vscode_proxy_config(_args())
        assert result == 0

    def test_aliases_skipped_by_default(self, monkeypatch, tmp_path: Path, capsys):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
        monkeypatch.setattr(
            "codefreedom.agents.vscode.proxy_models._check_proxy_live",
            lambda h, p: True,
        )
        monkeypatch.setattr(
            "codefreedom.agents.vscode.proxy_models._fetch_model_info",
            lambda h, p, k, *, timeout=10.0: [
                {"model_name": "fable"},
                {"model_name": "opus"},
                {"model_name": "Qwen3.7-Max"},
                {"model_name": "DeepSeek-V4-Flash"},
            ],
        )
        config_dir = tmp_path / "config" / "proxy" / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "config.yaml").write_text(
            yaml.safe_dump(
                {
                    "router_settings": {
                        "model_group_alias": {
                            "fable": "Qwen3.7-Max",
                            "opus": "Qwen3.7-Plus",
                        }
                    }
                }
            )
        )

        result = cmd_vscode_proxy_config(_args())
        assert result == 0

        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        ids = [m["id"] for m in payload["models"]]
        assert "fable" not in ids
        assert "opus" not in ids
        assert "Qwen3.7-Max" in ids
        assert "DeepSeek-V4-Flash" in ids

    def test_aliases_included_with_keep_alias(
        self, monkeypatch, tmp_path: Path, capsys
    ):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
        monkeypatch.setattr(
            "codefreedom.agents.vscode.proxy_models._check_proxy_live",
            lambda h, p: True,
        )
        monkeypatch.setattr(
            "codefreedom.agents.vscode.proxy_models._fetch_model_info",
            lambda h, p, k, *, timeout=10.0: [
                {"model_name": "fable"},
                {"model_name": "opus"},
                {"model_name": "Qwen3.7-Max"},
            ],
        )
        config_dir = tmp_path / "config" / "proxy" / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "config.yaml").write_text(
            yaml.safe_dump(
                {
                    "router_settings": {
                        "model_group_alias": {
                            "fable": "Qwen3.7-Max",
                            "opus": "Qwen3.7-Plus",
                        }
                    }
                }
            )
        )

        result = cmd_vscode_proxy_config(_args(keep_alias=True))
        assert result == 0

        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        ids = [m["id"] for m in payload["models"]]
        assert "fable" in ids
        assert "opus" in ids
        assert "Qwen3.7-Max" in ids

    def test_no_aliases_config_keeps_all_models(
        self, monkeypatch, tmp_path: Path, capsys
    ):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
        monkeypatch.setattr(
            "codefreedom.agents.vscode.proxy_models._check_proxy_live",
            lambda h, p: True,
        )
        monkeypatch.setattr(
            "codefreedom.agents.vscode.proxy_models._fetch_model_info",
            lambda h, p, k, *, timeout=10.0: [
                {"model_name": "fable"},
                {"model_name": "opus"},
                {"model_name": "Qwen3.7-Max"},
            ],
        )
        result = cmd_vscode_proxy_config(_args())
        assert result == 0

        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        ids = [m["id"] for m in payload["models"]]
        assert "fable" in ids
        assert "opus" in ids
        assert "Qwen3.7-Max" in ids
