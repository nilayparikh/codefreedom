"""Tests for doctor CLI — comprehensive diagnostic checks."""

# pyright: reportPrivateUsage = false

from pathlib import Path
from typing import Dict


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

    def test_env_files_all_present(self, monkeypatch, tmp_path):
        self._setup_cf_dir(
            tmp_path,
            {
                ".env.claude": "KEY=val\n",
                ".env.claude.secrets": "SECRET=abc\n",
                ".env.mimo.secrets": "MIMO_KEY=abc\n",
                ".env.opencode.secrets": "OPENCODE_KEY=abc\n",
                ".env.proxy": "PORT=4000\n",
                ".env.proxy.secrets": "KEY=xyz\n",
                ".env.user": "CUSTOM=val\n",
            },
        )
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
        )
        _clear_checks()

        @_section("Config Files")
        def _check() -> CheckResult:
            from codefreedom.cli.manage.doctor import _check_env_files

            return _check_env_files()

        passed, failed, warned = _run_checks()
        assert passed >= 1

    def test_env_files_missing_warns(self, monkeypatch, tmp_path):
        """Missing env files should produce a warning, not a failure."""
        self._setup_cf_dir(tmp_path, {})  # empty cf_dir
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
        )
        _clear_checks()

        @_section("Config Files")
        def _check() -> CheckResult:
            from codefreedom.cli.manage.doctor import _check_env_files

            return _check_env_files()

        passed, failed, warned = _run_checks()
        assert warned >= 1

    def test_proxy_config_files_present(self, monkeypatch, tmp_path):
        self._setup_cf_dir(
            tmp_path,
            {
                "proxy/docker-compose.yaml": "services: {}\n",
                "proxy/config/config.yaml": "general_settings: {}\n",
            },
        )
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
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
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
        )
        _clear_checks()

        @_section("Config Files")
        def _check() -> CheckResult:
            from codefreedom.cli.manage.doctor import _check_proxy_config_files

            return _check_proxy_config_files()

        passed, failed, warned = _run_checks()
        assert failed >= 1

    def test_recipe_instruction_found(self, monkeypatch, tmp_path):
        self._setup_cf_dir(
            tmp_path,
            {
                "RECIPE.md": "# CodeFreedom Recipe: _default\n\nInstalled: 2025-01-01\n",
            },
        )
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
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

    def test_litellm_master_key_missing_fails(self, monkeypatch, tmp_path):
        monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
        monkeypatch.delenv("CF_CLI_LITELLM_MASTER_KEY", raising=False)
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
        )
        _clear_checks()

        @_section("Environment Variables (Proxy)")
        def _check() -> CheckResult:
            from codefreedom.cli.manage.doctor import _check_litellm_master_key

            return _check_litellm_master_key()

        passed, failed, warned = _run_checks()
        assert failed >= 1

    def test_litellm_master_key_in_env_passes(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test-key")
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
        )
        _clear_checks()

        @_section("Environment Variables (Proxy)")
        def _check() -> CheckResult:
            from codefreedom.cli.manage.doctor import _check_litellm_master_key

            return _check_litellm_master_key()

        passed, failed, warned = _run_checks()
        assert passed >= 1

    def test_litellm_master_key_in_env_file_passes(self, monkeypatch, tmp_path):
        """Key set in .env.proxy.secrets should be detected."""
        secrets_file = tmp_path / ".env.proxy.secrets"
        secrets_file.write_text("LITELLM_MASTER_KEY=sk-from-file\n")
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
        )
        _clear_checks()

        @_section("Environment Variables (Proxy)")
        def _check() -> CheckResult:
            from codefreedom.cli.manage.doctor import _check_litellm_master_key

            return _check_litellm_master_key()

        passed, failed, warned = _run_checks()
        assert passed >= 1

    def test_litellm_master_key_cf_cli_override_passes(self, monkeypatch, tmp_path):
        """CF_CLI_LITELLM_MASTER_KEY in os.environ should satisfy the check."""
        monkeypatch.setenv("CF_CLI_LITELLM_MASTER_KEY", "sk-cf-cli-override")
        monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
        )
        _clear_checks()

        @_section("Environment Variables (Proxy)")
        def _check() -> CheckResult:
            from codefreedom.cli.manage.doctor import _check_litellm_master_key

            return _check_litellm_master_key()

        passed, failed, warned = _run_checks()
        assert passed >= 1

    def test_litellm_master_key_cf_cli_wins_over_direct(self, monkeypatch, tmp_path):
        """CF_CLI_LITELLM_MASTER_KEY should be detected even when LITELLM_MASTER_KEY is also set."""
        monkeypatch.setenv("CF_CLI_LITELLM_MASTER_KEY", "sk-cf-cli-wins")
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-direct")
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
        )
        _clear_checks()

        @_section("Environment Variables (Proxy)")
        def _check() -> CheckResult:
            from codefreedom.cli.manage.doctor import _check_litellm_master_key

            return _check_litellm_master_key()

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
        assert source == "MY_VAR (machine env)"

    def test_finds_cf_cli_override(self, monkeypatch):
        """CF_CLI_MY_VAR should be found even without MY_VAR."""
        monkeypatch.setenv("CF_CLI_MY_VAR", "cf-cli-value")
        value, source = _resolve_env_var_value("MY_VAR")
        assert value == "cf-cli-value"
        assert "CF_CLI_MY_VAR" in source

    def test_cf_cli_takes_priority_over_direct(self, monkeypatch):
        """CF_CLI_MY_VAR should win over MY_VAR."""
        monkeypatch.setenv("CF_CLI_MY_VAR", "cf-cli-value")
        monkeypatch.setenv("MY_VAR", "direct-value")
        value, source = _resolve_env_var_value("MY_VAR")
        assert value == "cf-cli-value"
        assert "CF_CLI_MY_VAR" in source

    def test_finds_in_env_file(self, tmp_path):
        """Value in an env file should be found."""
        env_file = tmp_path / ".env.test"
        env_file.write_text("MY_VAR=file-value\n")
        value, source = _resolve_env_var_value("MY_VAR", env_files=[env_file])
        assert value == "file-value"
        assert "in .env.test" in source

    def test_env_file_ignored_when_change_me(self, tmp_path):
        """CHANGE_ME placeholder values should be treated as unset."""
        env_file = tmp_path / ".env.test"
        env_file.write_text("MY_VAR=CHANGE_ME\n")
        value, source = _resolve_env_var_value("MY_VAR", env_files=[env_file])
        assert value is None
        assert source is None

    def test_env_file_ignored_when_empty(self, tmp_path):
        """Empty values in env files should be treated as unset."""
        env_file = tmp_path / ".env.test"
        env_file.write_text("MY_VAR=\n")
        value, source = _resolve_env_var_value("MY_VAR", env_files=[env_file])
        assert value is None
        assert source is None

    def test_cf_cli_wins_over_env_file(self, monkeypatch, tmp_path):
        """CF_CLI_* should take priority over an env file."""
        monkeypatch.setenv("CF_CLI_MY_VAR", "override-value")
        env_file = tmp_path / ".env.test"
        env_file.write_text("MY_VAR=file-value\n")
        value, source = _resolve_env_var_value("MY_VAR", env_files=[env_file])
        assert value == "override-value"
        assert "CF_CLI_MY_VAR" in source


# ═══════════════════════════════════════════════════════════════════════════════
# Full run() integration test
# ═══════════════════════════════════════════════════════════════════════════════


class TestRun:

    def test_run_with_empty_cf_dir(self, monkeypatch, tmp_path):
        """run() should not crash when cf_dir exists but has no config."""
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
        )
        monkeypatch.setattr("codefreedom.cli.manage.doctor.shutil.which", lambda _: None)

        # run() should return non-zero since many checks will fail
        result = run()
        assert result in (0, 1, 2)

    def test_run_with_verbose(self, monkeypatch, tmp_path):
        """run(verbose=True) should not crash."""
        monkeypatch.setattr(
            "codefreedom.cli.manage.doctor.get_codefreedom_dir", lambda: tmp_path
        )
        monkeypatch.setattr("codefreedom.cli.manage.doctor.shutil.which", lambda _: None)

        result = run(verbose=True)
        assert result in (0, 1, 2)
