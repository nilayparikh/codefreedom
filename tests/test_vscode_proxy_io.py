"""I/O-dependent helpers for VS Code proxy config.

Tests functions that read files, make network calls, or interact with
the environment.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codefreedom.cli.vscode import (
    _check_proxy_live,
    _load_alias_models,
    _load_route_image_models,
    _proxy_health_url,
    _proxy_model_info_url,
    _resolve_master_key,
)

pytestmark = pytest.mark.integration

# ── _resolve_master_key ──────────────────────────────────────────────────────


class TestResolveMasterKey:
    @staticmethod
    def _clean_cf_cli(monkeypatch):
        monkeypatch.delenv("CF_CLI_LITELLM_MASTER_KEY", raising=False)

    def test_from_cf_cli_env_wins(self, monkeypatch, tmp_path: Path):
        self._clean_cf_cli(monkeypatch)
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.setenv("CF_CLI_LITELLM_MASTER_KEY", "sk-from-cf-cli")
        assert _resolve_master_key() == "sk-from-cf-cli"

    def test_missing_returns_none(self, monkeypatch, tmp_path: Path):
        self._clean_cf_cli(monkeypatch)
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        assert _resolve_master_key() is None

    def test_empty_string_in_env_treated_as_set(self, monkeypatch, tmp_path: Path):
        self._clean_cf_cli(monkeypatch)
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
        monkeypatch.setenv("LITELLM_MASTER_KEY", "")
        (tmp_path / ".env.proxy.secrets").write_text(
            "LITELLM_MASTER_KEY=sk-from-file\n"
        )
        assert _resolve_master_key() is None

    def test_secrets_file_missing_key(self, monkeypatch, tmp_path: Path):
        self._clean_cf_cli(monkeypatch)
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
        (tmp_path / ".env.proxy.secrets").write_text("OTHER_KEY=foo\n")
        assert _resolve_master_key() is None

    def test_cf_cli_prefix_wins_over_env(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-from-env")
        monkeypatch.setenv("CF_CLI_LITELLM_MASTER_KEY", "sk-from-cf-cli")
        assert _resolve_master_key() == "sk-from-cf-cli"

    def test_cf_cli_prefix_falls_through_to_env(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-from-env")
        monkeypatch.delenv("CF_CLI_LITELLM_MASTER_KEY", raising=False)
        assert _resolve_master_key() == "sk-from-env"

    def test_cf_cli_empty_string_beats_env(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-from-env")
        monkeypatch.setenv("CF_CLI_LITELLM_MASTER_KEY", "")
        assert _resolve_master_key() is None

    def test_cf_cli_empty_string_beats_file(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
        monkeypatch.setenv("CF_CLI_LITELLM_MASTER_KEY", "")
        (tmp_path / ".env.proxy.secrets").write_text(
            "LITELLM_MASTER_KEY=sk-from-file\n"
        )
        assert _resolve_master_key() is None


# ── _proxy_health_url / _proxy_model_info_url ────────────────────────────────


class TestProxyUrls:
    def test_health_url_default(self):
        assert _proxy_health_url("localhost", 4000) == "http://localhost:4000/health/liveliness"

    def test_health_url_custom_host(self):
        assert _proxy_health_url("10.0.0.1", 4000) == "http://10.0.0.1:4000/health/liveliness"

    def test_health_url_custom_port(self):
        assert _proxy_health_url("localhost", 5000) == "http://localhost:5000/health/liveliness"

    def test_model_info_url_default(self):
        url = _proxy_model_info_url("localhost", 4000)
        assert url == "http://localhost:4000/v1/model/info"

    def test_model_info_url_custom_port(self):
        url = _proxy_model_info_url("localhost", 5000)
        assert url == "http://localhost:5000/v1/model/info"


# ── _check_proxy_live ────────────────────────────────────────────────────────


class TestCheckProxyLive:
    def test_returns_true_on_200(self, monkeypatch):
        from codefreedom.core.http_client import Response

        monkeypatch.setattr(
            "codefreedom.core.http_client._do_get",
            lambda url, timeout=5.0, **kw: Response(200, {}, b""),
        )
        assert _check_proxy_live("localhost", 4000) is True

    def test_returns_false_on_error(self, monkeypatch):
        from codefreedom.core.http_client import HTTPError

        def boom(url, timeout=5.0, **kw):
            raise HTTPError("refused")

        monkeypatch.setattr("codefreedom.core.http_client._do_get", boom)
        assert _check_proxy_live("localhost", 4000) is False

    def test_returns_false_on_http_status_error(self, monkeypatch):
        from codefreedom.core.http_client import HTTPStatusError

        def boom(url, timeout=5.0, **kw):
            raise HTTPStatusError("error", status_code=503, url="")

        monkeypatch.setattr("codefreedom.core.http_client._do_get", boom)
        assert _check_proxy_live("localhost", 4000) is False


# ── _fetch_model_info ────────────────────────────────────────────────────────


class TestFetchModelInfo:
    def test_returns_model_list(self, monkeypatch):
        from codefreedom.core.http_client import Response
        from codefreedom.cli.vscode import _fetch_model_info

        monkeypatch.setattr(
            "codefreedom.core.http_client._do_get",
            lambda url, timeout=10.0, **kw: Response(200, {}, b'{"data": [{"model_name": "m1"}]}'),
        )
        result = _fetch_model_info("localhost", 4000, "sk-key")
        assert result == [{"model_name": "m1"}]

    def test_returns_empty_on_missing_data(self, monkeypatch):
        from codefreedom.core.http_client import Response
        from codefreedom.cli.vscode import _fetch_model_info

        monkeypatch.setattr(
            "codefreedom.core.http_client._do_get",
            lambda url, timeout=10.0, **kw: Response(200, {}, b"{}"),
        )
        result = _fetch_model_info("localhost", 4000, "sk-key")
        assert result == []

    def test_propagates_http_error(self, monkeypatch):
        from codefreedom.cli.vscode import _fetch_model_info
        from codefreedom.core.http_client import HTTPStatusError

        def boom(url, timeout=10.0, **kw):
            raise HTTPStatusError("unauthorized", status_code=401, url="")

        monkeypatch.setattr("codefreedom.core.http_client._do_get", boom)
        with pytest.raises(HTTPStatusError):
            _fetch_model_info("localhost", 4000, "sk-key")


# ── _load_alias_models / _load_route_image_models ────────────────────────────


class TestLoadAliasModels:
    def test_returns_empty_when_no_config(self, tmp_path: Path):
        assert _load_alias_models(codefreedom_dir=tmp_path) == set()

    def test_reads_alias_from_config(self, tmp_path: Path):
        import yaml

        config_dir = tmp_path / "proxy" / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "config.yaml").write_text(
            yaml.safe_dump(
                {
                    "router_settings": {
                        "model_group_alias": {
                            "fable": "Qwen3.7-Max",
                            "opus": "Qwen3.7-Plus",
                        }
                    }
                }
            )
        )
        result = _load_alias_models(codefreedom_dir=tmp_path)
        assert result == {"fable", "opus"}


class TestLoadRouteImageModels:
    def test_returns_empty_when_no_config(self, tmp_path: Path):
        assert _load_route_image_models(codefreedom_dir=tmp_path) == set()

    def test_reads_route_image_from_config(self, tmp_path: Path):
        import yaml

        providers_dir = tmp_path / "proxy" / "config" / "providers"
        providers_dir.mkdir(parents=True)
        (providers_dir / "deepseek.yaml").write_text(
            yaml.safe_dump(
                {
                    "model_list": [
                        {
                            "model_name": "MiMo-V2.5",
                            "codefreedom": {
                                "plugins": {
                                    "route-image-request": {"enabled": True}
                                }
                            },
                        },
                        {
                            "model_name": "DeepSeek-V4-Flash",
                            "codefreedom": {
                                "plugins": {
                                    "route-image-request": {"enabled": True}
                                }
                            },
                        },
                        {
                            "model_name": "Other-Model",
                            "codefreedom": {
                                "plugins": {
                                    "route-image-request": {"enabled": False}
                                }
                            },
                        },
                    ]
                }
            )
        )
        result = _load_route_image_models(codefreedom_dir=tmp_path)
        assert result == {"MiMo-V2.5", "DeepSeek-V4-Flash"}
