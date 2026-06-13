"""Tests for proxy CLI — path resolution, validation, compose discovery."""

# pyright: reportPrivateUsage = false

import argparse
from pathlib import Path

import pytest
import yaml

from codefreedom.cli.run.proxy import (
    _find_compose_file,
    _find_config_file,
    _validate,
    _validate_basic,
    _env_is_set,
    run,
)

_FAKE_CF_DIR = Path("/nonexistent/.codefreedom")


class TestFindComposeFile:
    """Tests for _find_compose_file — only ~/.codefreedom/proxy/."""

    def test_finds_in_codefreedom_dir(self, monkeypatch, tmp_path):
        compose = tmp_path / "proxy" / "docker-compose.yaml"
        compose.parent.mkdir(parents=True)
        compose.write_text("")
        monkeypatch.setattr(
            "codefreedom.cli.run.proxy.get_codefreedom_dir", lambda: tmp_path
        )
        result = _find_compose_file()
        assert result == compose

    def test_returns_none_when_not_found(self, monkeypatch):
        monkeypatch.setattr(
            "codefreedom.cli.run.proxy.get_codefreedom_dir",
            lambda: Path("/nonexistent"),
        )
        result = _find_compose_file()
        assert result is None


class TestFindConfigFile:
    """Tests for _find_config_file — only ~/.codefreedom/proxy/config/."""

    def test_finds_in_codefreedom_dir(self, monkeypatch, tmp_path):
        config = tmp_path / "proxy" / "config" / "config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text("")
        monkeypatch.setattr(
            "codefreedom.cli.run.proxy.get_codefreedom_dir", lambda: tmp_path
        )
        result = _find_config_file()
        assert result == config

    def test_returns_none_when_not_found(self, monkeypatch):
        monkeypatch.setattr(
            "codefreedom.cli.run.proxy.get_codefreedom_dir",
            lambda: Path("/nonexistent"),
        )
        result = _find_config_file()
        assert result is None


class TestValidate:
    """Tests for _validate — config validation."""

    def test_valid_config_passes(self, monkeypatch, tmp_path):
        _write_proxy_config(
            tmp_path,
            {
                "include": [],
                "general_settings": {},
                "router_settings": {"model_group_alias": {}},
                "litellm_settings": {},
            },
        )
        monkeypatch.setattr(
            "codefreedom.cli.run.proxy.get_codefreedom_dir", lambda: tmp_path
        )
        result = _validate()
        assert result == 0

    def test_missing_config_file(self, monkeypatch):
        monkeypatch.setattr(
            "codefreedom.cli.run.proxy.get_codefreedom_dir",
            lambda: Path("/nonexistent"),
        )
        result = _validate()
        assert result == 1

    def test_yaml_parse_error(self, monkeypatch, tmp_path):
        _write_proxy_config(tmp_path, {})
        config_path = tmp_path / "proxy" / "config" / "config.yaml"
        config_path.write_text(": invalid yaml : :")
        monkeypatch.setattr(
            "codefreedom.cli.run.proxy.get_codefreedom_dir", lambda: tmp_path
        )
        result = _validate()
        assert result == 1

    def test_missing_provider_file_reported(self, monkeypatch, tmp_path):
        _write_proxy_config(
            tmp_path,
            {
                "include": ["providers/missing.yaml"],
                "general_settings": {},
                "router_settings": {},
                "litellm_settings": {},
            },
        )
        monkeypatch.setattr(
            "codefreedom.cli.run.proxy.get_codefreedom_dir", lambda: tmp_path
        )
        result = _validate()
        assert result == 1  # missing provider = validation failure


class TestValidateBasic:
    """Tests for _validate_basic (no PyYAML fallback)."""

    def test_finds_required_sections(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "include:\ngeneral_settings:\nrouter_settings:\nlitellm_settings:\nmodel_group_alias:\n"
        )
        errors = []
        _validate_basic(config, errors)
        assert len(errors) == 0

    def test_reports_missing_sections(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text("")
        errors = []
        _validate_basic(config, errors)
        assert len(errors) > 0


class TestEnvIsSet:
    """Tests for _env_is_set."""

    def test_set_var(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "value")
        assert _env_is_set("TEST_VAR") is True

    def test_unset_var(self):
        assert _env_is_set("NONEXISTENT_VAR") is False

    def test_empty_var(self, monkeypatch):
        monkeypatch.setenv("EMPTY_VAR", "")
        assert _env_is_set("EMPTY_VAR") is True


class TestRun:
    """Tests for the run() entry point."""

    def test_no_action_shows_help(self):
        args = argparse.Namespace(
            action="invalid",
            reset=False,
            port=4000,
            host="0.0.0.0",
        )
        result = run(args)
        assert result == 1

    def test_start_compose_not_found(self, monkeypatch):
        """start must return 1 if the compose file is missing."""
        args = argparse.Namespace(
            action="start",
            reset=False,
            port=4000,
            host="0.0.0.0",
        )
        monkeypatch.setattr(
            "codefreedom.cli.run.proxy._find_compose_file", lambda: None
        )
        result = run(args)
        assert result == 1

    def test_restart_calls_compose_restart(self, monkeypatch, tmp_path):
        """restart must call `docker compose restart` (no --docker flag)."""
        compose = tmp_path / "proxy" / "docker-compose.yaml"
        compose.parent.mkdir(parents=True)
        compose.write_text("")

        calls: list[list[str]] = []

        def fake_run(cmd, *_args, **_kwargs):
            calls.append(cmd)

            class _R:
                returncode = 0

            return _R()

        monkeypatch.setattr(
            "codefreedom.cli.run.proxy.get_codefreedom_dir", lambda: tmp_path
        )
        monkeypatch.setattr("codefreedom.cli.run.proxy.subprocess.run", fake_run)

        args = argparse.Namespace(
            action="restart",
            reset=False,
            port=4000,
            host="0.0.0.0",
        )
        result = run(args)
        assert result == 0
        assert len(calls) == 1
        # Must be `docker compose ... restart` (not down/up, not stop/start)
        assert calls[0][:3] == ["docker", "compose", "-f"]
        assert "restart" in calls[0]
        assert "down" not in calls[0]
        assert "up" not in calls[0]

    def test_restart_no_compose_file(self, monkeypatch):
        """restart returns 1 when compose file is missing."""
        args = argparse.Namespace(
            action="restart",
            reset=False,
            port=4000,
            host="0.0.0.0",
        )
        monkeypatch.setattr(
            "codefreedom.cli.run.proxy._find_compose_file", lambda: None
        )
        result = run(args)
        assert result == 1

    def test_restart_propagates_failure(self, monkeypatch, tmp_path):
        """restart returns non-zero exit code when compose restart fails."""
        compose = tmp_path / "proxy" / "docker-compose.yaml"
        compose.parent.mkdir(parents=True)
        compose.write_text("")

        def fake_run(*_args, **_kwargs):
            class _R:
                returncode = 1
                stderr = "compose error"

            return _R()

        monkeypatch.setattr(
            "codefreedom.cli.run.proxy.get_codefreedom_dir", lambda: tmp_path
        )
        monkeypatch.setattr("codefreedom.cli.run.proxy.subprocess.run", fake_run)

        args = argparse.Namespace(
            action="restart",
            reset=False,
            port=4000,
            host="0.0.0.0",
        )
        result = run(args)
        assert result == 1

    def test_start_overrides_port_and_host_in_env(self, monkeypatch, tmp_path):
        """`--port` and `--host` must set LITELLM_PORT/LITELLM_BIND_HOST
        in the subprocess env (for this run only — does not edit .env.proxy)."""
        compose = tmp_path / "proxy" / "docker-compose.yaml"
        compose.parent.mkdir(parents=True)
        compose.write_text("")

        captured_env: dict[str, str] = {}

        def fake_run(_cmd, *_args, **kwargs):
            captured_env.update(kwargs.get("env", {}))

            class _R:
                returncode = 0

            return _R()

        monkeypatch.setattr(
            "codefreedom.cli.run.proxy.get_codefreedom_dir", lambda: tmp_path
        )
        monkeypatch.setattr("codefreedom.cli.run.proxy.subprocess.run", fake_run)
        monkeypatch.setattr(
            "codefreedom.cli.run.proxy._ensure_web_bridge_image", lambda: 0
        )

        args = argparse.Namespace(
            action="start",
            reset=False,
            port=4001,
            host="127.0.0.1",
        )
        result = run(args)
        assert result == 0
        assert captured_env.get("LITELLM_PORT") == "4001"
        assert captured_env.get("LITELLM_BIND_HOST") == "127.0.0.1"


# ── helpers ──────────────────────────────────────────────────────────────────


def _write_proxy_config(tmp_path: Path, data: dict) -> Path:
    config_dir = tmp_path / "proxy" / "config"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "config.yaml"
    config_file.write_text(yaml.dump(data))
    return config_file


# ── web-bridge image helper ─────────────────────────────────────────────────


class TestWebBridgeBuildContext:
    """Tests for _web_bridge_build_context — locate docker/web-bridge/."""

    def test_finds_dockerfile_in_source_tree(self) -> None:
        """When the package is installed editable, the helper should find
        the real ``docker/web-bridge/Dockerfile.Bridge`` shipped with the
        source tree."""
        from codefreedom.cli.run.proxy import _web_bridge_build_context

        ctx = _web_bridge_build_context()
        # We only assert if the source tree is available — when installed
        # from a wheel the directory may be missing, in which case the
        # helper should return None (not raise).
        if ctx is not None:
            assert (ctx / "Dockerfile.Bridge").is_file()
            assert ctx.name == "web-bridge"

    def test_returns_none_when_dockerfile_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If ``codefreedom.__file__`` is rewritten to a path whose
        grandparent has no ``docker/web-bridge/`` directory, the helper
        should return None (not raise)."""
        import codefreedom

        # Build a temp layout that mimics src/codefreedom/ but without a
        # docker/ tree at the project root.
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            project_root = tmp_path / "fake-project"
            project_root.mkdir()
            pkg_dir = project_root / "src" / "codefreedom"
            pkg_dir.mkdir(parents=True)
            (pkg_dir / "__init__.py").write_text("")
            # No docker/ directory at project_root.

            monkeypatch.setattr(codefreedom, "__file__", str(pkg_dir / "__init__.py"))

            from codefreedom.cli.run.proxy import _web_bridge_build_context

            assert _web_bridge_build_context() is None


class TestEnsureWebBridgeImage:
    """Tests for _ensure_web_bridge_image — idempotent image check."""

    def test_image_present_skips_build(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When ``docker image inspect`` succeeds, no build is invoked."""
        from codefreedom.cli.run import proxy as proxy_mod

        calls: list[list[str]] = []

        def fake_run(cmd, *_args, **_kwargs):
            calls.append(cmd)

            class _R:
                returncode = 0
                stderr = ""
                stdout = ""

            return _R()

        monkeypatch.setattr(proxy_mod.subprocess, "run", fake_run)

        rc = (
            proxy_mod._ensure_web_bridge_image()
        )  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert rc == 0
        # First call: docker image inspect. No docker build should follow.
        assert any("inspect" in c for c in calls)
        assert not any("build" in c for c in calls)

    def test_image_missing_pull_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When the image is missing but ``docker pull`` succeeds,
        the helper should return 0 without building."""
        from codefreedom.cli.run import proxy as proxy_mod

        calls: list[list[str]] = []

        def fake_run(cmd, *_args, **_kwargs):
            calls.append(cmd)
            if "inspect" in cmd:
                rc = 1  # image not found
            else:
                rc = 0  # pull succeeds

            class _R:
                returncode = rc
                stderr = ""
                stdout = ""

            return _R()

        monkeypatch.setattr(proxy_mod.subprocess, "run", fake_run)

        rc = (
            proxy_mod._ensure_web_bridge_image()
        )  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert rc == 0
        # inspect + pull, no build
        assert any("inspect" in c for c in calls)
        assert any("pull" in c for c in calls)
        assert not any("build" in c for c in calls)

    def test_image_missing_and_source_tree_missing_warns(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the image is missing AND we can't locate the Dockerfile,
        the helper should warn (not crash) and return 0 — the rest of the
        proxy stack can still come up; only the bridge will be unhealthy.
        """
        from codefreedom.cli.run import proxy as proxy_mod

        def fake_run(*_args, **_kwargs):
            class _R:
                returncode = 1  # image inspect fails
                stderr = "No such image"
                stdout = ""

            return _R()

        monkeypatch.setattr(proxy_mod.subprocess, "run", fake_run)
        monkeypatch.setattr(proxy_mod, "_web_bridge_build_context", lambda: None)

        rc = (
            proxy_mod._ensure_web_bridge_image()
        )  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert rc == 0  # soft-warn, not hard-fail

    def test_image_missing_and_build_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the image is missing but the source tree is present and
        the build succeeds, the helper should return 0."""
        from codefreedom.cli.run import proxy as proxy_mod

        calls: list[list[str]] = []

        def fake_run(cmd, *_args, **_kwargs):
            calls.append(cmd)
            # The first call is `docker image inspect` (returns 1 because
            # the image is missing). The second call is `docker pull`
            # (returns 1 to simulate registry unavailable). The third
            # call is `docker build` (returns 0 to simulate a successful
            # local build).
            if "inspect" in cmd:
                rc = 1
            elif "pull" in cmd:
                rc = 1  # pull fails — fall back to local build
            else:
                rc = 0  # build succeeds

            class _R:
                returncode = rc
                stderr = ""
                stdout = ""

            return _R()

        monkeypatch.setattr(proxy_mod.subprocess, "run", fake_run)
        monkeypatch.setattr(
            proxy_mod, "_web_bridge_build_context", lambda: Path("/tmp/fake-bridge")
        )
        # The fake build context doesn't need to exist; the real subprocess
        # call is mocked.

        rc = (
            proxy_mod._ensure_web_bridge_image()
        )  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert rc == 0
        # Third call: docker build (after inspect and pull both failed).
        build_calls = [c for c in calls if "build" in c]
        assert len(build_calls) == 1
        # Tag should be the full registry reference (pushable without retag).
        assert "docker.io/nilayparikh/codefreedom:web-bridge" in build_calls[0]

    def test_build_failure_returns_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When the build subprocess returns non-zero, helper returns 1."""
        from codefreedom.cli.run import proxy as proxy_mod

        def fake_run(cmd, *_args, **_kwargs):
            if "inspect" in cmd:
                rc = 1
            else:
                rc = 1  # build also fails

            class _R:
                returncode = rc
                stderr = "build error"
                stdout = ""

            return _R()

        monkeypatch.setattr(proxy_mod.subprocess, "run", fake_run)
        monkeypatch.setattr(
            proxy_mod, "_web_bridge_build_context", lambda: Path("/tmp/fake-bridge")
        )

        rc = (
            proxy_mod._ensure_web_bridge_image()
        )  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert rc == 1
