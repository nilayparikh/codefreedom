"""Test isolation — never touch the real ~/.codefreedom.

Sets CODEFREEDOM_HOME to a session-scoped temporary directory so all
calls to ``get_codefreedom_dir()`` return a test-only path.

Individual test modules may override this via ``monkeypatch.setenv``
for per-test isolation when needed.
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest


@pytest.fixture(scope="session", autouse=True)
def _codefreedom_test_home() -> str:
    """Session-scoped fixture: CODEFREEDOM_HOME points to a temp directory.

    Runs once per test session, before any test.  Cleans up after all
    tests complete.
    """
    saved = os.environ.get("CODEFREEDOM_HOME")
    tmp = tempfile.mkdtemp(prefix="codefreedom-test-")
    os.environ["CODEFREEDOM_HOME"] = tmp

    yield tmp

    # Restore (or clear) the env var
    if saved is not None:
        os.environ["CODEFREEDOM_HOME"] = saved
    else:
        os.environ.pop("CODEFREEDOM_HOME", None)

    # Remove the temp directory tree
    shutil.rmtree(tmp, ignore_errors=True)
