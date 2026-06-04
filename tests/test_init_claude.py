"""Tests for 'codefreedom claude init' — bootstraps profile and env files."""

import json
from pathlib import Path
from unittest import mock

from codefreedom.cli.claude import init_claude


def _setup_bundled_claude_examples(root: Path) -> Path:
    """Create a fake bundled examples/claude/ directory for testing."""
    examples = root / "examples"
    claude_dir = examples / "claude"
    profiles_dir = claude_dir / "profiles"
    profiles_dir.mkdir(parents=True)

    (profiles_dir / "claude-code.json").write_text(
        json.dumps({"profiles": {"default": {"description": "test", "env": {}}}})
    )
    (profiles_dir / "claude-code.schema.json").write_text(
        json.dumps({"$schema": "http://json-schema.org/draft-07/schema#"})
    )
    (claude_dir / ".env.claude.example").write_text("# CLAUDE_VAR=test\n")
    (claude_dir / ".env.claude.secrets.example").write_text("# CLAUDE_SECRET=test\n")
    return examples


class TestInitClaude:
    """Tests for init_claude."""

    def test_creates_profiles_and_env(self, tmp_path, monkeypatch):
        """Clean init creates profiles, schema, and .env.claude files."""
        cf_dir = tmp_path / ".codefreedom"
        monkeypatch.setattr(
            "codefreedom.cli.claude.get_codefreedom_dir", lambda: cf_dir
        )
        examples = _setup_bundled_claude_examples(tmp_path)

        with mock.patch(
            "codefreedom.cli.claude.find_bundled_examples", return_value=examples
        ):
            result = init_claude()

        assert result == 0

        # Profiles
        profiles_dst = cf_dir / "profiles" / "claude-code.json"
        assert profiles_dst.exists()
        content = json.loads(profiles_dst.read_text())
        assert content["profiles"]["default"]["description"] == "test"

        # Schema
        schema_dst = cf_dir / "profiles" / "claude-code.schema.json"
        assert schema_dst.exists()

        # Env files
        env_dst = cf_dir / ".env.claude"
        assert env_dst.exists()
        assert "# CLAUDE_VAR=test" in env_dst.read_text()

        secrets_dst = cf_dir / ".env.claude.secrets"
        assert secrets_dst.exists()
        assert "# CLAUDE_SECRET=test" in secrets_dst.read_text()

    def test_skips_all_when_any_exists(self, tmp_path, monkeypatch):
        """All-or-nothing: if any destination file exists, nothing is copied."""
        cf_dir = tmp_path / ".codefreedom"
        monkeypatch.setattr(
            "codefreedom.cli.claude.get_codefreedom_dir", lambda: cf_dir
        )

        # Pre-create one file (but not the rest)
        (cf_dir / ".env.claude").parent.mkdir(parents=True, exist_ok=True)
        (cf_dir / ".env.claude").write_text("existing env")

        examples = _setup_bundled_claude_examples(tmp_path)
        (examples / "claude" / "profiles" / "claude-code.json").write_text("new")

        with mock.patch(
            "codefreedom.cli.claude.find_bundled_examples", return_value=examples
        ):
            result = init_claude()

        assert result == 0
        # None of the other files should be created either
        assert not (cf_dir / "profiles" / "claude-code.json").exists()
        assert (cf_dir / ".env.claude").read_text() == "existing env"

    def test_missing_source_graceful(self, tmp_path, monkeypatch):
        """When bundled examples don't exist, init still returns 0."""
        cf_dir = tmp_path / ".codefreedom"
        monkeypatch.setattr(
            "codefreedom.cli.claude.get_codefreedom_dir", lambda: cf_dir
        )

        empty = tmp_path / "empty"
        empty.mkdir()

        with mock.patch(
            "codefreedom.cli.claude.find_bundled_examples", return_value=empty
        ):
            result = init_claude()

        assert result == 0
