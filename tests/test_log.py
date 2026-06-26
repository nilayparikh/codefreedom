"""Tests for log.py — stderr logging utilities."""

import pytest

from codefreedom.log import eprint

pytestmark = pytest.mark.unit


def test_eprint_outputs_to_stderr(capsys):
    eprint("test message")
    captured = capsys.readouterr()
    assert "test message" in captured.err


def test_eprint_with_multiple_args(capsys):
    eprint("arg1", "arg2", "arg3")
    captured = capsys.readouterr()
    assert "arg1" in captured.err
    assert "arg2" in captured.err
    assert "arg3" in captured.err


def test_eprint_with_kwargs(capsys):
    eprint("no newline", end="")
    captured = capsys.readouterr()
    assert captured.err == "no newline"
