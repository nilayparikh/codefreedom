from __future__ import annotations

from unittest.mock import patch

import pytest

from codefreedom.core import remote_validation
from codefreedom.core.agent_runtime import PROXY_AUTH_REQUIRED, PROXY_OK, PROXY_UNREACHABLE

pytestmark = pytest.mark.unit


def test_validate_remote_proxy_url_allows_localhost_when_reachable():
    with patch.object(
        remote_validation, "fetch_proxy_models_with_status",
        return_value=([{"id": "m1"}], PROXY_OK),
    ) as mock:
        assert remote_validation.validate_remote_proxy_url("http://127.0.0.1:4000") is True
    mock.assert_called_once_with("http://127.0.0.1:4000", "")


def test_validate_remote_proxy_url_allows_localhost_hostname_when_reachable():
    with patch.object(
        remote_validation, "fetch_proxy_models_with_status",
        return_value=([{"id": "m1"}], PROXY_OK),
    ):
        assert remote_validation.validate_remote_proxy_url("http://localhost:4000") is True


def test_validate_remote_proxy_url_rejects_when_unreachable():
    with patch.object(
        remote_validation, "fetch_proxy_models_with_status",
        return_value=([], PROXY_UNREACHABLE),
    ):
        assert remote_validation.validate_remote_proxy_url("http://127.0.0.1:4000") is False


def test_validate_remote_proxy_url_passes_api_key_through():
    with patch.object(
        remote_validation, "fetch_proxy_models_with_status",
        return_value=([{"id": "m1"}], PROXY_OK),
    ) as mock:
        assert remote_validation.validate_remote_proxy_url("http://127.0.0.1:4000", "sk-1") is True
    mock.assert_called_once_with("http://127.0.0.1:4000", "sk-1")


def test_probe_remote_proxy_reports_auth_required():
    with patch.object(
        remote_validation, "fetch_proxy_models_with_status",
        return_value=([], PROXY_AUTH_REQUIRED),
    ):
        assert remote_validation.probe_remote_proxy("http://127.0.0.1:4000") == PROXY_AUTH_REQUIRED


def test_validate_remote_tool_url_allows_localhost_when_reachable():
    init_resp = (
        {"result": {"protocolVersion": "2024-11-05", "capabilities": {}}},
        {"mcp-session-id": "sess-123"},
    )
    list_resp = (
        {"result": {"tools": [{"name": "click"}, {"name": "screenshot"}]}},
        {},
    )
    responses = iter([init_resp, list_resp])

    with patch.object(remote_validation, "_mcp_post", side_effect=lambda *a, **kw: next(responses)):
        result = remote_validation.validate_remote_tool_url("chrome", "http://127.0.0.1:9223/mcp")

    assert result == ["click", "screenshot"]


def test_validate_remote_tool_url_handles_sse_response():
    sse_body = (
        'event: message\n'
        'data: {"result":{"tools":[{"name":"click"},{"name":"fill"}]}}\n'
    ).encode("utf-8")
    with patch.object(remote_validation, "_mcp_post") as mock_post:
        mock_post.side_effect = [
            (remote_validation._parse_mcp_response(sse_body), {"mcp-session-id": "s1"}),
            (remote_validation._parse_mcp_response(sse_body), {}),
        ]
        result = remote_validation.validate_remote_tool_url("chrome", "http://127.0.0.1:9223/mcp")

    assert result == ["click", "fill"]


def test_validate_remote_tool_url_rejects_when_unreachable():
    with patch.object(remote_validation, "_mcp_post", return_value=(None, {})):
        assert remote_validation.validate_remote_tool_url("chrome", "http://127.0.0.1:9223/mcp") == []


def test_validate_remote_tool_url_rejects_when_initialize_fails():
    error_resp = ({"error": {"code": -32000, "message": "bad"}}, {})
    with patch.object(remote_validation, "_mcp_post", return_value=error_resp):
        assert remote_validation.validate_remote_tool_url("chrome", "http://127.0.0.1:9223/mcp") == []


def test_validate_remote_tools_or_raise_skips_endpoints_without_url():
    endpoints = {"mcpServers": {"a": {"url": None}, "b": {}}}
    with patch("codefreedom.tools.registry.load_tool_mcp_endpoints", return_value=endpoints):
        remote_validation.validate_remote_tools_or_raise(["a", "b"])


def test_validate_remote_tools_or_raise_raises_when_unreachable():
    endpoints = {"mcpServers": {"chrome": {"url": "http://127.0.0.1:9223/mcp"}}}
    with patch("codefreedom.tools.registry.load_tool_mcp_endpoints", return_value=endpoints), \
            patch.object(remote_validation, "_mcp_post", return_value=(None, {})):
        with pytest.raises(remote_validation.RemoteValidationError):
            remote_validation.validate_remote_tools_or_raise(["chrome"])
