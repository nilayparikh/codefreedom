"""Tests for --init CLI command — bootstraps ~/.codefreedom/ from bundled examples."""

import json
from pathlib import Path
from unittest import mock

from codefreedom.cli.main import _init_codefreedom


def _setup_bundled_examples(root: Path) -> Path:
    """Create a fake bundled examples directory at root/examples/ for testing."""
    examples = root / "examples"

    # Profiles
    profiles_dir = examples / "profiles"
    profiles_dir.mkdir(parents=True)
    (profiles_dir / "claude-code-profiles.json").write_text(
        json.dumps({"profiles": {"default": {"description": "test", "env": {}}}})
    )
    (profiles_dir / "claude-code-profiles.schema.json").write_text(
        json.dumps({"$schema": "http://json-schema.org/draft-07/schema#"})
    )

    # Proxy
    proxy_dir = examples / "proxy"
    proxy_dir.mkdir(parents=True)
    (proxy_dir / "config.yaml").write_text("# test config")
    (proxy_dir / "docker-compose.yaml").write_text("version: '3'")
    providers_dir = proxy_dir / "providers"
    providers_dir.mkdir(parents=True)
    (providers_dir / "test.yaml").write_text("# test provider")

    # Env templates
    (examples / ".env.example").write_text(
        "# LITELLM_PORT=4000\n# LITELLM_LOG_LEVEL=INFO\n"
    )
    (examples / ".env.secrets.example").write_text(
        "# LITELLM_MASTER_KEY=sk-change-me\n"
    )

    return examples


class TestInitCodefreedom:
    """Tests for _init_codefreedom."""

    def test_creates_profiles_and_proxy(self, tmp_path):
        """When nothing exists, init creates profiles, schema, proxy, and env files."""
        cf_dir = tmp_path / ".codefreedom"
        examples = _setup_bundled_examples(tmp_path)

        with mock.patch(
            "codefreedom.cli.main._find_bundled_examples", return_value=examples
        ):
            result = _init_codefreedom(force=False, cf_dir=cf_dir)

        assert result == 0

        # Verify profiles were created
        profiles_dst = cf_dir / "profiles" / "claude-code.json"
        assert profiles_dst.exists()
        content = json.loads(profiles_dst.read_text())
        assert "profiles" in content
        assert content["profiles"]["default"]["description"] == "test"

        # Verify schema was created
        schema_dst = cf_dir / "profiles" / "claude-code-profiles.schema.json"
        assert schema_dst.exists()
        schema_content = json.loads(schema_dst.read_text())
        assert "$schema" in schema_content

        # Verify proxy was created with correct nested structure
        proxy_dst = cf_dir / "proxy"
        assert proxy_dst.exists()
        assert (proxy_dst / "docker-compose.yaml").exists()
        assert (proxy_dst / "config" / "config.yaml").exists()
        assert (proxy_dst / "config" / "providers" / "test.yaml").exists()

        # Verify .env was created (commented template)
        env_dst = cf_dir / ".env"
        assert env_dst.exists()
        assert "# LITELLM_PORT=4000" in env_dst.read_text()

        # Verify .env.secrets was created (commented template)
        secrets_dst = cf_dir / ".env.secrets"
        assert secrets_dst.exists()
        assert "# LITELLM_MASTER_KEY=sk-change-me" in secrets_dst.read_text()

    def test_init_skips_when_exists_and_no_force(self, tmp_path):
        """When files exist and force=False, init does nothing (including env files)."""
        cf_dir = tmp_path / ".codefreedom"

        # Pre-create destination files with existing content
        profiles_dst = cf_dir / "profiles" / "claude-code.json"
        profiles_dst.parent.mkdir(parents=True)
        profiles_dst.write_text("existing content")

        proxy_dst = cf_dir / "proxy"
        proxy_config = proxy_dst / "config"
        proxy_config.mkdir(parents=True)
        (proxy_config / "config.yaml").write_text("existing")
        (proxy_dst / "docker-compose.yaml").write_text("existing compose")

        (cf_dir / ".env").write_text("existing env")
        (cf_dir / ".env.secrets").write_text("existing secrets")

        # Setup source examples with different content
        examples = _setup_bundled_examples(tmp_path)
        # Override with newer content so we can verify it was NOT copied
        (examples / "profiles" / "claude-code-profiles.json").write_text(
            json.dumps({"profiles": {"default": {"env": {}}}})
        )
        (examples / "proxy" / "config.yaml").write_text("new content")
        (examples / "proxy" / "docker-compose.yaml").write_text("new compose")
        (examples / ".env.example").write_text("new env")
        (examples / ".env.secrets.example").write_text("new secrets")

        with mock.patch(
            "codefreedom.cli.main._find_bundled_examples", return_value=examples
        ):
            result = _init_codefreedom(force=False, cf_dir=cf_dir)

        assert result == 0
        # Content should NOT have changed
        assert profiles_dst.read_text() == "existing content"
        assert (proxy_dst / "config" / "config.yaml").read_text() == "existing"
        assert (cf_dir / ".env").read_text() == "existing env"
        assert (cf_dir / ".env.secrets").read_text() == "existing secrets"

    def test_init_force_overwrites(self, tmp_path):
        """With force=True, init overwrites existing files."""
        cf_dir = tmp_path / ".codefreedom"

        # Pre-create destination with old content
        profiles_dst = cf_dir / "profiles" / "claude-code.json"
        profiles_dst.parent.mkdir(parents=True)
        profiles_dst.write_text("old")
        proxy_dst = cf_dir / "proxy"
        proxy_config = proxy_dst / "config"
        proxy_config.mkdir(parents=True)
        (proxy_config / "config.yaml").write_text("old proxy")
        (proxy_dst / "docker-compose.yaml").write_text("old compose")

        # Setup source examples with new content
        examples = _setup_bundled_examples(tmp_path)
        new_content = json.dumps(
            {"profiles": {"test": {"description": "new", "env": {"KEY": "val"}}}}
        )
        (examples / "profiles" / "claude-code-profiles.json").write_text(new_content)
        (examples / "proxy" / "config.yaml").write_text("new proxy")
        (examples / "proxy" / "docker-compose.yaml").write_text("new compose")

        with mock.patch(
            "codefreedom.cli.main._find_bundled_examples", return_value=examples
        ):
            result = _init_codefreedom(force=True, cf_dir=cf_dir)

        assert result == 0
        assert profiles_dst.read_text() == new_content
        assert (proxy_dst / "config" / "config.yaml").read_text() == "new proxy"
        assert (proxy_dst / "docker-compose.yaml").read_text() == "new compose"

    def test_init_missing_examples_graceful(self, tmp_path):
        """When bundled examples don't exist, init reports errors but returns 0."""
        cf_dir = tmp_path / ".codefreedom"
        empty_examples = tmp_path / "empty_examples"
        empty_examples.mkdir()

        with mock.patch(
            "codefreedom.cli.main._find_bundled_examples", return_value=empty_examples
        ):
            result = _init_codefreedom(force=False, cf_dir=cf_dir)

        # Returns 0 even when no examples found (not a fatal error)
        assert result == 0

    def test_init_paths_are_correct(self):
        """Verify that --init computes correct destination paths."""
        from pathlib import Path as P

        cf_dir = P("/test/.codefreedom")

        profiles_dst = cf_dir / "profiles" / "claude-code.json"
        proxy_dst = cf_dir / "proxy"

        assert profiles_dst.as_posix().endswith(
            ".codefreedom/profiles/claude-code.json"
        )
        assert proxy_dst.as_posix().endswith(".codefreedom/proxy")
