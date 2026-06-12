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
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._config_path = config_path or (
            "/app/litellm-config/plugins/image-router/image-router.yaml"
        )
        self._warned: set = set()
        self._in_vlm_call = False

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

    # ----------------------------------------------------------------- warn

    def _warn(self, tag: str, msg: str) -> None:
        if tag in self._warned:
            return
        self._warned.add(tag)
        print(f"[image-router] {msg}")

    # ----------------------------------------------------------- core logic

    def _is_enabled(self, data: Dict[str, Any]) -> bool:
        lp = data.get("litellm_params") or {}
        mi = lp.get("model_info") or {}
        cf = mi.get("codefreedom") or {}
        plugins = cf.get("plugins") or {}
        route_cfg = plugins.get("route-image-request")
        if isinstance(route_cfg, dict) and route_cfg.get("enabled") is True:
            return True
        return False

    async def _call_vlm(
        self, model: str, images: List[Dict[str, Any]]
    ) -> Optional[str]:
        """Call a VLM to transcribe images.  Returns text or None on failure."""
        user_content: List[Dict[str, Any]] = [
            {"type": "text", "text": _VLM_PROMPT}
        ]
        user_content.extend(images)

        self._in_vlm_call = True
        try:
            import litellm

            response = await litellm.acompletion(
                model=model,
                messages=[{"role": "user", "content": user_content}],
                stream=False,
            )
            if response and response.choices:
                content = response.choices[0].message.content
                if content:
                    return str(content)
        except Exception as exc:
            self._warn(
                f"vlm-error:{model}",
                f"VLM {model!r} failed: {type(exc).__name__}: {exc}",
            )
            return None
        finally:
            self._in_vlm_call = False

        return None

    # --------------------------------------------------------------- hook

    async def async_pre_call_hook(
        self,
        user_api_key_dict: Any,
        cache: Any,
        data: Dict[str, Any],
        call_type: str,
    ) -> Optional[Dict[str, Any]]:
        if self._in_vlm_call:
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

        model_name = data.get("model", "<unknown>")
        self._warn(
            f"routing:{model_name}",
            f"Rerouting {len(images)} image(s) from {model_name!r} "
            f"through VLM chain: {vlm_models}",
        )

        description = None
        for vlm in vlm_models:
            description = await self._call_vlm(vlm, images)
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
