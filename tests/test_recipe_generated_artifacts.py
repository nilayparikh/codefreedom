"""Tests for generated artifact rendering (bash, powershell, env, metadata)."""

from __future__ import annotations

import pytest

from codefreedom.recipe.generated_artifacts import (
    render_bash_setup_script,
    render_env_template,
    render_powershell_setup_script,
    render_recipe_summary_metadata,
)

pytestmark = pytest.mark.unit


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def secrets():
    return [
        {"var": "PROXY_API_KEY", "prompt": "Proxy key", "default": "sk-local"},
        {"var": "OPENROUTER_API_KEY", "prompt": "OpenRouter key"},
    ]


@pytest.fixture
def config_vars():
    return [{"var": "MICROSOFT_FOUNDRY_API_BASE", "prompt": "Base URL"}]


@pytest.fixture
def service_groups():
    return [{"name": "LiteLLM Proxy", "requires": ["PROXY_API_KEY"]}]


@pytest.fixture
def manifest():
    return {
        "name": "test-recipe",
        "description": "A test recipe",
        "required_secrets": [
            {"var": "SECRET_A", "prompt": "Secret A"},
            {"var": "SECRET_B", "prompt": "Secret B"},
        ],
        "config_vars": [
            {"var": "CONFIG_A", "prompt": "Config A"},
        ],
        "service_groups": [
            {"name": "Proxy", "requires": ["SECRET_A"]},
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Bash Setup Script
# ═══════════════════════════════════════════════════════════════════════════════


def test_render_bash_setup_script_contains_secret_prompts(secrets, config_vars, service_groups):
    script = render_bash_setup_script(
        recipe_name="costeffective-coding",
        secrets=secrets,
        config_vars=config_vars,
        service_groups=service_groups,
    )
    assert "PROXY_API_KEY" in script
    assert "OPENROUTER_API_KEY" in script
    assert "Proxy key" in script
    assert "OpenRouter key" in script
    assert "read -p" in script


def test_render_bash_setup_script_contains_config_vars(secrets, config_vars, service_groups):
    script = render_bash_setup_script(
        recipe_name="costeffective-coding",
        secrets=secrets,
        config_vars=config_vars,
        service_groups=service_groups,
    )
    assert "MICROSOFT_FOUNDRY_API_BASE" in script
    assert "Base URL" in script


def test_render_bash_setup_script_contains_service_groups(secrets, config_vars, service_groups):
    script = render_bash_setup_script(
        recipe_name="costeffective-coding",
        secrets=secrets,
        config_vars=config_vars,
        service_groups=service_groups,
    )
    assert "LiteLLM Proxy" in script
    assert "costeffective-coding" in script
    assert script.startswith("#!")


def test_render_bash_setup_script_supports_defaults(secrets, config_vars, service_groups):
    script = render_bash_setup_script(
        recipe_name="test",
        secrets=secrets,
        config_vars=config_vars,
        service_groups=service_groups,
    )
    assert "sk-local" in script


def test_render_bash_setup_script_empty_inputs():
    script = render_bash_setup_script(
        recipe_name="empty",
        secrets=[],
        config_vars=[],
        service_groups=[],
    )
    assert "empty" in script
    assert script.startswith("#!")


# ═══════════════════════════════════════════════════════════════════════════════
# PowerShell Setup Script
# ═══════════════════════════════════════════════════════════════════════════════


def test_render_powershell_setup_script_contains_secret_prompts(secrets, config_vars, service_groups):
    script = render_powershell_setup_script(
        recipe_name="costeffective-coding",
        secrets=secrets,
        config_vars=config_vars,
        service_groups=service_groups,
    )
    assert "PROXY_API_KEY" in script
    assert "OPENROUTER_API_KEY" in script
    assert "Proxy key" in script
    assert "Read-Host" in script


def test_render_powershell_setup_script_contains_config_vars(secrets, config_vars, service_groups):
    script = render_powershell_setup_script(
        recipe_name="costeffective-coding",
        secrets=secrets,
        config_vars=config_vars,
        service_groups=service_groups,
    )
    assert "MICROSOFT_FOUNDRY_API_BASE" in script
    assert "Base URL" in script


def test_render_powershell_setup_script_supports_defaults(secrets, config_vars, service_groups):
    script = render_powershell_setup_script(
        recipe_name="test",
        secrets=secrets,
        config_vars=config_vars,
        service_groups=service_groups,
    )
    assert "sk-local" in script


def test_render_powershell_setup_script_empty_inputs():
    script = render_powershell_setup_script(
        recipe_name="empty",
        secrets=[],
        config_vars=[],
        service_groups=[],
    )
    assert "empty" in script
    assert script.startswith("#")


# ═══════════════════════════════════════════════════════════════════════════════
# Env Template
# ═══════════════════════════════════════════════════════════════════════════════


def test_render_env_template_has_placeholders(secrets):
    template = render_env_template(secrets)
    assert "PROXY_API_KEY=" in template
    assert "OPENROUTER_API_KEY=" in template
    assert "CHANGE_ME" in template


def test_render_env_template_empty():
    template = render_env_template([])
    assert template == ""


def test_render_env_template_no_default(secrets):
    template = render_env_template(secrets)
    assert "OPENROUTER_API_KEY=CHANGE_ME" in template


def test_render_env_template_with_default(secrets):
    template = render_env_template(secrets)
    assert "PROXY_API_KEY=sk-local" in template


# ═══════════════════════════════════════════════════════════════════════════════
# Recipe Summary Metadata
# ═══════════════════════════════════════════════════════════════════════════════


def test_render_recipe_summary_metadata_returns_dict(manifest):
    meta = render_recipe_summary_metadata(manifest)
    assert isinstance(meta, dict)
    assert meta["name"] == "test-recipe"
    assert meta["secret_count"] == 2
    assert meta["config_count"] == 1
    assert len(meta["service_groups"]) == 1
    assert meta["service_groups"][0]["name"] == "Proxy"


def test_render_recipe_summary_metadata_empty_manifest():
    meta = render_recipe_summary_metadata({})
    assert meta["name"] == ""
    assert meta["secret_count"] == 0
    assert meta["config_count"] == 0
    assert meta["service_groups"] == []
