"""Test isolation — never touch the real ~/.codefreedom.

Sets CODEFREEDOM_HOME to a function-scoped temporary directory so all
calls to ``get_codefreedom_dir()`` return a test-only path.

Individual test modules may override this via ``monkeypatch.setenv``
for per-test isolation when needed.
"""

from __future__ import annotations

import os

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
