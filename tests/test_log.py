import pytest
from codefreedom.log import eprint
import sys
from io import StringIO

def test_eprint_outputs_to_stderr():
    captured_stderr = StringIO()
    sys.stderr = captured_stderr
    eprint("test message")
    sys.stderr = sys.__stderr__
    assert "test message" in captured_stderr.getvalue()

def test_eprint_with_multiple_args():
    captured_stderr = StringIO()
    sys.stderr = captured_stderr
    eprint("arg1", "arg2", "arg3")
    sys.stderr = sys.__stderr__
    output = captured_stderr.getvalue()
    assert "arg1" in output
    assert "arg2" in output
    assert "arg3" in output