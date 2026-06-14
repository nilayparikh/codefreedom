"""Tests for core/http_client.py — stdlib urllib wrapper functions."""

from unittest.mock import patch

import pytest

from codefreedom.core.http_client import (
    HTTPError,
    HTTPStatusError,
    Response,
    check_health,
    get_json,
    get_response,
    get_text,
)


def _make_response(status=200, body=b"{}", headers=None):
    """Helper to create a Response object."""
    hdrs = headers or {}
    return Response(status_code=status, headers=hdrs, body=body)


class TestGetJson:
    def test_returns_parsed_json(self):
        with patch("codefreedom.core.http_client._do_get",
                    return_value=_make_response(body=b'{"key": "value"}')):
            result = get_json("http://example.com/api")
            assert result == {"key": "value"}

    def test_passes_bearer_token(self):
        with patch("codefreedom.core.http_client._do_get",
                    return_value=_make_response()) as mock_get:
            get_json("http://example.com/api", bearer="sk-test")
            call_kwargs = mock_get.call_args.kwargs
            assert call_kwargs["headers"]["Authorization"] == "Bearer sk-test"

    def test_passes_custom_headers(self):
        with patch("codefreedom.core.http_client._do_get",
                    return_value=_make_response()) as mock_get:
            get_json("http://example.com/api", headers={"X-Custom": "val"})
            call_kwargs = mock_get.call_args.kwargs
            assert call_kwargs["headers"]["X-Custom"] == "val"

    def test_raises_on_http_error(self):
        with patch("codefreedom.core.http_client._do_get",
                    side_effect=HTTPStatusError("error", status_code=500, url="http://example.com")):
            with pytest.raises(HTTPStatusError):
                get_json("http://example.com/api")

    def test_respects_timeout(self):
        with patch("codefreedom.core.http_client._do_get",
                    return_value=_make_response()) as mock_get:
            get_json("http://example.com/api", timeout=3.0)
            assert mock_get.call_args.kwargs["timeout"] == 3.0


class TestGetText:
    def test_returns_decoded_text(self):
        with patch("codefreedom.core.http_client._do_get",
                    return_value=_make_response(body=b"hello world")):
            result = get_text("http://example.com")
            assert result == "hello world"

    def test_passes_custom_headers(self):
        with patch("codefreedom.core.http_client._do_get",
                    return_value=_make_response()) as mock_get:
            get_text("http://example.com", headers={"User-Agent": "test/1.0"})
            call_kwargs = mock_get.call_args.kwargs
            assert call_kwargs["headers"]["User-Agent"] == "test/1.0"

    def test_raises_on_http_error(self):
        with patch("codefreedom.core.http_client._do_get",
                    side_effect=HTTPStatusError("error", status_code=500, url="http://example.com")):
            with pytest.raises(HTTPStatusError):
                get_text("http://example.com")


class TestCheckHealth:
    def test_returns_true_on_2xx(self):
        with patch("codefreedom.core.http_client._do_get",
                    return_value=_make_response(status=200)):
            assert check_health("http://example.com") is True

    def test_returns_false_on_5xx(self):
        with patch("codefreedom.core.http_client._do_get",
                    side_effect=HTTPStatusError("err", status_code=500, url="")):
            assert check_health("http://example.com") is False

    def test_returns_false_on_connect_error(self):
        with patch("codefreedom.core.http_client._do_get",
                    side_effect=HTTPError("refused")):
            assert check_health("http://example.com") is False

    def test_returns_false_on_timeout(self):
        with patch("codefreedom.core.http_client._do_get",
                    side_effect=HTTPError("timed out")):
            assert check_health("http://example.com") is False


class TestGetResponse:
    def test_returns_response_object(self):
        resp = _make_response(body=b'{"ok":true}')
        with patch("codefreedom.core.http_client._do_get", return_value=resp):
            result = get_response("http://example.com/api")
            assert result is resp

    def test_passes_bearer_token(self):
        with patch("codefreedom.core.http_client._do_get",
                    return_value=_make_response()) as mock_get:
            get_response("http://example.com/api", bearer="sk-test")
            call_kwargs = mock_get.call_args.kwargs
            assert call_kwargs["headers"]["Authorization"] == "Bearer sk-test"

    def test_passes_custom_headers(self):
        with patch("codefreedom.core.http_client._do_get",
                    return_value=_make_response()) as mock_get:
            get_response("http://example.com", headers={"Accept": "text/html"})
            call_kwargs = mock_get.call_args.kwargs
            assert call_kwargs["headers"]["Accept"] == "text/html"

    def test_respects_timeout(self):
        with patch("codefreedom.core.http_client._do_get",
                    return_value=_make_response()) as mock_get:
            get_response("http://example.com/api", timeout=25.0)
            assert mock_get.call_args.kwargs["timeout"] == 25.0

    def test_raises_on_http_error(self):
        with patch("codefreedom.core.http_client._do_get",
                    side_effect=HTTPStatusError("not found", status_code=404, url="http://example.com")):
            with pytest.raises(HTTPStatusError):
                get_response("http://example.com/api")


class TestResponse:
    def test_json(self):
        resp = Response(status_code=200, headers={}, body=b'{"a": 1}')
        assert resp.json() == {"a": 1}

    def test_text(self):
        resp = Response(status_code=200, headers={}, body=b"hello")
        assert resp.text == "hello"

    def test_raise_for_status_on_2xx(self):
        resp = Response(status_code=200, headers={}, body=b"")
        resp.raise_for_status()

    def test_raise_for_status_on_4xx(self):
        resp = Response(status_code=404, headers={}, body=b"")
        with pytest.raises(HTTPStatusError) as exc_info:
            resp.raise_for_status()
        assert exc_info.value.status_code == 404
