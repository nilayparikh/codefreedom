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
    """Integration tests for load_env_chain — layered .env → .env.secrets → system."""

    def test_loads_env_file(self, tmp_path):
        _write(tmp_path / ".env", "KEY=from_env\n")
        merged = load_env_chain(tmp_path)
        assert merged["KEY"] == "from_env"

    def test_secrets_override_env(self, tmp_path):
        _write(tmp_path / ".env", "KEY=from_env\n")
        _write(tmp_path / ".env.secrets", "KEY=from_secrets\n")
        merged = load_env_chain(tmp_path)
        assert merged["KEY"] == "from_secrets"

    def test_system_env_overrides_all(self, tmp_path):
        _write(tmp_path / ".env", "KEY=from_env\n")
        _write(tmp_path / ".env.secrets", "KEY=from_secrets\n")
        os.environ["KEY"] = "from_system"
        merged = load_env_chain(tmp_path)
        assert merged["KEY"] == "from_system"
        del os.environ["KEY"]

    def test_missing_secrets_ok(self, tmp_path):
        _write(tmp_path / ".env", "KEY=from_env\n")
        merged = load_env_chain(tmp_path)
        assert merged["KEY"] == "from_env"

    def test_missing_both_files_ok(self, tmp_path):
        os.environ["KEY"] = "from_system"
        merged = load_env_chain(tmp_path)
        assert merged["KEY"] == "from_system"
        del os.environ["KEY"]

    def test_secrets_adds_new_keys(self, tmp_path):
        _write(tmp_path / ".env", "A=1\n")
        _write(tmp_path / ".env.secrets", "B=2\n")
        merged = load_env_chain(tmp_path)
        assert merged["A"] == "1"
        assert merged["B"] == "2"


# ── helpers ──────────────────────────────────────────────────────────────────


def _write(path: Path, content: str) -> None:
    path.write_text(content)


def _write_temp(content: str) -> Path:
    """Write content to a temp file, return path. Caller is responsible for cleanup."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False)
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)
