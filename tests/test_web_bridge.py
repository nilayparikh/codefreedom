"""Tests for the web-bridge (SearXNG-shaped → Camoufox MCP web_search).

The bridge lives in ``docker/web-bridge/app/bridge.py`` and is not part of
the installable ``codefreedom`` package. We add its parent directory to
``sys.path`` here so the tests can import it directly. ``httpx`` and
``fastapi`` are added to the ``dev`` extras in ``pyproject.toml``.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Make the bridge importable.
_BRIDGE_PARENT = Path(__file__).parent.parent / "docker" / "web-bridge"
if str(_BRIDGE_PARENT) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_PARENT))

httpx = pytest.importorskip("httpx")  # noqa: E402
fastapi = pytest.importorskip("fastapi")  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import bridge  # noqa: E402


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_bridge_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset module-level mutable state between tests."""
    bridge._last_call_ts = None
    bridge._call_lock_token = None
    monkeypatch.setattr(bridge, "COOLDOWN_SECONDS", 2.0)
    monkeypatch.setattr(bridge, "MCP_WEB_URL", "http://mcp.test/mcp")
    monkeypatch.setattr(bridge, "MCP_TIMEOUT_SECONDS", 5.0)


@pytest.fixture
def client() -> TestClient:
    return TestClient(bridge.app)


def _make_response(
    status_code: int = 200,
    json_body: dict | None = None,
    text: str = "",
    headers: dict[str, str] | None = None,
) -> MagicMock:
    """Build a minimal ``httpx.Response``-shaped mock."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    if json_body is not None:
        resp.json.return_value = json_body
        # Bridge parser reads `.text` and supports either plain JSON text
        # or SSE event frames.
        import json as _json

        resp.text = _json.dumps(json_body)
    else:
        resp.json.side_effect = ValueError("no json")
        resp.text = text
    return resp


# ── Response parser tests ─────────────────────────────────────────────────


class TestParseJsonOrSse:
    """Unit tests for MCP response parser (JSON + SSE)."""

    def test_parses_plain_json(self) -> None:
        payload = '{"jsonrpc":"2.0","id":"1","result":{"ok":true}}'
        out = bridge._parse_json_or_sse(payload)
        assert out["jsonrpc"] == "2.0"
        assert out["id"] == "1"
        assert out["result"]["ok"] is True

    def test_parses_sse_message(self) -> None:
        payload = (
            "event: message\n"
            "data: {\"jsonrpc\":\"2.0\",\"id\":\"1\",\"result\":{\"ok\":true}}\n"
        )
        out = bridge._parse_json_or_sse(payload)
        assert out["jsonrpc"] == "2.0"
        assert out["id"] == "1"
        assert out["result"]["ok"] is True

    def test_raises_on_empty_body(self) -> None:
        with pytest.raises(ValueError):
            bridge._parse_json_or_sse("   ")

    def test_raises_on_sse_without_data_lines(self) -> None:
        with pytest.raises(ValueError):
            bridge._parse_json_or_sse("event: ping\n")


# ── Mapper tests ───────────────────────────────────────────────────────────


class TestMapMcpToSearxng:
    """Direct unit tests for the field-by-field mapper."""

    def test_basic_results(self) -> None:
        mcp = {
            "query": "fastapi",
            "results": [
                {
                    "title": "FastAPI",
                    "url": "https://fastapi.tiangolo.com",
                    "snippet": "Modern web framework",
                    "engine": "brave",
                }
            ],
            "ai_summaries": [],
        }
        out = bridge._map_mcp_to_searxng(mcp, query="fastapi")
        assert out["query"] == "fastapi"
        assert out["number_of_results"] == 1
        assert out["results"][0]["title"] == "FastAPI"
        assert out["results"][0]["url"] == "https://fastapi.tiangolo.com"
        assert out["results"][0]["content"] == "Modern web framework"
        assert out["results"][0]["engine"] == "brave"
        assert out["answers"] == []

    def test_ai_summaries_become_answers(self) -> None:
        mcp = {
            "query": "fastapi",
            "results": [],
            "ai_summaries": [
                {
                    "text": "FastAPI is a modern Python web framework.",
                    "sources": [
                        {
                            "text": "FastAPI docs",
                            "url": "https://fastapi.tiangolo.com",
                        }
                    ],
                }
            ],
        }
        out = bridge._map_mcp_to_searxng(mcp, query="fastapi")
        assert out["answers"] == [
            "FastAPI is a modern Python web framework."
        ]
        # Source URL is merged into results[] with engine="ai".
        assert out["number_of_results"] == 1
        assert out["results"][0]["url"] == "https://fastapi.tiangolo.com"
        assert out["results"][0]["engine"] == "ai"

    def test_dedupes_results(self) -> None:
        mcp = {
            "query": "x",
            "results": [
                {"title": "A", "url": "https://x.com/1", "snippet": "a", "engine": "b"},
                {"title": "A2", "url": "https://x.com/1", "snippet": "a2", "engine": "b"},
            ],
            "ai_summaries": [],
        }
        out = bridge._map_mcp_to_searxng(mcp, query="x")
        assert out["number_of_results"] == 1

    def test_merges_results_and_ai_sources(self) -> None:
        mcp = {
            "query": "x",
            "results": [
                {"title": "Org", "url": "https://org.com", "snippet": "s", "engine": "bing"},
            ],
            "ai_summaries": [
                {
                    "text": "summary",
                    "sources": [
                        {"text": "src", "url": "https://org.com"},  # dup with results
                        {"text": "src2", "url": "https://other.com"},
                    ],
                }
            ],
        }
        out = bridge._map_mcp_to_searxng(mcp, query="x")
        urls = {r["url"] for r in out["results"]}
        assert urls == {"https://org.com", "https://other.com"}
        assert out["number_of_results"] == 2

    def test_error_passthrough(self) -> None:
        mcp = {
            "query": "x",
            "results": [],
            "ai_summaries": [],
            "error": "No search engines configured.",
        }
        out = bridge._map_mcp_to_searxng(mcp, query="x")
        assert "error" in out
        assert "No search engines" in out["error"]
        assert out["results"] == []
        assert out["number_of_results"] == 0

    def test_missing_fields_handled(self) -> None:
        """Mapper should not crash on minimal/odd MCP payloads."""
        out = bridge._map_mcp_to_searxng({}, query="x")
        assert out["query"] == "x"
        assert out["results"] == []
        assert out["answers"] == []
        assert out["number_of_results"] == 0

    def test_non_dict_entries_ignored(self) -> None:
        mcp = {
            "query": "x",
            "results": [
                "not a dict",
                {"title": "ok", "url": "https://ok.com", "snippet": "ok", "engine": "ok"},
            ],
            "ai_summaries": [None, {"text": "t"}],
        }
        out = bridge._map_mcp_to_searxng(mcp, query="x")
        assert out["number_of_results"] == 1
        assert out["answers"] == ["t"]


# ── Cooldown tests ─────────────────────────────────────────────────────────


class TestCooldown:
    """Pure logic tests for the cooldown state machine."""

    def test_initial_state_allows_call(self) -> None:
        assert bridge._cooldown_remaining() == 0.0

    def test_within_window_blocks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(bridge, "COOLDOWN_SECONDS", 5.0)
        bridge._last_call_ts = time.monotonic()
        assert bridge._cooldown_remaining() > 0.0

    def test_after_window_allows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(bridge, "COOLDOWN_SECONDS", 0.01)
        bridge._last_call_ts = time.monotonic() - 1.0
        assert bridge._cooldown_remaining() == 0.0


# ── HTTP endpoint tests ────────────────────────────────────────────────────


class TestHealthz:
    def test_healthz_returns_ok(self, client: TestClient) -> None:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestSearchEndpoint:
    """HTTP-level tests using FastAPI's TestClient + mocked httpx."""

    def test_missing_query_returns_422(self, client: TestClient) -> None:
        resp = client.get("/search")
        assert resp.status_code == 422

    def test_successful_search_returns_searxng_json(
        self, client: TestClient
    ) -> None:
        """End-to-end: /search with a mocked MCP returns SearXNG-shaped JSON."""
        # 1. initialize → session id header
        init_resp = _make_response(200, headers={"mcp-session-id": "sess-123"})
        # 2. notifications/initialized → 2xx
        notif_resp = _make_response(202, text="")
        # 3. tools/call → JSON-RPC success with the tool's text payload
        call_resp = _make_response(
            200,
            json_body={
                "jsonrpc": "2.0",
                "id": "x",
                "result": {
                    "isError": False,
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                '{"query":"fastapi","results":[{"title":"FastAPI",'
                                '"url":"https://fastapi.tiangolo.com",'
                                '"snippet":"Web framework","engine":"brave"}],'
                                '"ai_summaries":[]}'
                            ),
                        }
                    ],
                },
            },
        )

        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=[init_resp, notif_resp, call_resp])

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch("app.bridge.httpx.AsyncClient", return_value=mock_ctx) as cls:
            resp = client.get("/search", params={"q": "fastapi"})

        # The bridge should have constructed an AsyncClient exactly once
        # (the request is stateless — one client per HTTP call).
        cls.assert_called_once()
        assert resp.status_code == 200
        body = resp.json()
        assert body["query"] == "fastapi"
        assert body["number_of_results"] == 1
        assert body["results"][0]["url"] == "https://fastapi.tiangolo.com"
        assert body["results"][0]["engine"] == "brave"
        # Cooldown is now armed.
        assert bridge._last_call_ts is not None

    def test_cooldown_returns_429(self, client: TestClient) -> None:
        """A second call within the cooldown window returns HTTP 429."""
        # First call arms the cooldown.
        init_resp = _make_response(200, headers={"mcp-session-id": "s1"})
        notif_resp = _make_response(202)
        call_resp = _make_response(
            200,
            json_body={
                "jsonrpc": "2.0",
                "id": "x",
                "result": {
                    "isError": False,
                    "content": [
                        {"type": "text", "text": '{"query":"x","results":[],"ai_summaries":[]}'}
                    ],
                },
            },
        )

        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=[init_resp, notif_resp, call_resp])
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch("app.bridge.httpx.AsyncClient", return_value=mock_ctx):
            first = client.get("/search", params={"q": "first"})
        assert first.status_code == 200

        # Second call should not even hit the MCP.
        with patch("app.bridge.httpx.AsyncClient") as cls:
            cls.assert_not_called()
            second = client.get("/search", params={"q": "second"})
        assert second.status_code == 429
        body = second.json()
        assert body["error"] == "cooldown"
        assert body["results"] == []
        assert "Retry-After" in second.headers

    def test_mcp_unreachable_returns_502(self, client: TestClient) -> None:
        """When httpx raises a connection error, /search returns HTTP 502."""

        async def _raise(*_args, **_kwargs):
            raise httpx.ConnectError("connection refused")

        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=_raise)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch("app.bridge.httpx.AsyncClient", return_value=mock_ctx):
            resp = client.get("/search", params={"q": "anything"})
        assert resp.status_code == 502
        body = resp.json()
        assert "mcp_unreachable" in body["error"]
        assert body["results"] == []

    def test_mcp_jsonrpc_error_returns_502(self, client: TestClient) -> None:
        """JSON-RPC ``error`` field in the response surfaces as HTTP 502."""
        init_resp = _make_response(200, headers={"mcp-session-id": "s1"})
        notif_resp = _make_response(202)
        call_resp = _make_response(
            200,
            json_body={
                "jsonrpc": "2.0",
                "id": "x",
                "error": {"code": -32601, "message": "tool not found"},
            },
        )

        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=[init_resp, notif_resp, call_resp])
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch("app.bridge.httpx.AsyncClient", return_value=mock_ctx):
            resp = client.get("/search", params={"q": "anything"})
        assert resp.status_code == 502
        assert "tool not found" in resp.json()["error"]

    def test_missing_session_id_returns_502(self, client: TestClient) -> None:
        """If the MCP initialize response has no session id, return 502."""
        init_resp = _make_response(200, headers={})  # no mcp-session-id

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=init_resp)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch("app.bridge.httpx.AsyncClient", return_value=mock_ctx):
            resp = client.get("/search", params={"q": "x"})
        assert resp.status_code == 502
        assert "missing Mcp-Session-Id" in resp.json()["error"]

    def test_iserror_flag_surfaces_as_502(self, client: TestClient) -> None:
        """MCP tool-level ``isError: true`` is reported as HTTP 502."""
        init_resp = _make_response(200, headers={"mcp-session-id": "s1"})
        notif_resp = _make_response(202)
        call_resp = _make_response(
            200,
            json_body={
                "jsonrpc": "2.0",
                "id": "x",
                "result": {
                    "isError": True,
                    "content": [
                        {"type": "text", "text": "No search engines configured."}
                    ],
                },
            },
        )

        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=[init_resp, notif_resp, call_resp])
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch("app.bridge.httpx.AsyncClient", return_value=mock_ctx):
            resp = client.get("/search", params={"q": "x"})
        assert resp.status_code == 502
        assert "No search engines" in resp.json()["error"]
