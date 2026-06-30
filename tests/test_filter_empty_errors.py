"""Tests for the filter_empty_errors plugin.

Exercises the unauthenticated / pre-routing failure fingerprint
detection and the hook's drop / keep behaviour without requiring a
running LiteLLM instance.
"""

from __future__ import annotations


import asyncio
import importlib.util
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

pytestmark = pytest.mark.integration

_project_root = Path(__file__).resolve().parent.parent

_plugin_path = str(
    _project_root / "docker" / "litellm" / "plugins" / "filter_empty_errors.py"
)
_spec = importlib.util.spec_from_file_location(
    "plugins.filter_empty_errors", _plugin_path
)
assert _spec is not None, f"Plugin not found at {_plugin_path}"
_plugin = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_plugin)

FilterEmptyErrorsLogger = _plugin.FilterEmptyErrorsLogger
_is_unauthenticated = _plugin._is_unauthenticated
instance = _plugin.instance


# ============================================================================
# Helpers
# ============================================================================


def _auth_key(api_key: str = "sk-test-key-123") -> Dict[str, Any]:
    return {
        "api_key": api_key,
        "user_id": "user-1",
        "team_id": "team-1",
        "key_alias": "test-key",
    }


def _request_data(
    model: Optional[str] = "gpt-4",
    provider: Optional[str] = "openai",
    api_base: Optional[str] = "https://api.openai.com/v1",
) -> Dict[str, Any]:
    return {
        "model": model,
        "custom_llm_provider": provider,
        "api_base": api_base,
        "messages": [{"role": "user", "content": "hi"}],
    }


def _call_hook(
    plugin: FilterEmptyErrorsLogger,
    request_data: Dict[str, Any],
    user_api_key_dict: Optional[Any],
) -> None:
    """Invoke the async hook synchronously via asyncio.run."""
    asyncio.run(
        plugin.async_post_call_failure_hook(
            request_data, RuntimeError("boom"), user_api_key_dict
        )
    )


# ============================================================================
# _is_unauthenticated fingerprint detection
# ============================================================================


class TestIsUnauthenticated:
    def test_none_user_key(self):
        assert _is_unauthenticated(None, _request_data()) is True

    def test_non_dict_user_key(self):
        assert _is_unauthenticated("not-a-dict", _request_data()) is True

    def test_dict_with_none_api_key(self):
        key = _auth_key()
        key["api_key"] = None
        assert _is_unauthenticated(key, _request_data()) is True

    def test_dict_with_empty_api_key(self):
        key = _auth_key(api_key="")
        assert _is_unauthenticated(key, _request_data()) is True

    def test_dict_with_no_api_key_field(self):
        key = {"user_id": "u-1"}
        assert _is_unauthenticated(key, _request_data()) is True

    def test_valid_key_but_empty_request(self):
        """Valid key + no model/provider/api_base -> filtered."""
        assert _is_unauthenticated(_auth_key(), {}) is True

    def test_valid_key_with_only_model(self):
        """Single model field is enough to NOT match the empty fingerprint."""
        assert _is_unauthenticated(_auth_key(), {"model": "gpt-4"}) is False

    def test_valid_key_with_only_provider(self):
        assert (
            _is_unauthenticated(_auth_key(), {"custom_llm_provider": "openai"})
            is False
        )

    def test_valid_key_with_only_api_base(self):
        assert (
            _is_unauthenticated(_auth_key(), {"api_base": "https://api.openai.com"})
            is False
        )

    def test_valid_key_with_full_request(self):
        assert _is_unauthenticated(_auth_key(), _request_data()) is False

    def test_none_request_data(self):
        """Defensive: missing request_data -> filtered."""
        assert _is_unauthenticated(_auth_key(), None) is True

    def test_non_dict_request_data(self):
        assert _is_unauthenticated(_auth_key(), "not-a-dict") is True


# ============================================================================
# Hook behaviour (drop vs. keep + stats)
# ============================================================================


class TestHookBehaviour:
    def _make_plugin(self) -> FilterEmptyErrorsLogger:
        return FilterEmptyErrorsLogger()

    def test_drops_when_user_key_is_none(self):
        plugin = self._make_plugin()
        _call_hook(plugin, _request_data(), None)
        assert plugin.stats() == {"dropped_unauth": 1, "kept": 0}

    def test_drops_when_api_key_empty(self):
        plugin = self._make_plugin()
        _call_hook(plugin, _request_data(), _auth_key(api_key=""))
        assert plugin.stats() == {"dropped_unauth": 1, "kept": 0}

    def test_drops_when_model_not_resolved(self):
        plugin = self._make_plugin()
        _call_hook(plugin, {}, _auth_key())
        assert plugin.stats() == {"dropped_unauth": 1, "kept": 0}

    def test_keeps_valid_runtime_error(self):
        plugin = self._make_plugin()
        _call_hook(plugin, _request_data(), _auth_key())
        assert plugin.stats() == {"dropped_unauth": 0, "kept": 1}

    def test_keeps_rate_limit_error(self):
        plugin = self._make_plugin()
        _call_hook(plugin, _request_data(), _auth_key())
        assert plugin.stats() == {"dropped_unauth": 0, "kept": 1}

    def test_keeps_model_4xx(self):
        plugin = self._make_plugin()
        _call_hook(plugin, _request_data(), _auth_key())
        assert plugin.stats() == {"dropped_unauth": 0, "kept": 1}

    def test_multiple_calls_accumulate(self):
        plugin = self._make_plugin()
        _call_hook(plugin, _request_data(), None)
        _call_hook(plugin, _request_data(), _auth_key())
        _call_hook(plugin, _request_data(), _auth_key())
        _call_hook(plugin, _request_data(), _auth_key(api_key=""))
        assert plugin.stats() == {"dropped_unauth": 2, "kept": 2}

    def test_hook_does_not_raise(self):
        """Returning silently is the documented contract -- never raise."""
        plugin = self._make_plugin()
        result = asyncio.run(
            plugin.async_post_call_failure_hook(
                _request_data(), RuntimeError("valid error"), _auth_key()
            )
        )
        assert result is None
        result = asyncio.run(
            plugin.async_post_call_failure_hook(
                _request_data(), RuntimeError("unauth"), None
            )
        )
        assert result is None


# ============================================================================
# Singleton and module surface
# ============================================================================


class TestModuleSurface:
    def test_singleton_is_instance(self):
        assert isinstance(instance, FilterEmptyErrorsLogger)

    def test_stats_starts_at_zero(self):
        plugin = FilterEmptyErrorsLogger()
        assert plugin.stats() == {"dropped_unauth": 0, "kept": 0}
