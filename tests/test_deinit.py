"""Tests for deinit CLI — full CodeFreedom teardown."""

# pyright: reportPrivateUsage = false

import argparse
import subprocess


from codefreedom.cli.setup.deinit import (
    _find_codefreedom_containers,
    _stop_and_remove_container,
    _stop_proxy,
    _stop_tools,
    _remove_codefreedom_dir,
    _list_codefreedom_images,
    _remove_codefreedom_images,
    _remove_codefreedom_volumes,
    _prune_dangling_images,
    _clean_docker_cache,
    run,
)

# ═══════════════════════════════════════════════════════════════════════════════
# _find_codefreedom_containers
# ═══════════════════════════════════════════════════════════════════════════════


class TestFindCodefreedomContainers:
    """Tests for _find_codefreedom_containers."""

    def test_no_docker(self, monkeypatch):
        """Returns empty list when no containers found."""
        monkeypatch.setattr(
            "codefreedom.cli.docker_utils.find_containers_by_base",
            lambda base_name: [],
        )
        assert _find_codefreedom_containers() == []

    def test_empty_output(self, monkeypatch):
        """Returns empty list when no containers match."""
        monkeypatch.setattr(
            "codefreedom.cli.docker_utils.find_containers_by_base",
            lambda base_name: [],
        )
        assert _find_codefreedom_containers() == []

    def test_matches_codefreedom_prefix(self, monkeypatch):
        """Returns containers matching the codefreedom- prefix."""
        monkeypatch.setattr(
            "codefreedom.cli.docker_utils.find_containers_by_base",
            lambda base_name: (
                ["codefreedom-a1b2", "codefreedom-c3d4"]
                if base_name == "codefreedom"
                else []
            ),
        )
        result = _find_codefreedom_containers()
        assert "codefreedom-a1b2" in result
        assert "codefreedom-c3d4" in result

    def test_matches_litellm_prefix(self, monkeypatch):
        """Returns containers matching the litellm-codefreedom- prefix."""
        monkeypatch.setattr(
            "codefreedom.cli.docker_utils.find_containers_by_base",
            lambda base_name: (
                ["litellm-codefreedom-0000"]
                if base_name == "litellm-codefreedom"
                else []
            ),
        )
        result = _find_codefreedom_containers()
        assert "litellm-codefreedom-0000" in result

    def test_deduplicates(self, monkeypatch):
        """Returns unique container names."""
        monkeypatch.setattr(
            "codefreedom.cli.docker_utils.find_containers_by_base",
            lambda base_name: (
                ["codefreedom-a1b2"]
                if base_name == "codefreedom"
                else []
            ),
        )
        result = _find_codefreedom_containers()
        assert result == ["codefreedom-a1b2"]


# ═══════════════════════════════════════════════════════════════════════════════
# _stop_and_remove_container
# ═══════════════════════════════════════════════════════════════════════════════


class TestStopAndRemoveContainer:
    """Tests for _stop_and_remove_container."""

    def test_runs_docker_rm_force(self, monkeypatch):
        """Calls docker rm -f with the container name."""
        calls = []

        def fake_run(cmd, *a, **kw):
            calls.append(cmd)
            return type("Proc", (object,), {"returncode": 0})()

        monkeypatch.setattr(subprocess, "run", fake_run)
        _stop_and_remove_container("test-container")
        assert len(calls) == 1
        assert calls[0] == ["docker", "rm", "-f", "test-container"]

    def test_no_error_on_failure(self, monkeypatch):
        """Does not raise on Docker failure."""
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: (_ for _ in ()).throw(subprocess.SubprocessError),
        )
        _stop_and_remove_container("test-container")  # should not raise


# ═══════════════════════════════════════════════════════════════════════════════
# _stop_proxy
# ═══════════════════════════════════════════════════════════════════════════════


class TestStopProxy:
    """Tests for _stop_proxy."""

    def test_noop_when_no_compose_file(self, tmp_path):
        """Returns 0 immediately when compose file does not exist."""
        assert _stop_proxy(tmp_path) == 0

    def test_runs_compose_down_when_compose_exists(self, tmp_path, monkeypatch):
        """Runs docker compose down when compose file exists."""
        proxy_dir = tmp_path / "proxy"
        proxy_dir.mkdir()
        compose_file = proxy_dir / "docker-compose.yaml"
        compose_file.write_text("version: '3'\n")

        calls = []

        def fake_run(cmd, *a, **kw):
            calls.append(cmd)
            return type("Proc", (object,), {"returncode": 0})()

        monkeypatch.setattr(subprocess, "run", fake_run)
        _stop_proxy(tmp_path)
        assert any("docker" in c and "compose" in c for c in calls)


# ═══════════════════════════════════════════════════════════════════════════════
# _stop_tools
# ═══════════════════════════════════════════════════════════════════════════════


class TestStopTools:
    """Tests for _stop_tools."""

    def test_returns_0_on_success(self, monkeypatch):
        """Returns 0 when tools stop successfully."""

        def fake_stop_all(*a, **kw):
            return 0

        monkeypatch.setattr("codefreedom.cli.run.tools.stop_all", fake_stop_all)

        assert _stop_tools() == 0

    def test_handles_import_error(self, monkeypatch):
        """Returns 1 when tools module fails."""

        def fake_stop_all(*a, **kw):
            raise RuntimeError("tools failure")

        monkeypatch.setattr("codefreedom.cli.run.tools.stop_all", fake_stop_all)

        assert _stop_tools() == 1


# ═══════════════════════════════════════════════════════════════════════════════
# _remove_codefreedom_dir
# ═══════════════════════════════════════════════════════════════════════════════


class TestRemoveCodefreedomDir:
    """Tests for _remove_codefreedom_dir."""

    def test_removes_directory(self, tmp_path):
        """Removes the directory and all its contents."""
        test_dir = tmp_path / ".codefreedom"
        test_dir.mkdir()
        (test_dir / "profiles").mkdir()
        (test_dir / "profiles" / "test.yaml").write_text("key: val\n")

        _remove_codefreedom_dir(test_dir)
        assert not test_dir.exists()

    def test_preserves_env_user(self, tmp_path):
        """Preserves .env.user by recreating it after rmtree."""
        test_dir = tmp_path / ".codefreedom"
        test_dir.mkdir()
        (test_dir / "profiles").mkdir()
        (test_dir / "profiles" / "test.yaml").write_text("key: val\n")
        (test_dir / ".env.user").write_text("MY_SECRET=abc123\n")

        _remove_codefreedom_dir(test_dir)

        # Directory should be recreated with .env.user
        assert test_dir.exists()
        assert (test_dir / ".env.user").exists()
        assert (test_dir / ".env.user").read_text() == "MY_SECRET=abc123\n"
        # Everything else should be gone
        assert not (test_dir / "profiles").exists()

    def test_preserves_env_user_empty_content(self, tmp_path):
        """Handles an empty .env.user gracefully."""
        test_dir = tmp_path / ".codefreedom"
        test_dir.mkdir()
        (test_dir / ".env.user").write_text("")

        _remove_codefreedom_dir(test_dir)

        assert test_dir.exists()
        assert (test_dir / ".env.user").exists()
        assert (test_dir / ".env.user").read_text() == ""

    def test_noop_when_not_exists(self, tmp_path, capsys):
        """Does nothing when directory does not exist."""
        test_dir = tmp_path / "nonexistent"
        _remove_codefreedom_dir(test_dir)
        captured = capsys.readouterr()
        assert "does not exist" in captured.err


# ═══════════════════════════════════════════════════════════════════════════════
# _list_codefreedom_images
# ═══════════════════════════════════════════════════════════════════════════════


class TestListCodefreedomImages:
    """Tests for _list_codefreedom_images."""

    def test_returns_images(self, monkeypatch):
        """Returns parsed image list from docker images output."""
        output = "nilayparikh/codefreedom:ubuntu-latest\nnilayparikh/codefreedom:cuda-latest\n"

        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: type(
                "Proc", (object,), {"returncode": 0, "stdout": output}
            )(),
        )
        result = _list_codefreedom_images()
        assert result == [
            "nilayparikh/codefreedom:ubuntu-latest",
            "nilayparikh/codefreedom:cuda-latest",
        ]

    def test_returns_empty_on_failure(self, monkeypatch):
        """Returns empty list when docker command fails."""
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: type(
                "Proc", (object,), {"returncode": 1, "stdout": ""}
            )(),
        )
        assert _list_codefreedom_images() == []

    def test_returns_empty_on_no_docker(self, monkeypatch):
        """Returns empty list when Docker is not available."""

        def raise_fn(*a, **kw):
            raise FileNotFoundError

        monkeypatch.setattr(subprocess, "run", raise_fn)
        assert _list_codefreedom_images() == []


# ═══════════════════════════════════════════════════════════════════════════════
# _remove_codefreedom_images
# ═══════════════════════════════════════════════════════════════════════════════


class TestRemoveCodefreedomImages:
    """Tests for _remove_codefreedom_images."""

    def test_removes_each_image(self, monkeypatch):
        """Calls docker image rm for each found image."""
        calls = []

        def fake_run(cmd, *a, **kw):
            calls.append(cmd)
            if "images" in cmd:
                return type(
                    "Proc",
                    (object,),
                    {
                        "returncode": 0,
                        "stdout": "nilayparikh/codefreedom:ubuntu-latest\nnilayparikh/codefreedom:chrome-latest\n",
                    },
                )()
            return type("Proc", (object,), {"returncode": 0})()

        monkeypatch.setattr(subprocess, "run", fake_run)
        _remove_codefreedom_images()
        rm_calls = [c for c in calls if "image" in c and "rm" in c]
        assert len(rm_calls) == 2
        assert rm_calls[0] == [
            "docker",
            "image",
            "rm",
            "-f",
            "nilayparikh/codefreedom:ubuntu-latest",
        ]

    def test_noop_when_no_images(self, monkeypatch):
        """Does nothing when no images found."""
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: type(
                "Proc", (object,), {"returncode": 0, "stdout": ""}
            )(),
        )
        _remove_codefreedom_images()  # should not raise


# ═══════════════════════════════════════════════════════════════════════════════
# _remove_codefreedom_volumes
# ═══════════════════════════════════════════════════════════════════════════════


class TestRemoveCodefreedomVolumes:
    """Tests for _remove_codefreedom_volumes."""

    def test_removes_existing_volumes(self, monkeypatch):
        """Removes volumes that exist."""
        calls = []

        def fake_run(cmd, *a, **kw):
            calls.append(cmd)
            if "inspect" in cmd:
                return type("Proc", (object,), {"returncode": 0})()
            return type("Proc", (object,), {"returncode": 0})()

        monkeypatch.setattr(subprocess, "run", fake_run)
        _remove_codefreedom_volumes()
        rm_calls = [c for c in calls if "volume" in c and "rm" in c]
        assert len(rm_calls) == 2
        assert ["docker", "volume", "rm", "codefreedom_pg_data"] in rm_calls
        assert ["docker", "volume", "rm", "codefreedom_pg_backup"] in rm_calls

    def test_skips_nonexistent_volumes(self, monkeypatch):
        """Skips volumes that do not exist."""
        calls = []

        def fake_run(cmd, *a, **kw):
            calls.append(cmd)
            if "inspect" in cmd:
                return type("Proc", (object,), {"returncode": 1})()
            return type("Proc", (object,), {"returncode": 0})()

        monkeypatch.setattr(subprocess, "run", fake_run)
        _remove_codefreedom_volumes()
        rm_calls = [c for c in calls if "volume" in c and "rm" in c]
        assert len(rm_calls) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# _prune_dangling_images
# ═══════════════════════════════════════════════════════════════════════════════


class TestPruneDanglingImages:
    """Tests for _prune_dangling_images."""

    def test_runs_docker_image_prune(self, monkeypatch):
        """Calls docker image prune -f."""
        calls = []

        def fake_run(cmd, *a, **kw):
            calls.append(cmd)
            return type(
                "Proc",
                (object,),
                {"returncode": 0, "stdout": "Total reclaimed space: 0B\n"},
            )()

        monkeypatch.setattr(subprocess, "run", fake_run)
        _prune_dangling_images()
        assert any("image" in c and "prune" in c for c in calls)

    def test_handles_failure(self, monkeypatch):
        """Does not raise on Docker failure."""
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: type(
                "Proc", (object,), {"returncode": 1, "stdout": ""}
            )(),
        )
        _prune_dangling_images()  # should not raise


# ═══════════════════════════════════════════════════════════════════════════════
# _clean_docker_cache
# ═══════════════════════════════════════════════════════════════════════════════


class TestCleanDockerCache:
    """Tests for _clean_docker_cache."""

    def test_calls_all_cleanup_functions(self, monkeypatch):
        """Calls images, volumes, and prune in order."""
        call_order = []

        monkeypatch.setattr(
            "codefreedom.cli.setup.deinit._remove_codefreedom_images",
            lambda: call_order.append("images"),
        )
        monkeypatch.setattr(
            "codefreedom.cli.setup.deinit._remove_codefreedom_volumes",
            lambda: call_order.append("volumes"),
        )
        monkeypatch.setattr(
            "codefreedom.cli.setup.deinit._prune_dangling_images",
            lambda: call_order.append("prune"),
        )
        _clean_docker_cache()
        assert call_order == ["images", "volumes", "prune"]


# ═══════════════════════════════════════════════════════════════════════════════
# run() — full integration
# ═══════════════════════════════════════════════════════════════════════════════


class TestRun:
    """Tests for the deinit run() entry point."""

    def _patch_all(self, monkeypatch):
        """Patch Docker subprocess calls and tools module."""
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: type("Proc", (object,), {"returncode": 0, "stdout": ""})(),
        )

        def fake_stop_all(*a, **kw):
            return 0

        monkeypatch.setattr("codefreedom.cli.run.tools.stop_all", fake_stop_all)

    def test_force_flag_skips_prompt(self, monkeypatch, tmp_path):
        """With --force, deletes the directory without prompting."""
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        self._patch_all(monkeypatch)

        # Create a fake codefreedom home with some content
        (tmp_path / "profiles").mkdir(parents=True)
        (tmp_path / "profiles" / "test.yaml").write_text("key: val\n")

        args = argparse.Namespace(force=True, clean_images=False)

        exit_code = run(args)
        assert exit_code == 0
        assert not tmp_path.exists()

    def test_no_force_prompts_and_aborts(self, monkeypatch, tmp_path):
        """Without --force, prompts and aborts on 'n'."""
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        self._patch_all(monkeypatch)
        (tmp_path / "profiles").mkdir(parents=True)

        args = argparse.Namespace(force=False, clean_images=False)

        monkeypatch.setattr("builtins.input", lambda prompt: "n")

        exit_code = run(args)
        assert exit_code == 1
        assert tmp_path.exists()  # directory should NOT be deleted

    def test_no_force_accepts_confirmation(self, monkeypatch, tmp_path):
        """Without --force, prompts and proceeds on 'y'."""
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        self._patch_all(monkeypatch)
        (tmp_path / "profiles").mkdir(parents=True)

        args = argparse.Namespace(force=False, clean_images=False)

        monkeypatch.setattr("builtins.input", lambda prompt: "y")

        exit_code = run(args)
        assert exit_code == 0
        assert not tmp_path.exists()

    def test_no_dir_noop(self, monkeypatch, tmp_path):
        """Returns 0 when codefreedom dir does not exist."""
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        self._patch_all(monkeypatch)
        args = argparse.Namespace(force=True, clean_images=False)

        exit_code = run(args)
        assert exit_code == 0

    def test_clean_images_flag_triggers_cleanup(self, monkeypatch, tmp_path):
        """With --clean-images, calls _clean_docker_cache."""
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        self._patch_all(monkeypatch)
        (tmp_path / "profiles").mkdir(parents=True)

        cleanup_called = []

        monkeypatch.setattr(
            "codefreedom.cli.setup.deinit._clean_docker_cache",
            lambda: cleanup_called.append(True),
        )
        monkeypatch.setattr(
            "codefreedom.cli.setup.deinit._list_codefreedom_images",
            lambda: ["nilayparikh/codefreedom:ubuntu-latest"],
        )

        args = argparse.Namespace(force=True, clean_images=True)
        exit_code = run(args)
        assert exit_code == 0
        assert cleanup_called

    def test_clean_images_without_force_prompts(self, monkeypatch, tmp_path):
        """With --clean-images but no --force, prompts before cleanup."""
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        self._patch_all(monkeypatch)
        (tmp_path / "profiles").mkdir(parents=True)

        cleanup_called = []

        monkeypatch.setattr(
            "codefreedom.cli.setup.deinit._clean_docker_cache",
            lambda: cleanup_called.append(True),
        )
        monkeypatch.setattr(
            "codefreedom.cli.setup.deinit._list_codefreedom_images",
            lambda: ["nilayparikh/codefreedom:ubuntu-latest"],
        )

        prompts = []

        def fake_input(prompt):
            prompts.append(prompt)
            return "y"

        monkeypatch.setattr("builtins.input", fake_input)

        args = argparse.Namespace(force=False, clean_images=True)
        exit_code = run(args)
        assert exit_code == 0
        assert cleanup_called
        assert len(prompts) == 2  # images prompt + directory prompt

    def test_clean_images_prompt_abort(self, monkeypatch, tmp_path):
        """With --clean-images, aborting image prompt returns 1."""
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        self._patch_all(monkeypatch)
        (tmp_path / "profiles").mkdir(parents=True)

        monkeypatch.setattr(
            "codefreedom.cli.setup.deinit._list_codefreedom_images",
            lambda: ["nilayparikh/codefreedom:ubuntu-latest"],
        )

        def fake_input(prompt):
            if "Continue" in prompt:
                return "n"
            return "y"

        monkeypatch.setattr("builtins.input", fake_input)

        args = argparse.Namespace(force=False, clean_images=True)
        exit_code = run(args)
        assert exit_code == 1

    def test_without_clean_images_skips_cleanup(self, monkeypatch, tmp_path):
        """Without --clean-images, skips image cleanup."""
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        self._patch_all(monkeypatch)
        (tmp_path / "profiles").mkdir(parents=True)

        cleanup_called = []

        monkeypatch.setattr(
            "codefreedom.cli.setup.deinit._clean_docker_cache",
            lambda: cleanup_called.append(True),
        )

        args = argparse.Namespace(force=True, clean_images=False)
        exit_code = run(args)
        assert exit_code == 0
        assert not cleanup_called
