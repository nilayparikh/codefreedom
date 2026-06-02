"""Tests for --init CLI command — bootstraps ~/.codefreedom/ from examples."""

import json
from pathlib import Path

from codefreedom.cli.main import _init_codefreedom


class TestInitCodefreedom:
    """Tests for _init_codefreedom."""

    def test_creates_profiles_and_proxy(self, tmp_path):
        """When neither exists, init creates profiles, schema, proxy, and env files."""
        proj_root = tmp_path / "project"
        cf_dir = tmp_path / ".codefreedom"

        # Set up fake project root with examples
        profiles_src = proj_root / "profiles.examples" / "claude-code-profiles.json"
        profiles_src.parent.mkdir(parents=True)
        profiles_src.write_text(
            json.dumps({"profiles": {"default": {"description": "test", "env": {}}}})
        )

        schema_src = (
            proj_root / "profiles.examples" / "claude-code-profiles.schema.json"
        )
        schema_src.write_text(
            json.dumps({"$schema": "http://json-schema.org/draft-07/schema#"})
        )

        proxy_src = proj_root / "litellm.examples"
        proxy_src.mkdir(parents=True)
        (proxy_src / "config.yaml").write_text("# test config")
        (proxy_src / "docker-compose.yml").write_text("version: '3'")
        providers_src = proxy_src / "providers"
        providers_src.mkdir(parents=True)
        (providers_src / "test.yaml").write_text("# test provider")

        # Set up env example files (fully commented)
        (proj_root / ".env.example").write_text(
            "# LITELLM_PORT=4000\n# LITELLM_LOG_LEVEL=INFO\n"
        )
        (proj_root / ".env.secrets.example").write_text(
            "# LITELLM_MASTER_KEY=sk-change-me\n"
        )

        result = _init_codefreedom(force=False, project_root=proj_root, cf_dir=cf_dir)
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
        assert (proxy_dst / "docker-compose.yml").exists()
        assert (proxy_dst / "config" / "config.yaml").exists()
        assert (proxy_dst / "config" / "providers" / "test.yaml").exists()

        # Verify .env was created (commented template)
        env_dst = cf_dir / ".env"
        assert env_dst.exists()
        env_content = env_dst.read_text()
        assert "# LITELLM_PORT=4000" in env_content

        # Verify .env.secrets was created (commented template)
        secrets_dst = cf_dir / ".env.secrets"
        assert secrets_dst.exists()
        secrets_content = secrets_dst.read_text()
        assert "# LITELLM_MASTER_KEY=sk-change-me" in secrets_content

    def test_init_skips_when_exists_and_no_force(self, tmp_path):
        """When files exist and force=False, init does nothing (including env files)."""
        proj_root = tmp_path / "project"
        cf_dir = tmp_path / ".codefreedom"

        # Pre-create destination files
        profiles_dst = cf_dir / "profiles" / "claude-code.json"
        profiles_dst.parent.mkdir(parents=True)
        profiles_dst.write_text("existing content")

        proxy_dst = cf_dir / "proxy"
        proxy_config = proxy_dst / "config"
        proxy_config.mkdir(parents=True)
        (proxy_config / "config.yaml").write_text("existing")
        (proxy_dst / "docker-compose.yml").write_text("existing compose")

        # Pre-create env files (should NOT be overwritten)
        (cf_dir / ".env").write_text("existing env")
        (cf_dir / ".env.secrets").write_text("existing secrets")

        # Setup source examples (different content)
        profiles_src = proj_root / "profiles.examples" / "claude-code-profiles.json"
        profiles_src.parent.mkdir(parents=True)
        profiles_src.write_text(json.dumps({"profiles": {"default": {"env": {}}}}))

        proxy_src = proj_root / "litellm.examples"
        proxy_src.mkdir(parents=True)
        (proxy_src / "config.yaml").write_text("new content")
        (proxy_src / "docker-compose.yml").write_text("new compose")

        (proj_root / ".env.example").write_text("new env")
        (proj_root / ".env.secrets.example").write_text("new secrets")

        result = _init_codefreedom(force=False, project_root=proj_root, cf_dir=cf_dir)
        assert result == 0
        # Content should NOT have changed
        assert profiles_dst.read_text() == "existing content"
        assert (proxy_dst / "config" / "config.yaml").read_text() == "existing"
        assert (cf_dir / ".env").read_text() == "existing env"
        assert (cf_dir / ".env.secrets").read_text() == "existing secrets"

    def test_init_force_overwrites(self, tmp_path):
        """With force=True, init overwrites existing files."""
        proj_root = tmp_path / "project"
        cf_dir = tmp_path / ".codefreedom"

        # Pre-create destination with old content
        profiles_dst = cf_dir / "profiles" / "claude-code.json"
        profiles_dst.parent.mkdir(parents=True)
        profiles_dst.write_text("old")
        proxy_dst = cf_dir / "proxy"
        proxy_config = proxy_dst / "config"
        proxy_config.mkdir(parents=True)
        (proxy_config / "config.yaml").write_text("old proxy")
        (proxy_dst / "docker-compose.yml").write_text("old compose")

        # Setup source examples
        new_content = json.dumps(
            {"profiles": {"test": {"description": "new", "env": {"KEY": "val"}}}}
        )
        profiles_src = proj_root / "profiles.examples" / "claude-code-profiles.json"
        profiles_src.parent.mkdir(parents=True)
        profiles_src.write_text(new_content)

        proxy_src = proj_root / "litellm.examples"
        proxy_src.mkdir(parents=True)
        (proxy_src / "config.yaml").write_text("new proxy")
        (proxy_src / "docker-compose.yml").write_text("new compose")

        result = _init_codefreedom(force=True, project_root=proj_root, cf_dir=cf_dir)
        assert result == 0
        assert profiles_dst.read_text() == new_content
        assert (proxy_dst / "config" / "config.yaml").read_text() == "new proxy"
        assert (proxy_dst / "docker-compose.yml").read_text() == "new compose"

    def test_init_missing_examples_graceful(self, tmp_path):
        """When examples don't exist, init reports errors but returns 0."""
        proj_root = tmp_path / "project"  # empty, no examples
        cf_dir = tmp_path / ".codefreedom"

        result = _init_codefreedom(force=False, project_root=proj_root, cf_dir=cf_dir)
        # Returns 0 even when no examples found (not a fatal error)
        assert result == 0

    def test_init_paths_are_correct(self):
        """Verify that --init computes correct source/destination paths."""
        from pathlib import Path as P

        cf_dir = P("/test/.codefreedom")
        proj = P("/test/project")

        profiles_dst = cf_dir / "profiles" / "claude-code.json"
        proxy_dst = cf_dir / "proxy"

        assert str(profiles_dst).endswith(".codefreedom/profiles/claude-code.json")
        assert str(proxy_dst).endswith(".codefreedom/proxy")
