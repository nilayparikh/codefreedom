"""Tests for env_loader — .env parsing, secrets, priority, ${VAR} resolution."""

import os
import tempfile
from pathlib import Path

import pytest

from codefreedom.env_loader import load_dotenv, load_env_chain


class TestLoadDotenv:
    """Unit tests for load_dotenv — parses .env-style files."""

    def test_basic_key_value(self):
        path = _write_temp("KEY=value\nOTHER=123\n")
        env = load_dotenv(path)
        assert env == {"KEY": "value", "OTHER": "123"}

    def test_quoted_values(self):
        path = _write_temp("KEY=\"value with spaces\"\nSINGLE='single quoted'\n")
        env = load_dotenv(path)
        assert env["KEY"] == "value with spaces"
        assert env["SINGLE"] == "single quoted"

    def test_comments_and_blanks(self):
        path = _write_temp("# comment\nKEY=value\n\n# another\nOTHER=123\n")
        env = load_dotenv(path)
        assert env == {"KEY": "value", "OTHER": "123"}

    def test_var_reference_from_env(self):
        os.environ["TEST_REF"] = "resolved"
        path = _write_temp("RESULT=${TEST_REF}\n")
        env = load_dotenv(path)
        assert env == {"RESULT": "resolved"}
        del os.environ["TEST_REF"]

    def test_var_reference_with_default(self):
        path = _write_temp("RESULT=${MISSING:-fallback}\n")
        env = load_dotenv(path)
        assert env == {"RESULT": "fallback"}

    def test_var_reference_missing_no_default(self):
        path = _write_temp("RESULT=${MISSING}\n")
        env = load_dotenv(path)
        assert env == {"RESULT": ""}

    def test_var_reference_from_previously_parsed(self):
        path = _write_temp("BASE=hello\nRESULT=${BASE}\n")
        env = load_dotenv(path)
        assert env == {"BASE": "hello", "RESULT": "hello"}

    def test_missing_file(self):
        env = load_dotenv(Path("/nonexistent/.env"))
        assert env == {}

    def test_no_equals_sign(self):
        path = _write_temp("INVALID_LINE\nKEY=val\n")
        env = load_dotenv(path)
        assert env == {"KEY": "val"}


class TestLoadEnvChain:
    """Integration tests for load_env_chain — layered home → workspace → system."""

    @pytest.fixture(autouse=True)
    def _redirect_home(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Redirect CODEFREEDOM_HOME -> tmp_path so .env tests are isolated."""
        cf_home = tmp_path / ".codefreedom"
        cf_home.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("CODEFREEDOM_HOME", str(cf_home))

    def test_home_env_loaded(self, tmp_path):
        (tmp_path / ".codefreedom").mkdir(parents=True, exist_ok=True)
        _write(tmp_path / ".codefreedom" / ".env", "KEY=from_home\n")
        merged = load_env_chain(tmp_path)
        assert merged["KEY"] == "from_home"

    def test_workspace_overrides_home(self, tmp_path):
        (tmp_path / ".codefreedom").mkdir(parents=True, exist_ok=True)
        _write(tmp_path / ".codefreedom" / ".env", "KEY=from_home\n")
        _write(tmp_path / ".env", "KEY=from_workspace\n")
        merged = load_env_chain(tmp_path)
        assert merged["KEY"] == "from_workspace"

    def test_home_secrets_override_home_env(self, tmp_path):
        (tmp_path / ".codefreedom").mkdir(parents=True, exist_ok=True)
        _write(tmp_path / ".codefreedom" / ".env", "KEY=from_env\n")
        _write(tmp_path / ".codefreedom" / ".env.secrets", "KEY=from_secrets\n")
        merged = load_env_chain(tmp_path)
        assert merged["KEY"] == "from_secrets"

    def test_system_env_overrides_all(self, tmp_path):
        (tmp_path / ".codefreedom").mkdir(parents=True, exist_ok=True)
        _write(tmp_path / ".codefreedom" / ".env", "KEY=from_home\n")
        _write(tmp_path / ".env", "KEY=from_workspace\n")
        os.environ["KEY"] = "from_system"
        merged = load_env_chain(tmp_path)
        assert merged["KEY"] == "from_system"
        del os.environ["KEY"]

    def test_missing_home_env_uses_workspace(self, tmp_path):
        _write(tmp_path / ".env", "KEY=from_workspace\n")
        merged = load_env_chain(tmp_path)
        assert merged["KEY"] == "from_workspace"

    def test_missing_all_files_ok(self, tmp_path):
        os.environ["KEY"] = "from_system"
        merged = load_env_chain(tmp_path)
        assert merged["KEY"] == "from_system"
        del os.environ["KEY"]

    def test_secrets_adds_new_keys(self, tmp_path):
        (tmp_path / ".codefreedom").mkdir(parents=True, exist_ok=True)
        _write(tmp_path / ".codefreedom" / ".env", "A=1\n")
        _write(tmp_path / ".codefreedom" / ".env.secrets", "B=2\n")
        merged = load_env_chain(tmp_path)
        assert merged["A"] == "1"
        assert merged["B"] == "2"

    def test_workspace_secrets_override_home(self, tmp_path):
        (tmp_path / ".codefreedom").mkdir(parents=True, exist_ok=True)
        _write(tmp_path / ".codefreedom" / ".env.secrets", "KEY=from_home_secrets\n")
        _write(tmp_path / ".env.secrets", "KEY=from_workspace_secrets\n")
        merged = load_env_chain(tmp_path)
        assert merged["KEY"] == "from_workspace_secrets"

    def test_component_env_loaded(self, tmp_path):
        """Component-specific env files are only loaded for their component."""
        (tmp_path / ".codefreedom").mkdir(parents=True, exist_ok=True)
        _write(tmp_path / ".codefreedom" / ".env.claude", "CLAUDE_VAR=claude_val\n")
        _write(tmp_path / ".codefreedom" / ".env.proxy", "PROXY_VAR=proxy_val\n")

        # Without component, neither should load
        merged_no_component = load_env_chain(tmp_path)
        assert "CLAUDE_VAR" not in merged_no_component
        assert "PROXY_VAR" not in merged_no_component

        # With component="claude", only claude envs load
        merged_claude = load_env_chain(tmp_path, component="claude")
        assert merged_claude["CLAUDE_VAR"] == "claude_val"
        assert "PROXY_VAR" not in merged_claude

        # With component="proxy", only proxy envs load
        merged_proxy = load_env_chain(tmp_path, component="proxy")
        assert merged_proxy["PROXY_VAR"] == "proxy_val"
        assert "CLAUDE_VAR" not in merged_proxy

    def test_component_secrets_override_component_env(self, tmp_path):
        """Component-specific secrets override component-specific env."""
        (tmp_path / ".codefreedom").mkdir(parents=True, exist_ok=True)
        _write(tmp_path / ".codefreedom" / ".env.proxy", "API_KEY=from_env\n")
        _write(
            tmp_path / ".codefreedom" / ".env.proxy.secrets",
            "API_KEY=from_secret\n",
        )
        merged = load_env_chain(tmp_path, component="proxy")
        assert merged["API_KEY"] == "from_secret"

    def test_shared_env_overrides_component_env(self, tmp_path):
        """Shared ~/.codefreedom/.env overrides component-specific env files."""
        (tmp_path / ".codefreedom").mkdir(parents=True, exist_ok=True)
        _write(tmp_path / ".codefreedom" / ".env.claude", "KEY=from_claude\n")
        _write(tmp_path / ".codefreedom" / ".env", "KEY=from_shared\n")
        merged = load_env_chain(tmp_path, component="claude")
        assert merged["KEY"] == "from_shared"

    def test_missing_component_files_ok(self, tmp_path):
        """Missing component-specific env files are skipped gracefully."""
        (tmp_path / ".codefreedom").mkdir(parents=True, exist_ok=True)
        _write(tmp_path / ".codefreedom" / ".env", "KEY=from_shared\n")
        merged = load_env_chain(tmp_path, component="claude")
        assert merged["KEY"] == "from_shared"


# ── helpers ──────────────────────────────────────────────────────────────────


def _write(path: Path, content: str) -> None:
    path.write_text(content)


def _write_temp(content: str) -> Path:
    """Write content to a temp file, return path. Caller is responsible for cleanup."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False)
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)
