"""Tests for workflow YAML and Dockerfile linting.

Uses actionlint (GitHub Actions) and hadolint (Dockerfile) via Docker.
Falls back to structural Python checks if Docker is unavailable.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
DOCKER_DIR = REPO_ROOT / "docker"

pytestmark = pytest.mark.unit


def _docker_available() -> bool:
    try:
        r = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=5
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _all_workflow_files() -> list[Path]:
    return sorted(WORKFLOWS_DIR.glob("*.yml")) + sorted(WORKFLOWS_DIR.glob("*.yaml"))


def _all_dockerfiles() -> list[Path]:
    return sorted(DOCKER_DIR.rglob("Dockerfile.*"))


def _docker_can_run_linux() -> bool:
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.OSType}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and "linux" in result.stdout.lower()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _docker_linux_image_available(image: str) -> bool:
    if not _docker_can_run_linux():
        return False
    try:
        result = subprocess.run(
            [
                "docker",
                "manifest",
                "inspect",
                image,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    output = result.stdout + result.stderr
    return '"os": "linux"' in output


# ── Workflow lint (actionlint) ──────────────────────────────────────────────


class TestWorkflowLint:
    """Validate all GitHub Actions workflow files."""

    def test_actionlint(self) -> None:
        if not _docker_available():
            pytest.skip("Docker not available")
        if not _docker_linux_image_available("rhysd/actionlint"):
            pytest.skip("actionlint image not available for this Docker platform")
        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"{REPO_ROOT}:/repo",
                "-w", "/repo",
                "rhysd/actionlint",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, (
            f"actionlint failed:\n{result.stdout}\n{result.stderr}"
        )

    @pytest.mark.parametrize(
        "workflow_file",
        [str(f.relative_to(REPO_ROOT)) for f in _all_workflow_files()],
        ids=lambda p: p,
    )
    def test_workflow_yaml_parses(self, workflow_file: str) -> None:
        path = REPO_ROOT / workflow_file
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict), f"{workflow_file}: not a valid YAML mapping"

    @pytest.mark.parametrize(
        "workflow_file",
        [str(f.relative_to(REPO_ROOT)) for f in _all_workflow_files()],
        ids=lambda p: p,
    )
    def test_workflow_dispatch_no_branches(self, workflow_file: str) -> None:
        path = REPO_ROOT / workflow_file
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        triggers = data.get("on") or data.get(True) or {}
        if isinstance(triggers, dict) and "workflow_dispatch" in triggers:
            dispatch = triggers["workflow_dispatch"]
            if isinstance(dispatch, dict):
                assert "branches" not in dispatch, (
                    f"{workflow_file}: 'branches' is not allowed under "
                    f"workflow_dispatch. Use a job-level 'if' condition instead."
                )


# ── Dockerfile lint (hadolint) ──────────────────────────────────────────────


_SKIP_HADOLINT = {
    "docker/litellm/Dockerfile.LitellmBase",
    "docker/litellm/Dockerfile.PgBase",
}

_SKIP_BUILD_ARTIFACT_CHECKS = {
    "docker/litellm/Dockerfile.LitellmBase",
    "docker/litellm/Dockerfile.PgBase",
}


class TestDockerfileLint:
    """Validate all Dockerfiles."""

    @pytest.mark.parametrize(
        "dockerfile",
        [f.relative_to(REPO_ROOT).as_posix() for f in _all_dockerfiles()],
        ids=lambda p: p,
    )
    def test_hadolint(self, dockerfile: str) -> None:
        if not _docker_available():
            pytest.skip("Docker not available")
        if not _docker_linux_image_available("hadolint/hadolint"):
            pytest.skip("hadolint image not available for this Docker platform")
        path = REPO_ROOT / dockerfile
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-i",
                "hadolint/hadolint",
                "hadolint",
                "--failure-threshold",
                "error",
                "-",
            ],
            input=path.read_text(encoding="utf-8").encode("utf-8"),
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            output = (result.stdout or result.stderr).decode("utf-8", errors="replace")
            pytest.fail(f"{dockerfile} hadolint errors:\n{output}")

    @pytest.mark.parametrize(
        "dockerfile",
        [f.relative_to(REPO_ROOT).as_posix() for f in _all_dockerfiles()],
        ids=lambda p: p,
    )
    def test_dockerfile_has_from(self, dockerfile: str) -> None:
        path = REPO_ROOT / dockerfile
        content = path.read_text(encoding="utf-8")
        lines = [
            line.strip()
            for line in content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        has_from = any(ln.upper().startswith("FROM ") for ln in lines)
        assert has_from, f"{dockerfile}: missing FROM instruction"

    @pytest.mark.parametrize(
        "dockerfile",
        [f.relative_to(REPO_ROOT).as_posix() for f in _all_dockerfiles()],
        ids=lambda p: p,
    )
    def test_dockerfile_has_version_arg(self, dockerfile: str) -> None:
        if dockerfile in _SKIP_BUILD_ARTIFACT_CHECKS:
            pytest.skip("build artifact")
        path = REPO_ROOT / dockerfile
        content = path.read_text(encoding="utf-8")
        assert "ARG IMAGE_VERSION" in content, (
            f"{dockerfile}: missing 'ARG IMAGE_VERSION'"
        )

    @pytest.mark.parametrize(
        "dockerfile",
        [f.relative_to(REPO_ROOT).as_posix() for f in _all_dockerfiles()],
        ids=lambda p: p,
    )
    def test_dockerfile_has_labels(self, dockerfile: str) -> None:
        if dockerfile in _SKIP_BUILD_ARTIFACT_CHECKS:
            pytest.skip("build artifact")
        path = REPO_ROOT / dockerfile
        content = path.read_text(encoding="utf-8")
        assert "LABEL " in content, f"{dockerfile}: missing LABEL instruction"
