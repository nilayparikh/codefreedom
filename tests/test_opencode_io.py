"""I/O-dependent tests for OpenCode CLI.

Tests arg parsing and binary detection.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


class TestFindOpenCodeBinary:
    def test_returns_none_or_string(self):
        from codefreedom.cli.opencode import find_opencode_binary

        result = find_opencode_binary()
        assert result is None or isinstance(result, str)
