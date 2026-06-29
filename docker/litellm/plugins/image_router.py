"""Image router plugin for LiteLLM (CodeFreedom).

Intercepts chat completion requests targeting text-only models, detects
image payloads in user messages, and re-routes them through a sequential
fallback chain of VLMs for image-to-text transcription before forwarding
clean text to the original model.

Configuration
-------------
The plugin reads a YAML config at
``/app/litellm-config/plugins/image-router/image-router.yaml``.

Per-model opt-in via the ``codefreedom.plugins.route-image-request``
block in the model entry (provider YAML):

  codefreedom:
    plugins:
      route-image-request:
        enabled: true

The VLM fallback chain is configured in the plugin's YAML:

  image-router-for-text-only:
    enabled: true
    models:
      - "OpenCode/MiMo-V2.5-FREE"
      - "OpenCode/Kimi-K2.6"
      - "OpenCode/Qwen3.7-Max"

If all VLMs fail, the original payload passes through unchanged.

Hooks used
----------
* ``async_pre_call_hook`` — called by the proxy before the LLM call.
  Modifies ``data["messages"]`` in place, removing image_url blocks
  and injecting the VLM's text description.
"""

from __future__ import annotations

import contextvars
import glob
import os
from typing import Any, Dict, List, Optional, Tuple

import yaml

try:
    from litellm.integrations.custom_logger import CustomLogger  # type: ignore[assignment]
except ImportError:  # pragma: no cover

    class CustomLogger:  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any) -> None:
            pass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VLM_PROMPT = (
    "Transcribe and describe all code, layout, and textual technical "
    "context from this image to match a software engineer's input."
)

_VLM_TIMEOUT_SECONDS = 60.0

# Per-request recursion guard.  Each asyncio task carries its own
# contextvars copy, so concurrent requests never interfere — unlike a
# plain boolean on the instance which is shared across all in-flight
# requests.
_vlm_call_active: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "image_router_vlm_call", default=False
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_images_and_text(
    messages: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str], List[int]]:
    """Scan *messages* for image_url blocks and text.

    Returns (images, text_strings, indices_of_messages_with_images).
    """
    images: List[Dict[str, Any]] = []
    text_parts: List[str] = []
    image_indices: List[int] = []

    for i, msg in enumerate(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, list):
            has_image = False
            for block in content:
                if isinstance(block, dict) and block.get("type") == "image_url":
                    images.append(block)
                    has_image = True
                elif isinstance(block, dict) and block.get("type") == "text":
                    t = block.get("text", "")
                    if t:
                        text_parts.append(t)
            if has_image:
                image_indices.append(i)
        elif isinstance(content, str):
            text_parts.append(content)

    return images, text_parts, image_indices


def _rewrite_messages(
    messages: List[Dict[str, Any]],
    description: str,
    original_text: List[str],
    image_indices: List[int],
) -> None:
    """Mutate *messages* in place: replace image payloads with VLM description.

    The VLM description is combined with the user's original text and
    placed in the first user message that contained an image.  Subsequent
    user messages that contained images are dropped (their visual content
    is now part of the combined description).  All other messages pass
    through unchanged.
    """
    if not image_indices:
        return

    combined = description
    if original_text:
        combined += "\n\n--- Original user prompt ---\n" + "\n".join(original_text)

    image_set = set(image_indices)

    result: List[Dict[str, Any]] = []
    replaced = False

    for i, msg in enumerate(messages):
        if i in image_set:
            if not replaced:
                result.append({"role": "user", "content": combined})
                replaced = True
            continue

        # Drop empty user messages that were between image messages (e.g.
        # a user message that had only image_url blocks and no text).
        if msg.get("role") == "user":
            c = msg.get("content")
            if isinstance(c, list) and len(c) == 0:
                continue

        result.append(msg)

    messages.clear()
    messages.extend(result)


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------


class ImageRouterLogger(CustomLogger):
    """Route image payloads through VLMs for text-only target models."""

    _config_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    def __init__(
        self,
        config_path: Optional[str] = None,
        proxy_config_dir: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._config_path = config_path or (
            "/app/litellm-config/plugins/image-router/image-router.yaml"
        )
        self._proxy_config_dir = proxy_config_dir or "/app/litellm-config/providers"
        self._model_codefreedom_cache: Dict[str, Dict[str, Any]] = {}
        self._codes_loaded = False
        self._warned: set = set()

    # ----------------------------------------------------------------- config

    def _load_config(self) -> Dict[str, Any]:
        path = self._config_path
        try:
            stat = os.stat(path)
        except OSError:
            return {}

        cached = self._config_cache.get(path)
        if cached is not None and cached[0] == stat.st_mtime:
            return cached[1]

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            raw = {}

        if not isinstance(raw, dict):
            raw = {}
        self._config_cache[path] = (stat.st_mtime, raw)
        return raw

    def _load_provider_codefreedom(self) -> Dict[str, Dict[str, Any]]:
        """Read all provider YAMLs and build model_name -> codefreedom cache.

        The ``codefreedom`` block sits at the top level of each model
        entry in the provider YAML (sibling of ``litellm_params`` and
        ``model_info``), so it is NOT reachable via the request-time
        ``data["litellm_params"]`` dict.  We read the files directly.
        """
        if self._codes_loaded:
            return self._model_codefreedom_cache
        self._codes_loaded = True
        if not os.path.isdir(self._proxy_config_dir):
            return self._model_codefreedom_cache
        for yp in glob.glob(os.path.join(self._proxy_config_dir, "*.yaml")):
            try:
                with open(yp, "r", encoding="utf-8") as f:
                    provider_data = yaml.safe_load(f) or {}
            except (OSError, yaml.YAMLError):
                continue
            if not isinstance(provider_data, dict):
                continue
            for entry in provider_data.get("model_list", []) or []:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("model_name")
                cf = entry.get("codefreedom")
                if isinstance(name, str) and isinstance(cf, dict):
                    self._model_codefreedom_cache[name] = cf
        return self._model_codefreedom_cache

    # ----------------------------------------------------------------- warn

    def _warn(self, tag: str, msg: str) -> None:
        if tag in self._warned:
            return
        self._warned.add(tag)
        print(f"[image-router] {msg}")

    # ----------------------------------------------------------- core logic

    def _is_enabled(self, data: Dict[str, Any]) -> bool:
        # Source 1: per-model plugin config from litellm_params.model_info
        lp = data.get("litellm_params") or {}
        mi = lp.get("model_info") or {}
        cf = mi.get("codefreedom") or {}
        plugins = cf.get("plugins") or {}
        route_cfg = plugins.get("route-image-request")
        if isinstance(route_cfg, dict) and route_cfg.get("enabled") is True:
            return True

        # Source 2: provider YAML files (codefreedom at model-entry level)
        model = data.get("model")
        if model:
            codes = self._load_provider_codefreedom()
            entry_cf = codes.get(model)
            if isinstance(entry_cf, dict):
                entry_plugins = entry_cf.get("plugins") or {}
                entry_route = entry_plugins.get("route-image-request")
                if isinstance(entry_route, dict) and entry_route.get("enabled") is True:
                    return True

        return False

    @staticmethod
    def _resolve_master_key() -> str:
        """Resolve the proxy master key from the container env chain.

        Checks ``LITELLM_MASTER_KEY`` (LiteLLM's convention) first, then
        ``PROXY_API_KEY`` (CodeFreedom's canonical name), then the
        ``CF_CLI_*`` overrides. Falls back to ``"sk-codefreedom-local"``
        (the container default) as a last resort so the VLM call always
        has a non-empty bearer token.  Never returns an empty string.
        """
        for name in (
            "LITELLM_MASTER_KEY",
            "PROXY_API_KEY",
            "CF_CLI_LITELLM_MASTER_KEY",
            "CF_CLI_PROXY_API_KEY",
        ):
            key = os.environ.get(name, "").strip()
            if key:
                return key
        return "sk-codefreedom-local"

    async def _call_vlm(
        self, model: str, images: List[Dict[str, Any]], master_key: str
    ) -> Optional[str]:
        """Call a single VLM via the proxy's own chat-completions endpoint.

        The proxy handles model resolution, auth, and routing — we just
        need to POST the image payload and read back the text description.

        Uses a ``contextvars.ContextVar`` (``_vlm_call_active``) to
        prevent recursion: when this async task is inside a VLM call the
        ``async_pre_call_hook`` skips image routing so the internal
        request passes straight through.

        *master_key* is resolved once by the caller and passed in to
        avoid repeated env lookups and to let the caller bail early when
        the key is missing.

        Checks both ``content`` and ``reasoning_content`` in the
        response — reasoning models (Qwen, etc.) often return
        ``content: null`` when thinking is enabled, with the actual text
        in ``reasoning_content``.
        """
        user_content: List[Dict[str, Any]] = [{"type": "text", "text": _VLM_PROMPT}]
        user_content.extend(images)

        port = os.environ.get("LITELLM_PORT", "4000")

        token = _vlm_call_active.set(True)
        try:
            import httpx

            async with httpx.AsyncClient(timeout=_VLM_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    f"http://127.0.0.1:{port}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {master_key}"},
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": user_content}],
                        "stream": False,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        msg = choices[0].get("message", {})
                        text = msg.get("content") or msg.get("reasoning_content")
                        if text:
                            return str(text)
                    return None
                else:
                    self._warn(
                        f"vlm-error:{model}",
                        f"VLM {model!r} returned HTTP {resp.status_code}: {resp.text[:200]}",
                    )
                    return None
        except Exception as exc:
            self._warn(
                f"vlm-error:{model}",
                f"VLM {model!r} failed: {type(exc).__name__}: {exc}",
            )
            return None
        finally:
            _vlm_call_active.reset(token)

    # --------------------------------------------------------------- hook

    async def async_pre_call_hook(
        self,
        user_api_key_dict: Any,
        cache: Any,
        data: Dict[str, Any],
        call_type: str,
    ) -> Optional[Dict[str, Any]]:
        # Per-request recursion guard: if this asyncio task is already
        # inside a VLM call, pass through without triggering another
        # round.  Uses contextvars so concurrent requests are isolated.
        if _vlm_call_active.get():
            return data

        if not self._is_enabled(data):
            return data

        messages = data.get("messages")
        if not isinstance(messages, list) or not messages:
            return data

        images, text_parts, image_indices = _extract_images_and_text(messages)
        if not images:
            return data

        config = self._load_config()
        global_cfg = config.get("image-router-for-text-only") or {}
        if not global_cfg.get("enabled"):
            return data

        vlm_models: List[str] = global_cfg.get("models") or []
        if not vlm_models:
            self._warn("no-vlm-models", "No VLM models configured; passing through")
            return data

        # Resolve master key once; bail early if completely unavailable
        # to avoid a flood of auth-failure requests.
        master_key = self._resolve_master_key()
        if not master_key:
            self._warn(
                "no-master-key",
                "LITELLM_MASTER_KEY/PROXY_API_KEY is not set; skipping VLM routing",
            )
            return data

        model_name = data.get("model", "<unknown>")
        self._warn(
            f"routing:{model_name}",
            f"Rerouting {len(images)} image(s) from {model_name!r} "
            f"through VLM chain: {vlm_models}",
        )

        description = None
        for vlm in vlm_models:
            description = await self._call_vlm(vlm, images, master_key)
            if description:
                break

        if not description:
            self._warn(
                "all-vlms-failed",
                "All VLMs failed; passing original payload through unchanged",
            )
            return data

        _rewrite_messages(messages, description, text_parts, image_indices)
        return data


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
instance = ImageRouterLogger()
