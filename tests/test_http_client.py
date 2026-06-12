"""Tests for core/http_client.py — httpx wrapper functions."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from codefreedom.core.http_client import check_health, get_json, get_text


class TestGetJson:
    def test_returns_parsed_json(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = {"key": "value"}
        with patch("httpx.get", return_value=mock_resp):
            result = get_json("http://example.com/api")
            assert result == {"key": "value"}

    def test_passes_bearer_token(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = {}
        with patch("httpx.get", return_value=mock_resp) as mock_get:
            get_json("http://example.com/api", bearer="sk-test")
            call_kwargs = mock_get.call_args.kwargs
            assert call_kwargs["headers"]["Authorization"] == "Bearer sk-test"

    def test_passes_custom_headers(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = {}
        with patch("httpx.get", return_value=mock_resp) as mock_get:
            get_json("http://example.com/api", headers={"X-Custom": "val"})
            call_kwargs = mock_get.call_args.kwargs
            assert call_kwargs["headers"]["X-Custom"] == "val"

    def test_raises_on_http_error(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=mock_resp
        )
        with patch("httpx.get", return_value=mock_resp):
            with pytest.raises(httpx.HTTPStatusError):
                get_json("http://example.com/api")

    def test_respects_timeout(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = {}
        with patch("httpx.get", return_value=mock_resp) as mock_get:
            get_json("http://example.com/api", timeout=3.0)
            assert mock_get.call_args.kwargs["timeout"] == 3.0


class TestGetText:
    def test_returns_decoded_text(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.text = "hello world"
        with patch("httpx.get", return_value=mock_resp):
            result = get_text("http://example.com")
            assert result == "hello world"

    def test_passes_custom_headers(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.text = ""
        with patch("httpx.get", return_value=mock_resp) as mock_get:
            get_text("http://example.com", headers={"User-Agent": "test/1.0"})
            call_kwargs = mock_get.call_args.kwargs
            assert call_kwargs["headers"]["User-Agent"] == "test/1.0"

    def test_raises_on_http_error(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=mock_resp
        )
        with patch("httpx.get", return_value=mock_resp):
            with pytest.raises(httpx.HTTPStatusError):
                get_text("http://example.com")


class TestCheckHealth:
    def test_returns_true_on_2xx(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        with patch("httpx.get", return_value=mock_resp):
            assert check_health("http://example.com") is True

    def test_returns_false_on_5xx(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 500
        with patch("httpx.get", return_value=mock_resp):
            assert check_health("http://example.com") is False

    def test_returns_false_on_connect_error(self):
        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            assert check_health("http://example.com") is False

    def test_returns_false_on_timeout(self):
        with patch("httpx.get", side_effect=httpx.ReadTimeout("timed out")):
            assert check_health("http://example.com") is False
