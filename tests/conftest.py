"""Test isolation — never touch the real ~/.codefreedom.

Sets CODEFREEDOM_HOME to a function-scoped temporary directory so all
calls to ``get_codefreedom_dir()`` return a test-only path.

Individual test modules may override this via ``monkeypatch.setenv``
for per-test isolation when needed.
"""

from __future__ import annotations

import os
import subprocess

import pytest


@pytest.fixture(autouse=True)
def _codefreedom_test_home(tmp_path):  # type: ignore[misc]
    """Function-scoped fixture: CODEFREEDOM_HOME points to a temp directory.

    Runs once per test function. Each test gets its own isolated directory
    to prevent cross-test contamination.
    """
    saved = os.environ.get("CODEFREEDOM_HOME")
    saved_tool = os.environ.get("CODEFREEDOM_TOOL_HOME")
    os.environ["CODEFREEDOM_HOME"] = str(tmp_path)
    os.environ["CODEFREEDOM_TOOL_HOME"] = str(tmp_path)

    yield tmp_path

    if saved is not None:
        os.environ["CODEFREEDOM_HOME"] = saved
    else:
        os.environ.pop("CODEFREEDOM_HOME", None)
    if saved_tool is not None:
        os.environ["CODEFREEDOM_TOOL_HOME"] = saved_tool
    else:
        os.environ.pop("CODEFREEDOM_TOOL_HOME", None)


# Proxy API key env-var names that must be isolated from the real machine
# environment. ``resolve_proxy_api_key`` checks all of these, so a stray
# machine export would leak into tests and shadow the values a test sets
# explicitly. Cleared before each test; tests that need a key ``setenv`` it.
_PROXY_API_KEY_ENV_NAMES = (
    "PROXY_API_KEY",
    "CF_CLI_PROXY_API_KEY",
    "LITELLM_MASTER_KEY",
    "CF_CLI_LITELLM_MASTER_KEY",
)


@pytest.fixture(autouse=True)
def _isolate_proxy_api_key():
    """Clear proxy-API-key env vars so tests start from a clean slate."""
    saved = {name: os.environ.get(name) for name in _PROXY_API_KEY_ENV_NAMES}
    for name in _PROXY_API_KEY_ENV_NAMES:
        os.environ.pop(name, None)
    yield
    for name, val in saved.items():
        if val is not None:
            os.environ[name] = val
        else:
            os.environ.pop(name, None)


# ── Shared fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository with basic config."""
    subprocess.run(["git", "init"], capture_output=True, cwd=str(tmp_path))
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        capture_output=True, cwd=str(tmp_path),
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        capture_output=True, cwd=str(tmp_path),
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"],
        capture_output=True, cwd=str(tmp_path),
    )
    return tmp_path



