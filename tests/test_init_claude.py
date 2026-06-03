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
        monkeypatch.setattr("codefreedom.cli.claude._CODEFREEDOM_DIR", cf_dir)
        examples = _setup_bundled_claude_examples(tmp_path)

        with mock.patch(
            "codefreedom.cli.claude._find_bundled_examples", return_value=examples
        ):
            result = init_claude(reset=False)

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

    def test_skips_when_exists_no_reset(self, tmp_path, monkeypatch):
        """When files exist and reset=False, init skips them."""
        cf_dir = tmp_path / ".codefreedom"
        monkeypatch.setattr("codefreedom.cli.claude._CODEFREEDOM_DIR", cf_dir)

        # Pre-create files with existing content
        profiles_dst = cf_dir / "profiles" / "claude-code.json"
        profiles_dst.parent.mkdir(parents=True)
        profiles_dst.write_text("existing")
        (cf_dir / ".env.claude").write_text("existing env")

        examples = _setup_bundled_claude_examples(tmp_path)
        (examples / "claude" / "profiles" / "claude-code.json").write_text("new")

        with mock.patch(
            "codefreedom.cli.claude._find_bundled_examples", return_value=examples
        ):
            result = init_claude(reset=False)

        assert result == 0
        assert profiles_dst.read_text() == "existing"
        assert (cf_dir / ".env.claude").read_text() == "existing env"

    def test_reset_overwrites(self, tmp_path, monkeypatch):
        """With reset=True, existing files are overwritten."""
        cf_dir = tmp_path / ".codefreedom"
        monkeypatch.setattr("codefreedom.cli.claude._CODEFREEDOM_DIR", cf_dir)

        profiles_dst = cf_dir / "profiles" / "claude-code.json"
        profiles_dst.parent.mkdir(parents=True)
        profiles_dst.write_text("old")

        examples = _setup_bundled_claude_examples(tmp_path)
        new_content = json.dumps(
            {"profiles": {"test": {"description": "new", "env": {"KEY": "val"}}}}
        )
        (examples / "claude" / "profiles" / "claude-code.json").write_text(new_content)

        with mock.patch(
            "codefreedom.cli.claude._find_bundled_examples", return_value=examples
        ):
            result = init_claude(reset=True)

        assert result == 0
        assert profiles_dst.read_text() == new_content

    def test_missing_source_graceful(self, tmp_path, monkeypatch):
        """When bundled examples don't exist, init still returns 0."""
        cf_dir = tmp_path / ".codefreedom"
        monkeypatch.setattr("codefreedom.cli.claude._CODEFREEDOM_DIR", cf_dir)

        empty = tmp_path / "empty"
        empty.mkdir()

        with mock.patch(
            "codefreedom.cli.claude._find_bundled_examples", return_value=empty
        ):
            result = init_claude(reset=False)

        assert result == 0
