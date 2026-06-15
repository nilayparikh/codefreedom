"""Tests for the image_router plugin.

Exercises recursion guard (contextvars), master-key resolution,
VLM fallback chain, and message rewriting without requiring a running
LiteLLM instance.
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

pytestmark = pytest.mark.integration

_project_root = Path(__file__).resolve().parent.parent

_plugin_path = str(
    _project_root / "docker" / "litellm" / "plugins" / "image_router.py"
)
_spec = importlib.util.spec_from_file_location(
    "plugins.image_router", _plugin_path
)
assert _spec is not None, f"Plugin not found at {_plugin_path}"
_plugin = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_plugin)

ImageRouterLogger = _plugin.ImageRouterLogger
_extract_images_and_text = _plugin._extract_images_and_text
_rewrite_messages = _plugin._rewrite_messages
_vlm_call_active = _plugin._vlm_call_active


# ============================================================================
# Helpers
# ============================================================================

def _make_data(
    model: str = "text-model",
    messages: Optional[List[Dict[str, Any]]] = None,
    enabled: bool = True,
) -> Dict[str, Any]:
    """Build a minimal ``data`` dict matching LiteLLM's pre-call shape."""
    if messages is None:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe this"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                ],
            }
        ]
    data: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "litellm_params": {
            "model_info": {
                "codefreedom": {
                    "plugins": {
                        "route-image-request": {"enabled": enabled},
                    },
                },
            },
        },
    }
    return data


def _make_plugin(
    config: Optional[Dict[str, Any]] = None,
) -> ImageRouterLogger:
    """Create a plugin instance with a synthetic config."""
    import tempfile

    if config is None:
        config = {
            "image-router-for-text-only": {
                "enabled": True,
                "models": ["VLM-A", "VLM-B"],
            },
        }

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    yaml.dump(config, tmp)
    tmp.close()

    p = ImageRouterLogger(config_path=tmp.name, proxy_config_dir="/nonexistent")
    return p


# ============================================================================
# _extract_images_and_text
# ============================================================================


class TestExtractImagesAndText:
    def test_no_messages(self):
        images, text, indices = _extract_images_and_text([])
        assert images == []
        assert text == []
        assert indices == []

    def test_text_only(self):
        msgs = [{"role": "user", "content": "hello"}]
        images, text, indices = _extract_images_and_text(msgs)
        assert images == []
        assert text == ["hello"]
        assert indices == []

    def test_image_only(self):
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": "data:..."}},
                ],
            }
        ]
        images, text, indices = _extract_images_and_text(msgs)
        assert len(images) == 1
        assert text == []
        assert indices == [0]

    def test_mixed_content(self):
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "look at this"},
                    {"type": "image_url", "image_url": {"url": "data:..."}},
                ],
            }
        ]
        images, text, indices = _extract_images_and_text(msgs)
        assert len(images) == 1
        assert text == ["look at this"]
        assert indices == [0]

    def test_skips_non_user_messages(self):
        msgs = [
            {"role": "system", "content": "you are helpful"},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": "data:..."}},
                ],
            },
        ]
        images, text, indices = _extract_images_and_text(msgs)
        assert len(images) == 1
        assert text == []
        assert indices == [1]


# ============================================================================
# _rewrite_messages
# ============================================================================


class TestRewriteMessages:
    def test_no_images_noop(self):
        msgs = [{"role": "user", "content": "hello"}]
        original = list(msgs)
        _rewrite_messages(msgs, "desc", ["hello"], [])
        assert msgs == original

    def test_single_image_replaced(self):
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "what is this"},
                    {"type": "image_url", "image_url": {"url": "data:..."}},
                ],
            }
        ]
        _rewrite_messages(msgs, "a cat", ["what is this"], [0])
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert "a cat" in msgs[0]["content"]
        assert "what is this" in msgs[0]["content"]

    def test_multiple_image_messages_merged(self):
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": "data:1"}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "second"},
                    {"type": "image_url", "image_url": {"url": "data:2"}},
                ],
            },
        ]
        _rewrite_messages(msgs, "description", ["second"], [0, 1])
        assert len(msgs) == 1
        assert "description" in msgs[0]["content"]


# ============================================================================
# _resolve_master_key
# ============================================================================


class TestResolveMasterKey:
    def test_from_litellm_master_key(self, monkeypatch):
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test-key")
        monkeypatch.delenv("CF_CLI_LITELLM_MASTER_KEY", raising=False)
        assert ImageRouterLogger._resolve_master_key() == "sk-test-key"

    def test_from_cf_cli_override(self, monkeypatch):
        monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
        monkeypatch.setenv("CF_CLI_LITELLM_MASTER_KEY", "sk-cf-cli")
        assert ImageRouterLogger._resolve_master_key() == "sk-cf-cli"

    def test_cf_cli_wins_over_direct(self, monkeypatch):
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-direct")
        monkeypatch.setenv("CF_CLI_LITELLM_MASTER_KEY", "sk-cf-cli")
        assert ImageRouterLogger._resolve_master_key() == "sk-direct"

    def test_empty_key_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("LITELLM_MASTER_KEY", "")
        monkeypatch.delenv("CF_CLI_LITELLM_MASTER_KEY", raising=False)
        assert ImageRouterLogger._resolve_master_key() == "sk-codefreedom-local"

    def test_whitespace_only_key_falls_back(self, monkeypatch):
        monkeypatch.setenv("LITELLM_MASTER_KEY", "   ")
        monkeypatch.delenv("CF_CLI_LITELLM_MASTER_KEY", raising=False)
        assert ImageRouterLogger._resolve_master_key() == "sk-codefreedom-local"

    def test_never_returns_empty(self, monkeypatch):
        monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
        monkeypatch.delenv("CF_CLI_LITELLM_MASTER_KEY", raising=False)
        result = ImageRouterLogger._resolve_master_key()
        assert result
        assert result.strip()


# ============================================================================
# Context-var recursion guard
# ============================================================================


class TestContextVarGuard:
    def test_default_is_false(self):
        assert _vlm_call_active.get() is False

    def test_set_and_reset(self):
        token = _vlm_call_active.set(True)
        assert _vlm_call_active.get() is True
        _vlm_call_active.reset(token)
        assert _vlm_call_active.get() is False

    def test_concurrent_tasks_isolated(self):
        """Two asyncio tasks should not see each other's context var."""

        async def task_a():
            token = _vlm_call_active.set(True)
            await asyncio.sleep(0.01)
            assert _vlm_call_active.get() is True
            _vlm_call_active.reset(token)

        async def task_b():
            assert _vlm_call_active.get() is False
            await asyncio.sleep(0.01)
            assert _vlm_call_active.get() is False

        async def run_both():
            await asyncio.gather(task_a(), task_b())

        asyncio.run(run_both())


# ============================================================================
# async_pre_call_hook
# ============================================================================


class TestPreCallHook:
    def test_skips_when_vlm_call_active(self):
        plugin = _make_plugin()
        data = _make_data()
        token = _vlm_call_active.set(True)
        try:
            result = asyncio.run(
                plugin.async_pre_call_hook(None, None, data, "chat")
            )
            assert result is data
        finally:
            _vlm_call_active.reset(token)

    def test_passes_through_when_not_enabled(self):
        plugin = _make_plugin()
        data = _make_data(enabled=False)
        result = asyncio.run(
            plugin.async_pre_call_hook(None, None, data, "chat")
        )
        assert result is data

    def test_passes_through_when_no_images(self):
        plugin = _make_plugin()
        data = _make_data(messages=[{"role": "user", "content": "hello"}])
        result = asyncio.run(
            plugin.async_pre_call_hook(None, None, data, "chat")
        )
        assert result is data

    def test_passes_through_when_config_disabled(self):
        plugin = _make_plugin(
            config={"image-router-for-text-only": {"enabled": False}}
        )
        data = _make_data()
        result = asyncio.run(
            plugin.async_pre_call_hook(None, None, data, "chat")
        )
        assert result is data

    def test_passes_through_when_no_vlm_models(self):
        plugin = _make_plugin(
            config={"image-router-for-text-only": {"enabled": True, "models": []}}
        )
        data = _make_data()
        result = asyncio.run(
            plugin.async_pre_call_hook(None, None, data, "chat")
        )
        assert result is data

    def test_vlm_success_rewrites_messages(self):
        plugin = _make_plugin()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "a screenshot of code"}}],
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        data = _make_data()

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(
                plugin.async_pre_call_hook(None, None, data, "chat")
            )

        assert result is data
        assert "a screenshot of code" in data["messages"][0]["content"]
        assert mock_client.post.call_count == 1

    def test_first_vlm_fails_falls_back_to_second(self):
        plugin = _make_plugin()

        fail_response = MagicMock()
        fail_response.status_code = 500
        fail_response.text = "Internal Server Error"

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "choices": [{"message": {"content": "fallback result"}}],
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[fail_response, success_response])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        data = _make_data()

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(
                plugin.async_pre_call_hook(None, None, data, "chat")
            )

        assert result is data
        assert "fallback result" in data["messages"][0]["content"]
        assert mock_client.post.call_count == 2

    def test_all_vlms_fail_passes_through(self):
        plugin = _make_plugin()

        fail_response = MagicMock()
        fail_response.status_code = 500
        fail_response.text = "error"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=fail_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        data = _make_data()
        original_messages = [m.copy() for m in data["messages"]]

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(
                plugin.async_pre_call_hook(None, None, data, "chat")
            )

        assert result is data
        assert data["messages"] == original_messages
        assert mock_client.post.call_count == 2

    def test_http_exception_falls_back(self):
        plugin = _make_plugin()

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "choices": [{"message": {"content": "recovered"}}],
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=[Exception("connection refused"), success_response]
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        data = _make_data()

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(
                plugin.async_pre_call_hook(None, None, data, "chat")
            )

        assert result is data
        assert "recovered" in data["messages"][0]["content"]
        assert mock_client.post.call_count == 2

    def test_reasoning_content_fallback(self):
        """Models with thinking return content=null, text in reasoning_content."""
        plugin = _make_plugin()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": None, "reasoning_content": "the description"}},
            ],
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        data = _make_data()

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(
                plugin.async_pre_call_hook(None, None, data, "chat")
            )

        assert result is data
        assert "the description" in data["messages"][0]["content"]

    def test_empty_choices_returns_none(self):
        plugin = _make_plugin()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": []}

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "choices": [{"message": {"content": "from second VLM"}}],
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[mock_response, success_response])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        data = _make_data()

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(
                plugin.async_pre_call_hook(None, None, data, "chat")
            )

        assert result is data
        assert "from second VLM" in data["messages"][0]["content"]
        assert mock_client.post.call_count == 2
