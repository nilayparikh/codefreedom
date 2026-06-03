"""Tests for 'codefreedom proxy init' — bootstraps proxy config and env files."""

from pathlib import Path
from unittest import mock

from codefreedom.cli.proxy import init_proxy


def _setup_bundled_proxy_examples(root: Path) -> Path:
    """Create a fake bundled examples/proxy/ directory for testing."""
    examples = root / "examples"
    proxy_dir = examples / "proxy"
    providers_dir = proxy_dir / "providers"
    providers_dir.mkdir(parents=True)
    (proxy_dir / "config.yaml").write_text("# test config")
    (proxy_dir / "docker-compose.yaml").write_text("version: '3'")
    (providers_dir / "test.yaml").write_text("# test provider")
    (proxy_dir / ".env.proxy.example").write_text("# PROXY_VAR=test\n")
    (proxy_dir / ".env.proxy.secrets.example").write_text("# PROXY_SECRET=test\n")
    return examples


class TestInitProxy:
    """Tests for init_proxy."""

    def test_creates_proxy_configs(self, tmp_path, monkeypatch):
        """Clean init creates proxy config files with correct structure."""
        cf_dir = tmp_path / ".codefreedom"
        monkeypatch.setattr("codefreedom.cli.proxy._CODEFREEDOM_DIR", cf_dir)
        examples = _setup_bundled_proxy_examples(tmp_path)

        with mock.patch(
            "codefreedom.cli.proxy._find_bundled_examples", return_value=examples
        ):
            result = init_proxy(reset=False)

        assert result == 0

        proxy_dst = cf_dir / "proxy"
        assert proxy_dst.exists()
        assert (proxy_dst / "docker-compose.yaml").exists()
        assert (proxy_dst / "config" / "config.yaml").exists()
        assert (proxy_dst / "config" / "providers" / "test.yaml").exists()

        # Env files
        assert (cf_dir / ".env.proxy").exists()
        assert (cf_dir / ".env.proxy.secrets").exists()

    def test_skips_when_exists_no_reset(self, tmp_path, monkeypatch):
        """When files exist and reset=False, proxy init skips them."""
        cf_dir = tmp_path / ".codefreedom"
        monkeypatch.setattr("codefreedom.cli.proxy._CODEFREEDOM_DIR", cf_dir)

        proxy_dst = cf_dir / "proxy"
        proxy_config = proxy_dst / "config"
        proxy_config.mkdir(parents=True)
        (proxy_config / "config.yaml").write_text("existing")
        (proxy_dst / "docker-compose.yaml").write_text("existing compose")
        (cf_dir / ".env.proxy").write_text("existing env")

        examples = _setup_bundled_proxy_examples(tmp_path)
        (examples / "proxy" / "config.yaml").write_text("new content")

        with mock.patch(
            "codefreedom.cli.proxy._find_bundled_examples", return_value=examples
        ):
            result = init_proxy(reset=False)

        assert result == 0
        assert (proxy_config / "config.yaml").read_text() == "existing"
        assert (cf_dir / ".env.proxy").read_text() == "existing env"

    def test_reset_overwrites(self, tmp_path, monkeypatch):
        """With reset=True, existing proxy files are overwritten."""
        cf_dir = tmp_path / ".codefreedom"
        monkeypatch.setattr("codefreedom.cli.proxy._CODEFREEDOM_DIR", cf_dir)

        proxy_dst = cf_dir / "proxy"
        proxy_config = proxy_dst / "config"
        proxy_config.mkdir(parents=True)
        (proxy_config / "config.yaml").write_text("old")

        examples = _setup_bundled_proxy_examples(tmp_path)
        (examples / "proxy" / "config.yaml").write_text("new proxy")

        with mock.patch(
            "codefreedom.cli.proxy._find_bundled_examples", return_value=examples
        ):
            result = init_proxy(reset=True)

        assert result == 0
        assert (proxy_config / "config.yaml").read_text() == "new proxy"

    def test_missing_source_graceful(self, tmp_path, monkeypatch):
        """When bundled examples don't exist, init still returns 0."""
        cf_dir = tmp_path / ".codefreedom"
        monkeypatch.setattr("codefreedom.cli.proxy._CODEFREEDOM_DIR", cf_dir)

        empty = tmp_path / "empty"
        empty.mkdir()

        with mock.patch(
            "codefreedom.cli.proxy._find_bundled_examples", return_value=empty
        ):
            result = init_proxy(reset=False)

        assert result == 0
