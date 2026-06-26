"""Shared agent-runtime helpers — proxy URL detection and model discovery.

These helpers were previously duplicated across the agent CLI modules
(``cli/mimo.py``, ``cli/opencode.py``, ``cli/codex.py``, ``cli/pi.py``).
They live in the ``core`` layer so the ``cli`` layer can import them
downward without introducing sideways dependencies.
"""

from __future__ import annotations

import json
import os
from typing import Any

from codefreedom.log import eprint

_DEFAULT_PROXY_URL = "http://localhost:4000"


def detect_proxy_url(base_env: dict[str, str]) -> str:
    """Detect the proxy URL from environment or fall back to the default.

    Checks (in order):
    1. ``PROXY_BASE_URL`` in the merged env
    2. ``PROXY_BASE_URL`` in ``os.environ``
    3. ``LITELLM_BASE_URL`` (legacy) in the merged env
    4. ``LITELLM_BASE_URL`` (legacy) in ``os.environ``
    5. Default ``http://localhost:4000``
    """
    return (
        base_env.get("PROXY_BASE_URL")
        or os.environ.get("PROXY_BASE_URL")
        or base_env.get("LITELLM_BASE_URL")
        or os.environ.get("LITELLM_BASE_URL")
        or _DEFAULT_PROXY_URL
    )


def fetch_proxy_models(
    proxy_url: str,
    api_key: str = "",
    *,
    label: str = "AGENT",
    secrets_hint: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch the model list from the LiteLLM proxy ``/v1/models`` endpoint.

    If *api_key* is provided it is sent as a ``Bearer`` token so the
    call succeeds even when the proxy requires authentication.

    Returns a list of model dicts (with at least an ``id`` key).
    Returns an empty list if the proxy is unreachable or returns an error.

    On 401/403 responses, prints a hint via ``eprint`` using *label*
    (e.g. ``MIMO``) and *secrets_hint* (a path such as
    ``~/.codefreedom/.env.mimo.secrets``) when provided.
    """
    from codefreedom.core.http_client import HTTPError, HTTPStatusError, get_json

    models_url = f"{proxy_url.rstrip('/')}/v1/models"
    try:
        data = get_json(models_url, timeout=5, bearer=api_key)
        return data.get("data", [])
    except HTTPStatusError as exc:
        if exc.status_code in (401, 403) and secrets_hint is not None:
            eprint(
                f"[{label}] Proxy returned {exc.status_code} — is LITELLM_MASTER_KEY set "
                f"in {secrets_hint}?"
            )
        return []
    except (HTTPError, json.JSONDecodeError):
        return []


def build_provider_models(
    proxy_models: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build a provider models dict from the proxy model list.

    Each model gets a minimal capability profile — just ``tool_call: True``
    and a display name.  Context limits and reasoning support are discovered
    by the agent at runtime; the proxy handles the actual routing.

    Skips internal LiteLLM models (``azure/``-prefixed) and known aliases
    (``gpt-3.5-turbo``, ``custom``).
    """
    provider_models: dict[str, dict[str, Any]] = {}

    for m in proxy_models:
        model_id = m.get("id", "")
        if not model_id:
            continue

        model_id_lower = model_id.lower()

        if model_id_lower.startswith("azure/") or model_id_lower in (
            "gpt-3.5-turbo",
            "custom",
        ):
            continue

        display_name = model_id.split("/")[-1] if "/" in model_id else model_id

        provider_models[model_id] = {
            "name": display_name,
            "tool_call": True,
        }

    return provider_models
