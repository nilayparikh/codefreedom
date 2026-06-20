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


# ── Workflow lint (actionlint) ──────────────────────────────────────────────


class TestWorkflowLint:
    """Validate all GitHub Actions workflow files."""

    def test_actionlint(self) -> None:
        if not _docker_available():
            pytest.skip("Docker not available")
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


class TestDockerfileLint:
    """Validate all Dockerfiles."""

    @pytest.mark.parametrize(
        "dockerfile",
        [str(f.relative_to(REPO_ROOT)) for f in _all_dockerfiles()],
        ids=lambda p: p,
    )
    def test_hadolint(self, dockerfile: str) -> None:
        if not _docker_available():
            pytest.skip("Docker not available")
        path = REPO_ROOT / dockerfile
        result = subprocess.run(
            ["docker", "run", "--rm", "-i", "hadolint/hadolint", "hadolint", "--failure-threshold", "error", "-"],
            input=path.read_text(encoding="utf-8"),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            pytest.fail(f"{dockerfile} hadolint errors:\n{result.stdout}")

    @pytest.mark.parametrize(
        "dockerfile",
        [str(f.relative_to(REPO_ROOT)) for f in _all_dockerfiles()],
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
        [str(f.relative_to(REPO_ROOT)) for f in _all_dockerfiles()],
        ids=lambda p: p,
    )
    def test_dockerfile_has_version_arg(self, dockerfile: str) -> None:
        if dockerfile in _SKIP_HADOLINT:
            pytest.skip("build artifact")
        path = REPO_ROOT / dockerfile
        content = path.read_text(encoding="utf-8")
        assert "ARG IMAGE_VERSION" in content, (
            f"{dockerfile}: missing 'ARG IMAGE_VERSION'"
        )

    @pytest.mark.parametrize(
        "dockerfile",
        [str(f.relative_to(REPO_ROOT)) for f in _all_dockerfiles()],
        ids=lambda p: p,
    )
    def test_dockerfile_has_labels(self, dockerfile: str) -> None:
        if dockerfile in _SKIP_HADOLINT:
            pytest.skip("build artifact")
        path = REPO_ROOT / dockerfile
        content = path.read_text(encoding="utf-8")
        assert "LABEL " in content, f"{dockerfile}: missing LABEL instruction"
