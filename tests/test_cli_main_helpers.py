"""Unit tests for ``codefreedom.cli.main`` helper functions.

Pure logic only: no I/O, no subprocess, no network.
"""
from __future__ import annotations

import io
import sys

import pytest

from codefreedom.cli.main import _configure_streams

pytestmark = pytest.mark.unit


class TestConfigureStreams:
    def test_reconfigures_stdout_to_utf8(self, monkeypatch):
        stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        monkeypatch.setattr(sys, "stdout", stream)
        _configure_streams()
        assert stream.encoding.lower().replace("-", "") == "utf8"

    def test_reconfigures_stderr_to_utf8(self, monkeypatch):
        stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        monkeypatch.setattr(sys, "stderr", stream)
        _configure_streams()
        assert stream.encoding.lower().replace("-", "") == "utf8"

    def test_uses_replace_error_handler(self, monkeypatch):
        stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        monkeypatch.setattr(sys, "stdout", stream)
        _configure_streams()
        stream.write("→ ☃ — \u2192")
        stream.flush()
        raw = stream.buffer.getvalue().decode("utf-8")
        assert "→" in raw
        assert "\u2192" in raw

    def test_skips_streams_without_reconfigure(self, monkeypatch):
        class _NoReconfigure:
            encoding = "cp1252"

        fake = _NoReconfigure()
        monkeypatch.setattr(sys, "stdout", fake)
        _configure_streams()
        assert fake.encoding == "cp1252"

    def test_swallows_reconfigure_errors(self, monkeypatch):
        class _Boom:
            def reconfigure(self, **kwargs):
                raise OSError("nope")

        monkeypatch.setattr(sys, "stdout", _Boom())
        _configure_streams()

