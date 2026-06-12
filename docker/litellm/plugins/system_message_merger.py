"""System message merger plugin for LiteLLM (CodeFreedom).

Merges multiple ``system`` role messages into a single system message
before forwarding requests to the backend.  This fixes Jinja chat
template errors (e.g. "System message must be at the beginning") on
models that enforce a single leading system message.

Configuration
-------------
The plugin reads a YAML config at
``/app/litellm-config/plugins/system-message-merger/system-message-merger.yaml``.

Per-model opt-in via the ``codefreedom.plugins.system-message-merger``
block in the model entry (``local.yaml`` or equivalent):

  codefreedom:
    plugins:
      system-message-merger:
        enabled: true

If a model has no ``system-message-merger`` block, the plugin is
inactive for that model (pass-through).  This ensures only the models
that need merging are affected.

Hooks used
----------
* ``async_pre_call_hook`` — called by the proxy before the LLM call
  for /chat/completions, /embeddings, /image/generation.
"""

from __future__ import annotations

import glob
import os
from typing import Any, Dict, List, Optional, Union

import yaml

try:
    from litellm.integrations.custom_logger import CustomLogger
except ImportError:

    class CustomLogger:  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any) -> None:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _merge_system_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge consecutive system messages into a single system message.

    If there are 0 or 1 system messages, the list is returned unchanged.
    If there are 2+ system messages, their content is joined with
    ``\\n\\n`` separators and replaced with a single system message at the
    original position of the first system message.
    """
    system_indices = [i for i, m in enumerate(messages) if m.get("role") == "system"]
    if len(system_indices) <= 1:
        return messages

    contents = []
    for idx in system_indices:
        c = messages[idx].get("content")
        if isinstance(c, str):
            contents.append(c)
        elif isinstance(c, list):
            parts = []
            for block in c:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    parts.append(block)
            if parts:
                contents.append("\n\n".join(parts))

    merged_content = "\n\n".join(contents)

    result = []
    merged_inserted = False
    skip_until = -1

    for i, msg in enumerate(messages):
        if i <= skip_until:
            continue

        if msg.get("role") == "system" and not merged_inserted:
            result.append({"role": "system", "content": merged_content})
            merged_inserted = True
            if len(system_indices) > 1:
                skip_until = system_indices[-1]
            continue

        if msg.get("role") == "system" and merged_inserted:
            continue

        result.append(msg)

    return result


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------


class SystemMessageMergerLogger(CustomLogger):
    """Merge multiple system messages into one for models that require it."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        config_path: Optional[str] = None,
        proxy_config_dir: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        if hasattr(self, "_initialized"):
            return
        super().__init__(**kwargs)
        self._config_path = config_path or (
            "/app/litellm-config/plugins/system-message-merger/"
            "system-message-merger.yaml"
        )
        self._proxy_config_dir = proxy_config_dir or "/app/litellm-config/providers"
        self._enabled_models: Optional[set] = None
        self._model_codefreedom_cache: Dict[str, Dict[str, Any]] = {}
        self._codes_loaded = False
        self._warned: set = set()
        self._initialized = True

    # --------------------------------------------------------- config

    def _load_enabled_models(self) -> set:
        if self._enabled_models is not None:
            return self._enabled_models

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            data = {}

        models = set()
        for entry in data.get("models", []) or []:
            if isinstance(entry, str):
                models.add(entry.lower())
            elif isinstance(entry, dict):
                name = entry.get("name")
                if isinstance(name, str):
                    models.add(name.lower())

        self._enabled_models = models
        return models

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

    def _is_enabled(self, model: Optional[str], data: Dict[str, Any]) -> bool:
        # Source 1: per-model plugin config from litellm_params.model_info
        lp = data.get("litellm_params") or {}
        mi = lp.get("model_info") or {}
        cf = mi.get("codefreedom") or {}
        plugins = cf.get("plugins") or {}
        merger_cfg = plugins.get("system-message-merger")
        if isinstance(merger_cfg, dict):
            if merger_cfg.get("enabled") is True:
                return True
            if merger_cfg.get("enabled") is False:
                return False

        # Source 2: provider YAML files (codefreedom at model-entry level)
        if model:
            codes = self._load_provider_codefreedom()
            entry_cf = codes.get(model)
            if isinstance(entry_cf, dict):
                entry_plugins = entry_cf.get("plugins") or {}
                entry_merger = entry_plugins.get("system-message-merger")
                if isinstance(entry_merger, dict):
                    if entry_merger.get("enabled") is True:
                        return True
                    if entry_merger.get("enabled") is False:
                        return False

        # Source 3: YAML config file
        enabled = self._load_enabled_models()
        if enabled and model and model.lower() in enabled:
            return True

        return False

    # --------------------------------------------------------- core

    def _process(self, data: Dict[str, Any]) -> None:
        messages = data.get("messages")
        if not isinstance(messages, list):
            return

        model = data.get("model")
        if not self._is_enabled(model, data):
            return

        system_count = sum(1 for m in messages if m.get("role") == "system")
        if system_count <= 1:
            return

        merged = _merge_system_messages(messages)
        messages.clear()
        messages.extend(merged)

        tag = f"merged:{model}"
        if tag not in self._warned:
            self._warned.add(tag)
            print(
                f"[system-message-merger] Merged {system_count} system messages "
                f"for model {model!r}"
            )

    # --------------------------------------------------------------- hook

    async def async_pre_call_hook(
        self,
        user_api_key_dict: Any,
        cache: Any,
        data: Dict[str, Any],
        call_type: str,
    ) -> Optional[Dict[str, Any]]:
        self._process(data)
        return data


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
instance = SystemMessageMergerLogger()
