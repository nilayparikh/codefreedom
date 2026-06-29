"""Tests for ``load_tool_profile`` override wiring (Phase 1b).

Regression tests for the bug where ``override.yaml``'s ``tools:`` block and
``vars:`` block were ignored by tool loaders — so ``CHROME_PORT: "9224"``
set in ``override.yaml`` had no effect on tool runtime ports.

Marker: integration (writes YAML to ``tmp_path``-scoped ``CODEFREEDOM_HOME``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from codefreedom.cli.docker_utils import load_tool_profile

pytestmark = pytest.mark.integration


def _config_dir(cf_home: Path) -> Path:
    d = cf_home / "config"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_yaml(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def _base_profiles(chrome_port: int = 9222, chrome_mcp_port: int = 9223) -> dict:
    return {
        "agents": {"claude-code": {"profiles": {"default": {"env": {}}}}},
        "tools": {
            "chrome": {
                "image": "img:chrome-latest",
                "container_name": "codefreedom-tools-chrome",
                "port": chrome_port,
                "mcp_port": chrome_mcp_port,
            },
            "web": {}, "github": {}, "web-bridge": {}, "git": {},
        },
        "common": {"suffix_id": "${SUFFIX_ID:-0000}"},
    }


def test_override_yaml_tools_block_overrides_profiles(monkeypatch, tmp_path):
    """override.yaml tools.chrome.mcp_port=9226 wins over profiles.yaml mcp_port=9223."""
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    cdir = _config_dir(cf_home)
    _write_yaml(cdir / "profiles.yaml", _base_profiles(chrome_mcp_port=9223))
    _write_yaml(cdir / "override.yaml", {"tools": {"chrome": {"mcp_port": 9226}}})

    settings = load_tool_profile(
        "chrome",
        {"image": "default:img", "container_name": "default",
         "port": 9222, "mcp_port": 9223, "mcp_path": "/mcp", "data_dir": "", "env": {}},
        extra_keys=["mcp_port", "mcp_path", "cdp_proxy_port"],
    )

    assert settings["mcp_port"] == 9226
    assert settings["port"] == 9222  # unchanged


def test_override_vars_feeds_interpolation_into_profiles(monkeypatch, tmp_path):
    """override.yaml vars.CHROME_PORT interpolates into profiles tools.chrome.port."""
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    cdir = _config_dir(cf_home)
    # Profiles uses ${CHROME_PORT:-9222} — to be interpolated.
    profiles = _base_profiles(chrome_port="${CHROME_PORT:-9222}")
    _write_yaml(cdir / "profiles.yaml", profiles)
    _write_yaml(cdir / "override.yaml", {"vars": {"CHROME_PORT": "9224"}})

    settings = load_tool_profile(
        "chrome",
        {"image": "default:img", "container_name": "default",
         "port": 9222, "mcp_port": 9223, "mcp_path": "/mcp", "data_dir": "", "env": {}},
        extra_keys=["mcp_port", "mcp_path", "cdp_proxy_port"],
    )

    # Interpolated string "9224" coerced to int and applied.
    assert settings["port"] == 9224


def test_cf_cli_vars_beat_override_yaml_vars(monkeypatch, tmp_path):
    """CF_CLI_CHROME_PORT (machine env) wins over override.yaml vars.CHROME_PORT."""
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    monkeypatch.setenv("CF_CLI_CHROME_PORT", "9299")
    cdir = _config_dir(cf_home)
    _write_yaml(cdir / "profiles.yaml", _base_profiles(chrome_port="${CHROME_PORT:-9222}"))
    _write_yaml(cdir / "override.yaml", {"vars": {"CHROME_PORT": "9224"}})

    settings = load_tool_profile(
        "chrome",
        {"image": "default:img", "container_name": "default",
         "port": 9222, "mcp_port": 9223, "mcp_path": "/mcp", "data_dir": "", "env": {}},
        extra_keys=["mcp_port", "mcp_path", "cdp_proxy_port"],
    )

    assert settings["port"] == 9299


def test_env_port_vars_override_mcp_port(monkeypatch, tmp_path):
    """CODEFREEDOM_CHROME_MCP_PORT machine env overrides both YAML and defaults."""
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    monkeypatch.setenv("CODEFREEDOM_CHROME_MCP_PORT", "9230")
    cdir = _config_dir(cf_home)
    _write_yaml(cdir / "profiles.yaml", _base_profiles(chrome_mcp_port=9223))

    settings = load_tool_profile(
        "chrome",
        {"image": "default:img", "container_name": "default",
         "port": 9222, "mcp_port": 9223, "mcp_path": "/mcp", "data_dir": "", "env": {}},
        extra_keys=["mcp_port", "mcp_path", "cdp_proxy_port"],
        env_port_vars={"mcp_port": "CODEFREEDOM_CHROME_MCP_PORT"},
    )

    assert settings["mcp_port"] == 9230


def test_override_vars_interpolate_tool_strings(monkeypatch, tmp_path):
    """override.yaml vars feed tool image/container_name interpolation."""
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    cdir = _config_dir(cf_home)
    profiles = _base_profiles()
    profiles["tools"]["chrome"]["image"] = "${REGISTRY:-docker.io}/${IMAGE_NAME:-nilayparikh/codefreedom}:chrome-${TAG:-latest}"
    profiles["tools"]["chrome"]["container_name"] = "codefreedom-${SUFFIX_ID:-0000}-chrome"
    _write_yaml(cdir / "profiles.yaml", profiles)
    _write_yaml(
        cdir / "override.yaml",
        {"vars": {"REGISTRY": "ghcr.io", "IMAGE_NAME": "example/codefreedom", "TAG": "dev", "SUFFIX_ID": "windemo"}},
    )

    settings = load_tool_profile(
        "chrome",
        {"image": "default:img", "container_name": "default",
         "port": 9222, "mcp_port": 9223, "mcp_path": "/mcp", "data_dir": "", "env": {}},
        extra_keys=["mcp_port", "mcp_path", "cdp_proxy_port"],
    )

    assert settings["image"] == "ghcr.io/example/codefreedom:chrome-dev"
    assert settings["container_name"] == "codefreedom-windemo-chrome"


def test_no_override_yaml_falls_back_clean(monkeypatch, tmp_path):
    """No override.yaml file present — behaviour matches pre-refactor."""
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    cdir = _config_dir(cf_home)
    _write_yaml(cdir / "profiles.yaml", _base_profiles())

    settings = load_tool_profile(
        "chrome",
        {"image": "default:img", "container_name": "default",
         "port": 9222, "mcp_port": 9223, "mcp_path": "/mcp", "data_dir": "", "env": {}},
        extra_keys=["mcp_port", "mcp_path", "cdp_proxy_port"],
    )

    assert settings["port"] == 9222
    assert settings["mcp_port"] == 9223
    assert settings["container_name"] == "codefreedom-tools-chrome"


def test_recipe_yaml_vars_feed_runtime_tool_interpolation(monkeypatch, tmp_path):
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    cdir = _config_dir(cf_home)
    profiles = _base_profiles()
    profiles["tools"]["chrome"]["image"] = "${TOOL_IMAGE_BASE}:chrome-${CHROME_IMAGE_TAG}"
    _write_yaml(cdir / "profiles.yaml", profiles)
    _write_yaml(
        cdir / "recipe.yaml",
        {
            "vars": {
                "TOOL_IMAGE_BASE": "docker.io/nilayparikh/codefreedom",
                "CHROME_IMAGE_TAG": "latest",
            }
        },
    )

    settings = load_tool_profile(
        "chrome",
        {"image": "default:img", "container_name": "default",
         "port": 9222, "mcp_port": 9223, "mcp_path": "/mcp", "data_dir": "", "env": {}},
        extra_keys=["mcp_port", "mcp_path", "cdp_proxy_port"],
    )

    assert settings["image"] == "docker.io/nilayparikh/codefreedom:chrome-latest"


def test_kind_discriminator_does_not_trigger_validation_warning(monkeypatch, tmp_path, capsys):
    """The ``kind: tool`` discriminator in profiles.yaml must not cause a
    schema validation warning — it is metadata, not a container setting."""
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    cdir = _config_dir(cf_home)
    profiles = _base_profiles()
    profiles["tools"]["chrome"]["kind"] = "tool"
    _write_yaml(cdir / "profiles.yaml", profiles)

    from codefreedom.tools.schemas.chrome import ChromeConfig

    load_tool_profile(
        "chrome",
        {"image": "default:img", "container_name": "default",
         "port": 9222, "mcp_port": 9223, "mcp_path": "/mcp", "data_dir": "", "env": {}},
        schema_class=ChromeConfig,
        extra_keys=["mcp_port", "mcp_path", "cdp_proxy_port"],
    )

    captured = capsys.readouterr()
    assert "validation issue" not in captured.err


def test_github_schema_accepts_remote_url(monkeypatch, tmp_path, capsys):
    """GithubSettings must accept ``remote_url`` without a validation warning."""
    cf_home = tmp_path / ".codefreedom"
    monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))
    cdir = _config_dir(cf_home)
    _write_yaml(cdir / "profiles.yaml", {
        "agents": {"claude-code": {"profiles": {"default": {"env": {}}}}},
        "tools": {
            "github": {
                "kind": "tool",
                "image": "img:github-latest",
                "container_name": "codefreedom-tools-github",
                "port": 8129,
                "remote_url": "http://localhost:8129/mcp",
            },
        },
        "common": {"suffix_id": "${SUFFIX_ID:-0000}"},
    })

    from codefreedom.tools.schemas.github import GithubConfig

    settings = load_tool_profile(
        "github",
        {"image": "default:img", "container_name": "default",
         "port": 0, "data_dir": "", "env": {}, "bind_host": "0.0.0.0", "remote_url": ""},
        schema_class=GithubConfig,
        extra_keys=["bind_host", "remote_url"],
    )

    captured = capsys.readouterr()
    assert "validation issue" not in captured.err
    assert settings["remote_url"] == "http://localhost:8129/mcp"

