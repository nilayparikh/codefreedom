"""Tests for doctor CLI — comprehensive diagnostic checks."""

# pyright: reportPrivateUsage = false

from pathlib import Path
from typing import Dict

import pytest
import yaml


from codefreedom.cli.manage.doctor import (
    CheckResult,
    _clear_checks,
    _section,
    _run_checks,
    _ok,
    _fail,
    _warn,
    _skip,
    _resolve_env_var_value,
    run,
)

# ═══════════════════════════════════════════════════════════════════════════════
# CheckResult tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCheckResult:
    def test_pass_is_truthy(self):
        assert _ok("everything fine")

    def test_fail_is_falsy(self):
        assert not _fail("something broke")

    def test_warn_is_falsy(self):
        assert not _warn("check this")

    def test_skip_is_falsy(self):
        assert not _skip("not applicable")

    def test_detail_stored(self):
        r = _fail("msg", "detail text")
        assert r.message == "msg"
        assert r.detail == "detail text"

    def test_status_strings(self):
        assert _ok("x").status == "PASS"
        assert _fail("x").status == "FAIL"
        assert _warn("x").status == "WARN"
        assert _skip("x").status == "SKIP"


# ═══════════════════════════════════════════════════════════════════════════════
# Check registration and runner tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCheckRegistry:

    def setup_method(self):
        _clear_checks()

    def test_register_and_run(self):
        @_section("Test Section")
        def _my_check() -> CheckResult:
            return _ok("test check")

        passed, failed, warned = _run_checks()
        assert passed == 1
        assert failed == 0
        assert warned == 0

    def test_multiple_checks_accumulate(self):
        _clear_checks()

        @_section("Section A")
        def _check_a() -> CheckResult:
            return _ok("a")

        @_section("Section A")
        def _check_b() -> CheckResult:
            return _fail("b")

        @_section("Section B")
        def _check_c() -> CheckResult:
            return _warn("c")

        passed, failed, warned = _run_checks()
        assert passed == 1
        assert failed == 1
        assert warned == 1

    def test_exception_in_check_is_caught(self):
        _clear_checks()

        @_section("Test")
        def _broken_check() -> CheckResult:
            raise ValueError("crash")

        passed, failed, warned = _run_checks()
        assert passed == 0
        assert failed == 1
        assert warned == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Integration tests — cf_dir structure checks
# ═══════════════════════════════════════════════════════════════════════════════


class TestCFDirChecks:
    """Test checks that inspect the CodeFreedom home directory."""

    def test_cf_dir_exists_passes(self, monkeypatch, tmp_path):
        """_check_cf_dir_exists should pass when the dir exists."""
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
        )
        _clear_checks()

        @_section("CodeFreedom Home")
        def _check() -> CheckResult:
            from codefreedom.cli.manage.doctor import _check_cf_dir_exists

            return _check_cf_dir_exists()

        passed, failed, warned = _run_checks()
        assert passed >= 1

    def test_cf_dir_missing_fails(self, monkeypatch):
        """_check_cf_dir_exists should fail when the dir does not exist."""
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir",
            lambda: Path("/nonexistent/cf"),
        )
        _clear_checks()

        @_section("CodeFreedom Home")
        def _check() -> CheckResult:
            from codefreedom.cli.manage.doctor import _check_cf_dir_exists

            return _check_cf_dir_exists()

        passed, failed, warned = _run_checks()
        assert failed >= 1

    def test_cf_dir_permissions_passes(self, monkeypatch, tmp_path):
        """_check_cf_dir_permissions should pass when dir is accessible."""
        tmp_path.chmod(0o755)
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
        )
        _clear_checks()

        @_section("CodeFreedom Home")
        def _check() -> CheckResult:
            from codefreedom.cli.manage.doctor import _check_cf_dir_permissions

            return _check_cf_dir_permissions()

        passed, failed, warned = _run_checks()
        assert passed >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Integration tests — Config file checks
# ═══════════════════════════════════════════════════════════════════════════════


class TestConfigFileChecks:

    def _setup_cf_dir(self, tmp_path: Path, files: Dict[str, str]) -> Path:
        """Create a fake ~/.codefreedom directory with specified files."""
        for rel_path, content in files.items():
            full = tmp_path / rel_path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content)
        return tmp_path

    def test_proxy_config_files_present(self, monkeypatch, tmp_path):
        self._setup_cf_dir(
            tmp_path,
            {
                "config/proxy/docker-compose.yaml": "services: {}\n",
                "config/proxy/config/config.yaml": "general_settings: {}\n",
            },
        )
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_config_dir", lambda: tmp_path / "config"
        )
        _clear_checks()

        @_section("Config Files")
        def _check() -> CheckResult:
            from codefreedom.cli.manage.doctor import _check_proxy_config_files

            return _check_proxy_config_files()

        passed, failed, warned = _run_checks()
        assert passed >= 1

    def test_proxy_config_files_missing_fails(self, monkeypatch, tmp_path):
        self._setup_cf_dir(tmp_path, {})
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_config_dir", lambda: tmp_path / "config"
        )
        _clear_checks()

        @_section("Config Files")
        def _check() -> CheckResult:
            from codefreedom.cli.manage.doctor import _check_proxy_config_files

            return _check_proxy_config_files()

        passed, failed, warned = _run_checks()
        assert failed >= 1

    def test_recipe_instruction_found(self, monkeypatch, tmp_path):
        config_dir = tmp_path / "config"
        self._setup_cf_dir(
            tmp_path,
            {
                "config/RECIPE.md": "# CodeFreedom Recipe: _default\n\nInstalled: 2025-01-01\n",
            },
        )
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
        )
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_config_dir", lambda: config_dir
        )
        _clear_checks()

        @_section("CodeFreedom Home")
        def _check() -> CheckResult:
            from codefreedom.cli.manage.doctor import _check_recipe_instruction

            return _check_recipe_instruction()

        passed, failed, warned = _run_checks()
        assert passed >= 1

    def test_recipe_instruction_missing_skips(self, monkeypatch, tmp_path):
        """Missing RECIPE.md is expected pre-init — should skip, not warn."""
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
        )
        _clear_checks()

        @_section("CodeFreedom Home")
        def _check() -> CheckResult:
            from codefreedom.cli.manage.doctor import _check_recipe_instruction

            return _check_recipe_instruction()

        passed, failed, warned = _run_checks()
        assert passed == 0
        assert failed == 0
        assert warned == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Integration tests — PostgreSQL / Proxy data checks
# ═══════════════════════════════════════════════════════════════════════════════


class TestPostgresChecks:

    def test_pg_data_dir_not_exists_ok(self, monkeypatch, tmp_path):
        """If pg/data doesn't exist yet, it should pass (will be auto-created)."""
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
        )
        _clear_checks()

        @_section("PostgreSQL / Proxy Data")
        def _check() -> CheckResult:
            from codefreedom.cli.manage.doctor import _check_pg_data_dir

            return _check_pg_data_dir()

        passed, failed, warned = _run_checks()
        assert passed >= 1

    def test_pg_data_dir_writable_ok(self, monkeypatch, tmp_path):
        """If pg/data exists and is writable, it should pass."""
        import sys

        if sys.platform == "win32":
            import os

            monkeypatch.setattr(os, "getuid", lambda: 1000, raising=False)
        pg_data = tmp_path / "pg" / "data"
        pg_data.mkdir(parents=True)
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
        )
        _clear_checks()

        @_section("PostgreSQL / Proxy Data")
        def _check() -> CheckResult:
            from codefreedom.cli.manage.doctor import _check_pg_data_dir

            return _check_pg_data_dir()

        passed, failed, warned = _run_checks()
        assert passed >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Integration tests — Env var checks
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnvVarChecks:

    def test_proxy_api_key_missing_fails(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
        )
        _clear_checks()

        @_section("Environment Variables (Proxy)")
        def _check() -> CheckResult:
            from codefreedom.cli.manage.doctor import _check_proxy_api_key

            return _check_proxy_api_key()

        passed, failed, warned = _run_checks()
        assert failed >= 1

    def test_proxy_api_key_in_machine_env_passes(self, monkeypatch, tmp_path):
        """Bare ``PROXY_API_KEY`` in os.environ satisfies the doctor check.

        CodeFreedom no longer reads ``.env.user`` or ``.env.*.secrets`` files
        for secrets — the doctor resolves solely from ``CF_CLI_*`` machine
        overrides and bare ``os.environ``. This test pins that path.
        """
        monkeypatch.setenv("PROXY_API_KEY", "sk-from-machine-env")
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
        )
        _clear_checks()

        @_section("Environment Variables (Proxy)")
        def _check() -> CheckResult:
            from codefreedom.cli.manage.doctor import _check_proxy_api_key

            return _check_proxy_api_key()

        passed, failed, warned = _run_checks()
        assert passed >= 1

    def test_proxy_api_key_cf_cli_override_passes(self, monkeypatch, tmp_path):
        """CF_CLI_PROXY_API_KEY in os.environ should satisfy the check."""
        monkeypatch.setenv("CF_CLI_PROXY_API_KEY", "sk-cf-cli-override")
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
        )
        _clear_checks()

        @_section("Environment Variables (Proxy)")
        def _check() -> CheckResult:
            from codefreedom.cli.manage.doctor import _check_proxy_api_key

            return _check_proxy_api_key()

        passed, failed, warned = _run_checks()
        assert passed >= 1

    def test_proxy_api_key_legacy_litellm_fallback_passes(self, monkeypatch, tmp_path):
        """Legacy ``CF_CLI_LITELLM_MASTER_KEY`` still satisfies the check."""
        monkeypatch.setenv("CF_CLI_LITELLM_MASTER_KEY", "sk-legacy")
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
        )
        _clear_checks()

        @_section("Environment Variables (Proxy)")
        def _check() -> CheckResult:
            from codefreedom.cli.manage.doctor import _check_proxy_api_key

            return _check_proxy_api_key()

        passed, failed, warned = _run_checks()
        assert passed >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Unit tests — _resolve_env_var_value
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolveEnvVarValue:

    def test_returns_none_when_not_found(self):
        """No source should return (None, None)."""
        value, source = _resolve_env_var_value("MY_VAR")
        assert value is None
        assert source is None

    def test_finds_direct_env_var(self, monkeypatch):
        """Direct os.environ value should be found."""
        monkeypatch.setenv("MY_VAR", "direct-value")
        value, source = _resolve_env_var_value("MY_VAR")
        assert value == "direct-value"
        assert source == "machine env"

    def test_finds_cf_cli_override(self, monkeypatch):
        """CF_CLI_MY_VAR should be found even without MY_VAR."""
        monkeypatch.setenv("CF_CLI_MY_VAR", "cf-cli-value")
        value, source = _resolve_env_var_value("MY_VAR")
        assert value == "cf-cli-value"
        assert source == "CF_CLI_* override"

    def test_cf_cli_takes_priority_over_direct(self, monkeypatch):
        """CF_CLI_MY_VAR should win over MY_VAR."""
        monkeypatch.setenv("CF_CLI_MY_VAR", "cf-cli-value")
        monkeypatch.setenv("MY_VAR", "direct-value")
        value, source = _resolve_env_var_value("MY_VAR")
        assert value == "cf-cli-value"
        assert source == "CF_CLI_* override"

    def test_finds_in_env_file(self, monkeypatch):
        """Value in machine env should be found (no .env file reading)."""
        monkeypatch.setenv("MY_VAR", "env-value")
        value, source = _resolve_env_var_value("MY_VAR")
        assert value == "env-value"
        assert source == "machine env"

    def test_env_file_ignored(self, tmp_path, monkeypatch):
        """.env files are no longer read — only machine env vars."""
        env_file = tmp_path / ".env.test"
        env_file.write_text("MY_VAR=file-value\n")
        value, source = _resolve_env_var_value("MY_VAR")
        assert value is None
        assert source is None

    def test_cf_cli_wins_over_env(self, monkeypatch):
        """CF_CLI_* should take priority over direct env."""
        monkeypatch.setenv("CF_CLI_MY_VAR", "override-value")
        monkeypatch.setenv("MY_VAR", "direct-value")
        value, source = _resolve_env_var_value("MY_VAR")
        assert value == "override-value"
        assert source == "CF_CLI_* override"


# ═══════════════════════════════════════════════════════════════════════════════
# Full run() integration test
# ═══════════════════════════════════════════════════════════════════════════════


class TestCheckProxyPort:
    """Regression tests for ``_check_proxy_port``.

    The previous version defined ``hint`` only inside the ``except``
    branch, so a healthy config would raise
    ``UnboundLocalError: cannot access local variable 'hint' where it
    is not associated with a value`` — crashing the entire check and
    surfacing as a ``[FAIL] Exception: ...`` line in the doctor output.
    """

    def test_returns_check_result_on_happy_path(self, monkeypatch, tmp_path):
        """A working config must not raise UnboundLocalError."""
        from codefreedom.cli.manage.doctor import _check_proxy_port

        # Provide a minimal profiles.yaml that load_config() can parse.
        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(yaml.dump({
            "common": {"proxy": {"bind_port": 5555}},
            "agents": {"claude-code": {"profiles": {"default": {"env": {}}}}},
            "tools": {"chrome": {}},
        }))
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_config_dir", lambda: tmp_path,
        )

        result = _check_proxy_port()
        assert isinstance(result, CheckResult)

    def test_falls_back_to_default_on_load_failure(self, monkeypatch):
        """When load_config() raises, the check must still return a result."""
        from codefreedom.cli.manage.doctor import _check_proxy_port

        def _boom():
            raise RuntimeError("synthetic load failure")

        # ``load_config`` is imported lazily inside _check_proxy_port, so
        # patch the source module — the import rebinds at call time.
        monkeypatch.setattr("codefreedom.config.load_config", _boom)
        result = _check_proxy_port()
        assert isinstance(result, CheckResult)


class TestRun:

    def test_run_with_empty_cf_dir(self, monkeypatch, tmp_path):
        """run() should not crash when cf_dir exists but has no config."""
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
        )
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.shutil.which", lambda _: None
        )

        # run() should return non-zero since many checks will fail
        result = run()
        assert result in (0, 1, 2)

    def test_run_with_verbose(self, monkeypatch, tmp_path):
        """run(verbose=True) should not crash."""
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
        )
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.shutil.which", lambda _: None
        )

        result = run(verbose=True)
        assert result in (0, 1, 2)


class TestCheckUnwiredProxyVars:
    """Tests for ``_check_unwired_proxy_vars``.

    Regression for the bug where a var set in ``override.yaml`` / ``.cf.yaml``
    was displayed by ``cf m dr`` but silently ignored by ``cf r px`` because
    the compose file used a hardcoded literal instead of ``${VAR}``.
    """

    def _write_compose(self, config_dir: Path, content: str) -> None:
        proxy_dir = config_dir / "proxy"
        proxy_dir.mkdir(parents=True, exist_ok=True)
        (proxy_dir / "docker-compose.yaml").write_text(content, encoding="utf-8")

    def test_warns_on_stale_hardcoded_compose(self, monkeypatch, tmp_path):
        from codefreedom.cli.manage.doctor import _check_unwired_proxy_vars

        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_config_dir", lambda: tmp_path
        )
        self._write_compose(
            tmp_path,
            'services:\n  litellm:\n    ports:\n      - "127.0.0.1:4000:4000"\n',
        )

        result = _check_unwired_proxy_vars()

        assert result.status == CheckResult.WARN
        assert "hardcoded literals" in result.message

    def test_warns_on_unwired_var(self, monkeypatch, tmp_path):
        from codefreedom.cli.manage.doctor import _check_unwired_proxy_vars

        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_config_dir", lambda: tmp_path
        )
        # Templated compose that references some vars but not the unwired one.
        # Must include ${PROXY_BIND_HOST} so it is not flagged as stale.
        self._write_compose(
            tmp_path,
            "services:\n  litellm:\n    ports:\n"
            '      - "${PROXY_BIND_HOST:-0.0.0.0}:${PROXY_PORT:-4000}:4000"\n'
            "    environment:\n"
            "      OPENCODE_SUB_ROUTING_ORDER: ${OPENCODE_SUB_ROUTING_ORDER:-10}\n",
        )
        # override.yaml declares a var not referenced in the compose file.
        (tmp_path / "override.yaml").write_text(
            yaml.safe_dump(
                {"vars": {"TOTALLY_UNWIRED_VAR": "x"}}, sort_keys=False
            ),
            encoding="utf-8",
        )
        # Avoid .cf.yaml walk-up picking up a real file.
        monkeypatch.setenv("CF_CLI_CF_YAML", "")

        result = _check_unwired_proxy_vars()

        assert result.status == CheckResult.WARN
        assert "TOTALLY_UNWIRED_VAR" in result.detail

    def test_passes_when_all_vars_wired(self, monkeypatch, tmp_path):
        from codefreedom.cli.manage.doctor import _check_unwired_proxy_vars

        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_config_dir", lambda: tmp_path
        )
        self._write_compose(
            tmp_path,
            "services:\n  litellm:\n    ports:\n"
            '      - "${PROXY_BIND_HOST:-0.0.0.0}:${PROXY_PORT:-4000}:4000"\n'
            "    environment:\n"
            "      OPENCODE_SUB_ROUTING_ORDER: ${OPENCODE_SUB_ROUTING_ORDER:-10}\n",
        )
        (tmp_path / "override.yaml").write_text(
            yaml.safe_dump(
                {"vars": {"OPENCODE_SUB_ROUTING_ORDER": "5"}}, sort_keys=False
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("CF_CLI_CF_YAML", "")

        result = _check_unwired_proxy_vars()

        assert result.status == CheckResult.PASS

    def test_skips_when_compose_missing(self, monkeypatch, tmp_path):
        from codefreedom.cli.manage.doctor import _check_unwired_proxy_vars

        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_config_dir", lambda: tmp_path
        )

        result = _check_unwired_proxy_vars()

        assert result.status == CheckResult.SKIP


pytestmark = pytest.mark.integration
