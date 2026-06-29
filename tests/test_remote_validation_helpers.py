from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from codefreedom.core import remote_validation

pytestmark = pytest.mark.unit


def test_validate_remote_proxy_url_allows_localhost_when_reachable():
    with patch.object(remote_validation, "fetch_proxy_models", return_value=[{"id": "m1"}]) as mock:
        assert remote_validation.validate_remote_proxy_url("http://127.0.0.1:4000") is True
    mock.assert_called_once_with("http://127.0.0.1:4000")


def test_validate_remote_proxy_url_allows_localhost_hostname_when_reachable():
    with patch.object(remote_validation, "fetch_proxy_models", return_value=[{"id": "m1"}]):
        assert remote_validation.validate_remote_proxy_url("http://localhost:4000") is True


def test_validate_remote_proxy_url_rejects_when_unreachable():
    with patch.object(remote_validation, "fetch_proxy_models", return_value=[]):
        assert remote_validation.validate_remote_proxy_url("http://127.0.0.1:4000") is False


def test_validate_remote_tool_url_allows_localhost_when_reachable():
    captured: dict = {}

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"result": {"tools": []}}).encode("utf-8")

    def _fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["data"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeResp()

    with patch.object(remote_validation.urllib.request, "urlopen", side_effect=_fake_urlopen):
        assert remote_validation.validate_remote_tool_url("chrome", "http://127.0.0.1:9223/mcp") is True

    assert captured["url"] == "http://127.0.0.1:9223/mcp"
    assert captured["data"]["method"] == "tools/list"
    assert captured["timeout"] == 5


def test_validate_remote_tool_url_rejects_when_unreachable():
    import urllib.error

    def _raise(req, timeout):
        raise urllib.error.URLError("no route")

    with patch.object(remote_validation.urllib.request, "urlopen", side_effect=_raise):
        assert remote_validation.validate_remote_tool_url("chrome", "http://127.0.0.1:9223/mcp") is False


def test_validate_remote_tools_or_raise_skips_endpoints_without_url():
    endpoints = {"mcpServers": {"a": {"url": None}, "b": {}}}
    with patch("codefreedom.tools.registry.load_tool_mcp_endpoints", return_value=endpoints):
        remote_validation.validate_remote_tools_or_raise(["a", "b"])


def test_validate_remote_tools_or_raise_raises_when_unreachable():
    import urllib.error

    endpoints = {"mcpServers": {"chrome": {"url": "http://127.0.0.1:9223/mcp"}}}
    with patch("codefreedom.tools.registry.load_tool_mcp_endpoints", return_value=endpoints), \
            patch.object(remote_validation.urllib.request, "urlopen", side_effect=urllib.error.URLError("nope")):
        with pytest.raises(remote_validation.RemoteValidationError):
            remote_validation.validate_remote_tools_or_raise(["chrome"])
