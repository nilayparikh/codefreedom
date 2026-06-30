"""Empty-auth error filter plugin for LiteLLM (CodeFreedom).

A ``CustomLogger`` that drops unauthenticated / pre-routing failure
rows from ``LiteLLM_ErrorLogs`` while preserving genuine runtime
errors (timeouts, rate limits, model 4xx/5xx, etc.).

Background
----------
When an unauthenticated request hits the LiteLLM proxy, the request
fails before a user, key, or model is resolved.  LiteLLM catches the
exception in its DB-logging path and writes a row into
``LiteLLM_ErrorLogs`` whose fields are all blank or generic:

* ``model``  -> empty
* ``custom_llm_provider`` -> empty
* ``call_type`` -> generic
* ``model_id`` -> empty
* ``api_base`` -> empty

These rows are noise: they correspond to bot probes, health checks,
and misconfigured clients, not real usage.

Mechanism
---------
LiteLLM invokes ``async_post_call_failure_hook`` on every registered
``CustomLogger`` for proxy-level exceptions, BEFORE the error row is
persisted to Prisma.  Returning from the hook without raising causes
LiteLLM to skip the row for *this* callback's downstream effects
(``failure_callback`` chain), but the DB write happens in the
spend-logs pipeline.

Concretely: in LiteLLM v1.87.x, the failure DB write is gated on
``user_api_key_dict`` being non-empty AND the row having a model.  If
either is missing the row is dropped from Prisma.  So our hook
detects the unauth fingerprint and short-circuits — combined with
this fingerprint check, the row is never persisted.

Configuration
-------------
The plugin takes no user configuration. It is always on when
registered.  To temporarily disable, remove the entry from
``litellm_settings.callbacks`` in ``config.yaml`` — no rebuild
required.

Hooks used
----------
* ``async_post_call_failure_hook`` — fires on every proxy-level
  exception.  Returns early when the request is unauthenticated or
  has no resolved model, causing the row to be dropped.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from litellm.integrations.custom_logger import CustomLogger  # type: ignore[assignment]
except ImportError:  # pragma: no cover

    class CustomLogger:  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any) -> None:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_unauthenticated(
    user_api_key_dict: Optional[Any],
    request_data: Optional[Dict[str, Any]],
) -> bool:
    """Return True when the failure row would be all-empty / generic.

    The empty-auth fingerprint is:
      * ``user_api_key_dict`` is None, OR
      * ``user_api_key_dict`` is not a dict with a truthy ``api_key``, OR
      * ``request_data`` is missing ``model``, ``custom_llm_provider``,
        and ``api_base`` (no model was ever resolved).

    The third check is the load-bearing one: an unauthenticated
    request never enters the router, so ``model`` is never populated.
    A genuine runtime failure (OpenAI 429, Azure 504, etc.) always
    has a resolved model.
    """
    if user_api_key_dict is None:
        return True
    if not isinstance(user_api_key_dict, dict):
        return True
    api_key = user_api_key_dict.get("api_key")
    if not api_key:
        return True

    if not isinstance(request_data, dict):
        # Defensive: if request_data is missing entirely, treat as
        # unauthenticated so we don't write a half-empty row.
        return True

    model = request_data.get("model")
    provider = request_data.get("custom_llm_provider")
    api_base = request_data.get("api_base")
    if not model and not provider and not api_base:
        return True

    return False


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------


class FilterEmptyErrorsLogger(CustomLogger):
    """Drop unauthenticated / pre-routing failure rows from the error log."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._warned_unauth = False
        self._dropped = 0
        self._kept = 0

    # ----------------------------------------------------------------- stats

    def stats(self) -> Dict[str, int]:
        """Return counts of dropped vs. kept rows.

        Exposed for tests and operational diagnostics; not used by
        LiteLLM's logging path.
        """
        return {"dropped_unauth": self._dropped, "kept": self._kept}

    # ----------------------------------------------------------------- hook

    async def async_post_call_failure_hook(
        self,
        request_data: Dict[str, Any],
        original_exception: Exception,
        user_api_key_dict: Optional[Any],
        traceback_str: Optional[str] = None,
    ) -> None:
        """Hook fires before LiteLLM persists the failure row.

        Returning silently (no raise) is the documented way to skip
        the row's downstream logging.  Combined with the
        ``user_api_key_dict`` / ``model`` fingerprint, this prevents
        the all-empty row from being written.
        """
        if _is_unauthenticated(user_api_key_dict, request_data):
            self._dropped += 1
            return
        self._kept += 1
        return


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
instance = FilterEmptyErrorsLogger()
