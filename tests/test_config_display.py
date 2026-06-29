"""Tests for config.display — secret redaction, source tracking, config display."""

import pytest
import yaml

from codefreedom.config.display import (
    format_resolved_config,
    is_secret_key,
    redact_value,
    resolve_value_source,
)

pytestmark = pytest.mark.unit


class TestSecretDetection:
    """Tests for is_secret_key — detect secret-like env var names."""

    def test_key_with_token(self):
        assert is_secret_key("PROXY_API_KEY") is True

    def test_key_with_secret(self):
        assert is_secret_key("API_SECRET") is True

    def test_key_with_password(self):
        assert is_secret_key("DB_PASSWORD") is True

    def test_key_with_credential(self):
        assert is_secret_key("AWS_CREDENTIAL") is True

    def test_non_secret_key(self):
        assert is_secret_key("PROXY_PORT") is False

    def test_non_secret_key_lowercase(self):
        assert is_secret_key("some_random_setting") is False

    def test_empty_string(self):
        assert is_secret_key("") is False


class TestRedaction:
    """Tests for redact_value — redact secret values."""

    def test_long_value(self):
        assert redact_value("sk-abc123xyz") == "s**********z"

    def test_medium_value(self):
        assert redact_value("secret123") == "s*******3"

    def test_short_value(self):
        assert redact_value("abc") == "a*c"

    def test_two_chars(self):
        assert redact_value("ab") == "**"

    def test_one_char(self):
        assert redact_value("x") == "*"

    def test_empty_string(self):
        assert redact_value("") == ""

    def test_preserves_first_last(self):
        result = redact_value("password123")
        assert result[0] == "p"
        assert result[-1] == "3"


class TestSourceTracking:
    """Tests for resolve_value_source — determine value origin."""

    def test_default_source(self, tmp_path):
        """Value not in any layer → default."""
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({
            "agents": {"claude-code": {"profiles": {"default": {"env": {}}}}},
            "tools": {"chrome": {}},
        }))
        source = resolve_value_source("suffix_id", "0000", tmp_path, {})
        assert source == "default"

    def test_profiles_source(self, tmp_path):
        """Value in profiles.yaml vars → profiles.yaml."""
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({
            "vars": {"MY_VAR": "from_profiles"},
            "agents": {"claude-code": {"profiles": {"default": {"env": {}}}}},
            "tools": {"chrome": {}},
        }))
        source = resolve_value_source("MY_VAR", "from_profiles", tmp_path, {})
        assert source == "profiles.yaml"

    def test_recipe_source(self, tmp_path):
        """Value in recipe.yaml vars → recipe.yaml."""
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({
            "vars": {"MY_VAR": "from_profiles"},
            "agents": {"claude-code": {"profiles": {"default": {"env": {}}}}},
            "tools": {"chrome": {}},
        }))
        recipe = tmp_path / "recipe.yaml"
        recipe.write_text(yaml.dump({
            "vars": {"MY_VAR": "from_recipe"},
        }))
        source = resolve_value_source("MY_VAR", "from_recipe", tmp_path, {})
        assert source == "recipe.yaml"

    def test_override_source(self, tmp_path):
        """Value in override.yaml vars → override.yaml."""
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({
            "vars": {"MY_VAR": "from_profiles"},
            "agents": {"claude-code": {"profiles": {"default": {"env": {}}}}},
            "tools": {"chrome": {}},
        }))
        override = tmp_path / "override.yaml"
        override.write_text(yaml.dump({
            "comment": "test",
            "vars": {"MY_VAR": "from_override"},
        }))
        source = resolve_value_source("MY_VAR", "from_override", tmp_path, {})
        assert source == "override.yaml"

    def test_cflcli_source(self, tmp_path, monkeypatch):
        """Value in CF_CLI_* env → CF_CLI_*."""
        monkeypatch.setenv("CF_CLI_MY_VAR", "from_cflcli")
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({
            "vars": {"MY_VAR": "from_profiles"},
            "agents": {"claude-code": {"profiles": {"default": {"env": {}}}}},
            "tools": {"chrome": {}},
        }))
        source = resolve_value_source("MY_VAR", "from_cflcli", tmp_path, {})
        assert source == "CF_CLI_*"


class TestFormatResolvedConfig:
    """Tests for format_resolved_config — full config display."""

    def test_basic_output(self, tmp_path):
        """Basic config renders without error."""
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({
            "agents": {"claude-code": {"profiles": {"default": {"env": {"KEY": "val"}}}}},
            "tools": {"chrome": {}},
        }))
        output = format_resolved_config(tmp_path, show_source=False)
        assert "agents:" in output
        assert "claude-code:" in output

    def test_secret_redaction_in_output(self, tmp_path):
        """Secret values are redacted in output."""
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({
            "agents": {"claude-code": {"profiles": {"default": {"env": {"API_KEY": "secret123"}}}}},
            "tools": {"chrome": {}},
        }))
        output = format_resolved_config(tmp_path, show_source=False)
        assert "s*******3" in output
        assert "secret123" not in output

    def test_source_labels_in_output(self, tmp_path):
        """Source labels appear when show_source=True."""
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({
            "vars": {"PROXY_PORT": "4000"},
            "agents": {"claude-code": {"profiles": {"default": {"env": {}}}}},
            "tools": {"chrome": {}},
        }))
        output = format_resolved_config(tmp_path, show_source=True)
        # PROXY_PORT is in profiles.yaml vars, but also defaults to 4000
        # so source could be default or profiles.yaml depending on resolution
        assert "(default)" in output or "(profiles.yaml)" in output
