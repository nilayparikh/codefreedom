import sys
from io import StringIO

from codefreedom.log import eprint


def test_eprint_outputs_to_stderr():
    captured_stderr = StringIO()
    old_stderr = sys.stderr
    sys.stderr = captured_stderr
    try:
        eprint("test message")
        assert "test message" in captured_stderr.getvalue()
    finally:
        sys.stderr = old_stderr


def test_eprint_with_multiple_args():
    captured_stderr = StringIO()
    old_stderr = sys.stderr
    sys.stderr = captured_stderr
    try:
        eprint("arg1", "arg2", "arg3")
        output = captured_stderr.getvalue()
        assert "arg1" in output
        assert "arg2" in output
        assert "arg3" in output
    finally:
        sys.stderr = old_stderr


def test_eprint_with_kwargs():
    captured_stderr = StringIO()
    old_stderr = sys.stderr
    sys.stderr = captured_stderr
    try:
        eprint("no newline", end="")
        output = captured_stderr.getvalue()
        assert output == "no newline"
    finally:
        sys.stderr = old_stderr
