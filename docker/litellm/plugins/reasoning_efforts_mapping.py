"""Reasoning-efforts mapping plugin for LiteLLM (CodeFreedom) — v2.

A CustomLogger that translates reasoning-effort signals across provider
standards using a rule-based mapping. The plugin reads its configuration
from a YAML file on disk and resolves the rule per model based on the
``codefreedom.plugins.reasoning-efforts`` block in the model entry.

Two rule types:

  ``mapping`` — maps reasoning-level strings from upstream apps
  (Claude Code, Cursor, etc.) to values the downstream model accepts.
  The ``values`` dict is a direct incoming→outgoing map.  No
  interpolation, no clamping, no guess.  If a value is missing from
  ``values`` the field is dropped for that request (warn-once).

  ``thinking_budget`` — maps reasoning-level strings to a numeric
  thinking-token budget.  The ``field`` is a dotted path
  (e.g. ``extra_body.max_thinking_tokens``) that determines where in
  the request the value gets set.  Applied on EVERY request.

A model may be associated with exactly ONE rule (by name or inline).
If a model has no rule the plugin does a pure field rename
(``output_config.effort`` ↔ ``reasoning_effort``) — the ``auto``
default.

Configuration
-------------
The plugin reads a YAML config at
``/app/litellm-config/plugins/reasoning-efforts/reasoning-efforts-mapping.yaml``.
The Python module is baked into the Docker image; the YAML is
user-editable on the host at
``~/.codefreedom/proxy/config/plugins/reasoning-efforts/reasoning-efforts-mapping.yaml``.

Hooks used
----------
* ``async_pre_request_hook`` — Anthropic /v1/messages path.
* ``async_log_pre_api_call`` — OpenAI /v1/chat/completions path.

The translation is idempotent: if the incoming request already
matches the target provider's native syntax we leave it alone.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml

try:
    from litellm.integrations.custom_logger import CustomLogger  # type: ignore[assignment]
except ImportError:  # pragma: no cover

    class CustomLogger:  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any) -> None:
            pass


# ---------------------------------------------------------------------------
# Per-provider output fields (used by the ``auto`` default)
# ---------------------------------------------------------------------------
_AUTO_OUTPUT: Dict[str, str] = {
    "anthropic": "output_config",
    "bedrock": "output_config",
    "vertex_ai": "output_config",
    "azure-anthropic": "output_config",
    # everything else → reasoning_effort
}

_KNOWN_PROVIDERS = frozenset(
    {
        "openai",
        "azure",
        "anthropic",
        "bedrock",
        "vertex_ai",
        "deepseek",
        "groq",
        "cohere",
        "huggingface",
        "nvidia",
        "openrouter",
        "opencode-zen",
        "minimax",
        "xai",
        "mistral",
        "perplexity",
        "together_ai",
        "fireworks_ai",
        "anyscale",
        "azure-anthropic",
        "oci",
    }
)

# Prefixes that resolve to a canonical provider name (used when the
# model has a non-standard prefix, e.g. "OCZ/MNP/..." → opencode-zen).
_PREFIX_ALIASES: Dict[str, str] = {
    "ocz": "opencode-zen",
}


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------
class ReasoningEffortsMappingLogger(CustomLogger):
    """Normalise reasoning effort across providers via rule-based mapping."""

    _config_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    def __init__(
        self,
        config_path: Optional[str] = None,
        proxy_config_dir: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._config_path = config_path or (
            "/app/litellm-config/plugins/reasoning-efforts/"
            "reasoning-efforts-mapping.yaml"
        )
        self._proxy_config_dir = proxy_config_dir or "/app/litellm-config/providers"
        self._warned: set = set()
        self._model_info_cache: Dict[str, Dict[str, Any]] = {}
        self._loaded_cache = False

    # ----------------------------------------------------------------- config

    def _load_config(self) -> Dict[str, Any]:
        """Load (and cache) the YAML config.  Returns {} on any error."""
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
        except (OSError, yaml.YAMLError) as exc:
            print(f"[reasoning-efforts] WARN: cannot parse {path}: {exc!r}")
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        self._config_cache[path] = (stat.st_mtime, raw)
        return raw

    def _load_proxy_model_infos(self) -> None:
        """Build model_name→model_info cache (Anthropic-path fallback)."""
        if self._loaded_cache:
            return
        self._loaded_cache = True
        if not os.path.isdir(self._proxy_config_dir):
            return
        for yp in glob.glob(os.path.join(self._proxy_config_dir, "*.yaml")):
            try:
                with open(yp, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            except (OSError, yaml.YAMLError):
                continue
            if not isinstance(data, dict):
                continue
            for entry in data.get("model_list", []) or []:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("model_name")
                if isinstance(name, str):
                    self._model_info_cache[name] = entry.get("model_info") or {}

    # --------------------------------------------------------- rule resolve

    def _get_model_info(
        self, model: Optional[str], lp: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Resolve model_info from kwargs (OpenAI path) or cache."""
        if lp and isinstance(lp.get("model_info"), dict):
            return lp["model_info"]
        if model is None:
            return {}
        self._load_proxy_model_infos()
        return self._model_info_cache.get(model, {})

    def _resolve_rule(
        self, mi: Dict[str, Any]
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str], str]:
        """Resolve the rule for this model.

        Returns (rule_dict, rule_name, source).
        *source*: inline_mapping | inline_thinking_budget | named | auto.
        """
        plugins = (mi.get("codefreedom") or {}).get("plugins") or {}
        if not isinstance(plugins, dict):
            return None, None, "auto"

        re_cfg = plugins.get("reasoning-efforts")
        if not isinstance(re_cfg, dict):
            return None, None, "auto"

        # Inline mapping
        if (
            "values" in re_cfg
            and "output" in re_cfg
            and "field" not in re_cfg
            and re_cfg.get("type") in (None, "mapping")
        ):
            return re_cfg, None, "inline_mapping"

        # Inline thinking_budget
        if (
            "field" in re_cfg
            and "values" in re_cfg
            and "output" not in re_cfg
            and re_cfg.get("type") in (None, "thinking_budget")
        ):
            return re_cfg, None, "inline_thinking_budget"

        # Named rule
        rule_name = re_cfg.get("rule")
        if isinstance(rule_name, str):
            config = self._load_config()
            rules = config.get("rules") or {}
            if rule_name in rules:
                return rules[rule_name], rule_name, "named"
            self._warn_once("missing-rule", f"rule {rule_name!r} not found; using auto")

        return None, None, "auto"

    # ---------------------------------------------------------------- warn

    def _warn_once(self, tag: str, msg: str) -> None:
        """Log *msg* at most once per *tag*."""
        if tag in self._warned:
            return
        self._warned.add(tag)
        print(f"[reasoning-efforts] WARNING: {msg}")

    def _warn_missing_value(self, rule_name: Optional[str], key: str) -> None:
        tag = f"missing:{rule_name or '<inline>'}:{key}"
        desc = repr(rule_name) if rule_name else "<inline>"
        self._warn_once(
            tag,
            f"rule {desc} has no value for key {key!r}; dropping field",
        )

    # -------------------------------------------------------- transformation

    @staticmethod
    def _get_incoming(
        kwargs: Dict[str, Any],
    ) -> Tuple[Optional[str], Optional[str]]:
        """Return (lowered_value, source_field) or (None, None)."""
        oc = kwargs.get("output_config")
        if isinstance(oc, dict) and "effort" in oc:
            v = oc.get("effort")
            if isinstance(v, str):
                return v.strip().lower(), "output_config"
        if "reasoning_effort" in kwargs:
            v = kwargs.get("reasoning_effort")
            if isinstance(v, str):
                return v.strip().lower(), "reasoning_effort"
        return None, None

    @staticmethod
    def _set_nested(d: Dict[str, Any], path: str, value: Any) -> None:
        """Set d[part1][part2]...[last] = value (creates dicts as needed)."""
        parts = path.split(".")
        cursor = d
        for p in parts[:-1]:
            if p not in cursor or not isinstance(cursor[p], dict):
                cursor[p] = {}
            cursor = cursor[p]
        cursor[parts[-1]] = value

    def _apply_mapping(
        self,
        out: Dict[str, Any],
        rule: Dict[str, Any],
        rule_name: Optional[str],
        raw_value: str,
    ) -> None:
        """Mutate *out* with the mapping result."""
        output = rule.get("output") or "reasoning_effort"
        values = rule.get("values")
        if not isinstance(values, dict):
            return
        key = raw_value.lower()
        if key not in values:
            self._warn_missing_value(rule_name, key)
            # Drop the source field regardless of whether source == target —
            # the value isn't supported.
            out.pop("output_config", None)
            out.pop("reasoning_effort", None)
            return
        target = values[key]
        if output == "output_config":
            oc = out.get("output_config")
            if not isinstance(oc, dict):
                oc = {}
            oc["effort"] = target
            out["output_config"] = oc
            out.pop("reasoning_effort", None)
        else:
            out["reasoning_effort"] = target
            out.pop("output_config", None)

    def _apply_thinking_budget(
        self,
        out: Dict[str, Any],
        rule: Dict[str, Any],
        rule_name: Optional[str],
        raw_value: str,
    ) -> None:
        """Mutate *out* with the thinking_budget result."""
        field = rule.get("field")
        values = rule.get("values")
        if not isinstance(field, str) or not isinstance(values, dict):
            return
        key = raw_value.lower()
        if key not in values:
            self._warn_missing_value(rule_name, key)
            return
        self._set_nested(out, field, values[key])

    def _apply_auto(
        self,
        out: Dict[str, Any],
        raw_value: str,
        source_field: Optional[str],
        provider: Optional[str],
        model: Optional[str],
    ) -> None:
        """Pure field rename, no value remap."""
        if not source_field:
            return
        target = _AUTO_OUTPUT.get(provider or "", "reasoning_effort")
        if model and provider is None:
            lo = model.lower()
            if "claude" in lo or "anthropic" in lo:
                target = "output_config"
        if source_field == target:
            return
        if target == "output_config":
            oc = out.get("output_config")
            if not isinstance(oc, dict):
                oc = {}
            oc["effort"] = raw_value
            out["output_config"] = oc
            out.pop("reasoning_effort", None)
        else:
            out["reasoning_effort"] = raw_value
            out.pop("output_config", None)

    # ----------------------------------------------------------- core entry

    def _translate(
        self,
        kwargs: Dict[str, Any],
        model: Optional[str],
        custom_provider: Optional[str],
    ) -> Dict[str, Any]:
        """Return a new kwargs dict with the effort translated."""
        out = dict(kwargs)
        raw_value, source_field = self._get_incoming(out)
        if raw_value is None:
            return out

        lp = out.get("litellm_params") or {}
        mi = self._get_model_info(model, lp)
        rule, rule_name, source = self._resolve_rule(mi)

        if source in ("inline_mapping", "named"):
            resolved_rule: Dict[str, Any] = rule if rule is not None else {}
            rtype = resolved_rule.get("type", "mapping")
            if rtype == "mapping":
                self._apply_mapping(out, resolved_rule, rule_name, raw_value)
            elif rtype == "thinking_budget":
                self._apply_thinking_budget(out, resolved_rule, rule_name, raw_value)
            else:
                provider = custom_provider or self._infer_provider(model)
                self._apply_auto(out, raw_value, source_field, provider, model)
        elif source == "inline_thinking_budget":
            resolved_rule_budget: Dict[str, Any] = rule if rule is not None else {}
            self._apply_thinking_budget(out, resolved_rule_budget, rule_name, raw_value)
        else:
            provider = custom_provider or self._infer_provider(model)
            self._apply_auto(out, raw_value, source_field, provider, model)

        return out

    @staticmethod
    def _infer_provider(model: Optional[str]) -> Optional[str]:
        if not model:
            return None
        lo = model.lower()
        s = lo.find("/")
        if s != -1:
            pfx = lo[:s]
            if pfx in _KNOWN_PROVIDERS:
                return pfx
            if pfx in _PREFIX_ALIASES:
                return _PREFIX_ALIASES[pfx]
        if "deepseek" in lo:
            return "deepseek"
        if "claude" in lo or "anthropic" in lo:
            return "anthropic"
        return None

    # --------------------------------------------------------------- hooks

    async def async_pre_request_hook(
        self, model: str, _messages: list, kwargs: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        provider = (kwargs.get("litellm_params") or {}).get("custom_llm_provider")
        return self._translate(kwargs, model=model, custom_provider=provider)

    async def async_log_pre_api_call(
        self, model: str, _messages: list, kwargs: Dict[str, Any]
    ) -> None:
        provider = (kwargs.get("litellm_params") or {}).get("custom_llm_provider")
        translated = self._translate(kwargs, model=model, custom_provider=provider)
        for k in list(kwargs.keys()):
            if k not in translated:
                kwargs.pop(k, None)
        for k, v in translated.items():
            kwargs[k] = v


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
instance = ReasoningEffortsMappingLogger()


# ---------------------------------------------------------------------------
# Helper for tests
# ---------------------------------------------------------------------------
def normalise(effort: Any) -> Optional[str]:
    """Pass-through (lowercase + strip). No scale collapse in v2."""
    if effort is None:
        return None
    if isinstance(effort, str):
        return effort.strip().lower()
    return None
