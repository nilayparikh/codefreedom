"""Tests for the ``_unify_profiles_yaml`` helper.

Recipes ship a ``profiles/`` directory with one YAML file per agent
(e.g. ``claude-code.yaml``) and per tool (e.g. ``chrome.yaml``).  The
loader reads the unified ``profiles.yaml``; the helper aggregates the
per-profile files into that file when the recipe does not provide one.

Exercises the agent-vs-tool detection, the ``kind`` inference, the
underscore-to-hyphen conversion, the no-op cases, and the loader round
trip.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from codefreedom.cli.setup.recipe import _unify_profiles_yaml

pytestmark = pytest.mark.integration


def _write(dir_: Path, name: str, data: Dict[str, Any]) -> None:
    (dir_ / name).write_text(
        yaml.safe_dump(data, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def _write_profiles(config_dir: Path, files: Dict[str, Dict[str, Any]]) -> None:
    profiles = config_dir / "profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        _write(profiles, name, data)


def _read_yaml(path: Path) -> Dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# ============================================================================
# Idempotency / no-op behaviour
# ============================================================================


class TestNoOp:
    def test_skips_when_profiles_yaml_exists(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        existing = {"agents": {"claude-code": {"profiles": {"default": {}}}}}
        _write(config_dir, "profiles.yaml", existing)
        _write_profiles(config_dir, {"claude-code.yaml": {"profiles": {"default": {}}}})

        assert _unify_profiles_yaml(config_dir) is False
        assert _read_yaml(config_dir / "profiles.yaml") == existing

    def test_skips_when_profiles_dir_missing(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        assert _unify_profiles_yaml(config_dir) is False
        assert not (config_dir / "profiles.yaml").exists()

    def test_skips_when_profiles_dir_empty(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "profiles").mkdir()
        assert _unify_profiles_yaml(config_dir) is False
        assert not (config_dir / "profiles.yaml").exists()

    def test_skips_files_with_no_recognised_layout(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        _write_profiles(
            config_dir,
            {
                "README.yaml": {"foo": "bar", "baz": 1},
            },
        )
        assert _unify_profiles_yaml(config_dir) is False


# ============================================================================
# Agent detection (files with ``profiles:`` key)
# ============================================================================


class TestAgentDetection:
    def test_single_agent(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        _write_profiles(
            config_dir,
            {
                "claude-code.yaml": {
                    "description": "Claude Code profiles",
                    "profiles": {
                        "default": {"env": {"KEY": "val"}},
                        "bare": {"env": {}},
                    },
                },
            },
        )
        assert _unify_profiles_yaml(config_dir) is True
        out = _read_yaml(config_dir / "profiles.yaml")
        assert out == {
            "agents": {
                "claude-code": {
                    "profiles": {
                        "default": {"env": {"KEY": "val"}},
                        "bare": {"env": {}},
                    }
                }
            }
        }

    def test_multiple_agents(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        _write_profiles(
            config_dir,
            {
                "claude-code.yaml": {
                    "profiles": {"default": {"env": {"A": "1"}}}
                },
                "mimo-code.yaml": {
                    "profiles": {"default": {"env": {"B": "2"}}}
                },
                "pi-code.yaml": {
                    "profiles": {"default": {"env": {"C": "3"}}}
                },
            },
        )
        assert _unify_profiles_yaml(config_dir) is True
        out = _read_yaml(config_dir / "profiles.yaml")
        assert set(out["agents"].keys()) == {"claude-code", "mimo-code", "pi-code"}
        assert out["agents"]["claude-code"]["profiles"]["default"]["env"] == {"A": "1"}
        assert out["agents"]["mimo-code"]["profiles"]["default"]["env"] == {"B": "2"}
        assert out["agents"]["pi-code"]["profiles"]["default"]["env"] == {"C": "3"}

    def test_agent_metadata_ignored(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        _write_profiles(
            config_dir,
            {
                "claude-code.yaml": {
                    "description": "ignored",
                    "notes": ["ignored", "too"],
                    "profiles": {"default": {"env": {"K": "v"}}},
                }
            },
        )
        _unify_profiles_yaml(config_dir)
        out = _read_yaml(config_dir / "profiles.yaml")
        assert "description" not in out["agents"]["claude-code"]
        assert "notes" not in out["agents"]["claude-code"]


# ============================================================================
# Tool detection (single non-metadata top-level key)
# ============================================================================


class TestToolDetection:
    def test_tool_with_image(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        _write_profiles(
            config_dir,
            {
                "chrome.yaml": {
                    "description": "ignored",
                    "chrome": {
                        "image": "docker.io/x:latest",
                        "port": 9222,
                        "env": {"DEBUG": "1"},
                    },
                },
            },
        )
        _unify_profiles_yaml(config_dir)
        out = _read_yaml(config_dir / "profiles.yaml")
        assert out["tools"]["chrome"] == {
            "kind": "tool",
            "image": "docker.io/x:latest",
            "port": 9222,
            "env": {"DEBUG": "1"},
        }

    def test_cli_with_model(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        _write_profiles(
            config_dir,
            {
                "git.yaml": {
                    "git": {
                        "model": "MiMo-V2.5",
                        "conventional_commit": True,
                    }
                }
            },
        )
        _unify_profiles_yaml(config_dir)
        out = _read_yaml(config_dir / "profiles.yaml")
        assert out["tools"]["git"]["kind"] == "cli"
        assert out["tools"]["git"]["model"] == "MiMo-V2.5"

    def test_underscore_key_converted_to_hyphen(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        _write_profiles(
            config_dir,
            {
                "web-bridge.yaml": {
                    "web_bridge": {
                        "image": "docker.io/x:latest",
                        "port": 8500,
                    }
                }
            },
        )
        _unify_profiles_yaml(config_dir)
        out = _read_yaml(config_dir / "profiles.yaml")
        assert "web-bridge" in out["tools"]
        assert "web_bridge" not in out["tools"]
        assert out["tools"]["web-bridge"]["kind"] == "tool"

    def test_existing_kind_preserved(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        _write_profiles(
            config_dir,
            {
                "chrome.yaml": {
                    "chrome": {
                        "kind": "mcp",
                        "transport": "remote",
                        "url": "https://example/mcp",
                    }
                }
            },
        )
        _unify_profiles_yaml(config_dir)
        out = _read_yaml(config_dir / "profiles.yaml")
        assert out["tools"]["chrome"]["kind"] == "mcp"
        assert out["tools"]["chrome"]["transport"] == "remote"

    def test_multiple_tools(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        _write_profiles(
            config_dir,
            {
                "chrome.yaml": {"chrome": {"image": "x", "port": 9222}},
                "web.yaml": {"web": {"image": "y", "port": 8420}},
                "git.yaml": {"git": {"model": "z"}},
            },
        )
        _unify_profiles_yaml(config_dir)
        out = _read_yaml(config_dir / "profiles.yaml")
        assert out["tools"]["chrome"]["kind"] == "tool"
        assert out["tools"]["web"]["kind"] == "tool"
        assert out["tools"]["git"]["kind"] == "cli"


# ============================================================================
# Mixed agents + tools
# ============================================================================


class TestMixed:
    def test_agents_and_tools_combined(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        _write_profiles(
            config_dir,
            {
                "claude-code.yaml": {
                    "profiles": {"default": {"env": {"K": "v"}}}
                },
                "chrome.yaml": {"chrome": {"image": "x", "port": 9222}},
                "git.yaml": {"git": {"model": "MiMo-V2.5"}},
            },
        )
        _unify_profiles_yaml(config_dir)
        out = _read_yaml(config_dir / "profiles.yaml")
        assert "claude-code" in out["agents"]
        assert "chrome" in out["tools"]
        assert "git" in out["tools"]
        assert out["agents"]["claude-code"]["profiles"]["default"]["env"] == {"K": "v"}
        assert out["tools"]["chrome"]["kind"] == "tool"
        assert out["tools"]["git"]["kind"] == "cli"


# ============================================================================
# Return value & side effects
# ============================================================================


class TestReturnValue:
    def test_returns_true_when_written(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        _write_profiles(
            config_dir,
            {"claude-code.yaml": {"profiles": {"default": {}}}},
        )
        assert _unify_profiles_yaml(config_dir) is True
        assert (config_dir / "profiles.yaml").exists()

    def test_creates_config_dir_if_missing(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config" / "nested"
        _write_profiles(
            config_dir,
            {"claude-code.yaml": {"profiles": {"default": {}}}},
        )
        assert _unify_profiles_yaml(config_dir) is True
        assert (config_dir / "profiles.yaml").exists()
