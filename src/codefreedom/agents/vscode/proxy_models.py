"""Section 2 — Proxy VS Code config generator (``vscode proxy config``).

Generates a chatLanguageModels.json entry from the running LiteLLM proxy.
Probes /health/liveliness and /v1/model/info to auto-discover models.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from codefreedom.config.runtime import apply_cf_cli_overrides
from codefreedom.core.http_client import HTTPError, HTTPStatusError
from codefreedom.log import eprint, tag

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║ Section 2: Proxy VS Code config (`vscode proxy config`)                  ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
#
# Generates a chatLanguageModels.json entry for VS Code's built-in Copilot
# Chat custom-provider system.  Probes the running LiteLLM proxy at
# /health/liveliness and /v1/model/info.


# Default VS Code input reference inserted into the generated `apiKey` field.
# VS Code replaces this at runtime with a value the user stored via the input
# variable system.  Users should run VS Code's "Add Secret Input" command and
# paste this same key to wire the actual LITELLM_MASTER_KEY.
_VSCODE_APIKEY_PLACEHOLDER = "${input:codefreedom.litellm.master_key}"

# Default field fallbacks when the proxy /v1/model/info response omits a
# specific capability or token-limit.  These are conservative -- the user can
# edit the generated JSON to adjust per-model.
_DEFAULT_MAX_INPUT_TOKENS = 128000
_DEFAULT_MAX_OUTPUT_TOKENS = 16000

# Standard reasoning effort levels advertised to VS Code.
#
# The VS Code config always advertises the full standard set for any model
# that supports reasoning.  The proxy's reasoning-efforts mapping plugin
# translates these standard values to model-native values at runtime
# (see ``plugins/reasoning-efforts/reasoning-efforts-mapping.yaml``).
_STANDARD_REASONING_EFFORT_LEVELS: Tuple[str, ...] = (
    "none",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)

# Note: ``supportsReasoningEffort`` is now unconditionally advertised for
# ALL models.  The proxy's ``reasoning-efforts`` mapping plugin translates
# standard effort levels to model-native values at runtime.  If a model has
# no real reasoning capability, the plugin's rule maps everything to
# ``"none"`` -- the VS Code UI still shows the control but it's effectively
# a no-op.  No per-model rule table needed anymore.
#
# The old ``_REASONING_EFFORT_RULES`` tuple was removed because it required
# manual updates for every new model family and could not keep up with the
# proxy's plugin-based mapping.  The plugin IS the single source of truth.


def _resolve_reasoning_effort(_model_name: str) -> List[str]:
    """Return the supported `reasoning_effort` levels for *model_name*.

    Always returns the full standard set (``["none", "low", "medium",
    "high", "xhigh", "max"]``) for every model.  The proxy's
    reasoning-efforts mapping plugin handles translation to model-native
    values (thinking budgets, native reasoning_effort, pass-through) at
    runtime -- see ``plugins/reasoning-efforts/reasoning-efforts-mapping.yaml``.
    If a model truly has no reasoning capability, the mapping plugin's
    rule simply maps all levels to ``"none"``, and VS Code's UI still
    shows the control but the effect is a no-op.

    The ``_model_name`` parameter is accepted for backward compatibility
    with callers that already pass it, but is no longer consulted.
    Previously this function used a hardcoded rule table
    (``_REASONING_EFFORT_RULES``) to decide per-model, but that was fragile
    and required updates whenever a new model family was added.  Since the
    mapping plugin already covers all configured models, unconditionally
    advertising the field is both simpler and more future-proof.
    """
    return list(_STANDARD_REASONING_EFFORT_LEVELS)


def _load_route_image_models(codefreedom_dir: Optional[Path] = None) -> Set[str]:
    """Return model names that have ``route-image-request: enabled``.

    Reads provider YAML files from ``~/.codefreedom/config/proxy/config/providers/``
    and collects every ``model_name`` whose
    ``codefreedom.plugins.route-image-request.enabled`` is ``true``.
    """
    if codefreedom_dir is None:
        from codefreedom.core.config import get_config_dir

        codefreedom_dir = get_config_dir()
    providers_dir = codefreedom_dir / "proxy" / "config" / "providers"
    if not os.path.isdir(providers_dir):
        return set()
    result: Set[str] = set()
    for yp in glob.glob(os.path.join(providers_dir, "*.yaml")):
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
            cf = entry.get("codefreedom")
            if not (isinstance(name, str) and isinstance(cf, dict)):
                continue
            plugins = cf.get("plugins") or {}
            route_cfg = plugins.get("route-image-request")
            if isinstance(route_cfg, dict) and route_cfg.get("enabled") is True:
                result.add(name)
    return result


def _load_alias_models(codefreedom_dir: Optional[Path] = None) -> Set[str]:
    """Return model names that are ``model_group_alias`` entries.

    Reads ``~/.codefreedom/config/proxy/config/config.yaml`` and collects the
    keys of ``router_settings.model_group_alias``.
    """
    if codefreedom_dir is None:
        from codefreedom.core.config import get_config_dir

        codefreedom_dir = get_config_dir()
    config_path = codefreedom_dir / "proxy" / "config" / "config.yaml"
    if not config_path.is_file():
        return set()
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return set()
    if not isinstance(config, dict):
        return set()
    router = config.get("router_settings") or {}
    if not isinstance(router, dict):
        return set()
    aliases = router.get("model_group_alias") or {}
    if not isinstance(aliases, dict):
        return set()
    return set(aliases.keys())


def _resolve_master_key() -> Optional[str]:
    """Return LITELLM_MASTER_KEY from the canonical :func:`get_env` chain.

    Delegates to :func:`get_env` (``component="proxy"``) so the same
    precedence applies as everywhere else — env files, shared configs,
    ``os.environ``, and ``CF_CLI_*`` overrides.

    This is a convenience wrapper; ``cmd_vscode_proxy_config`` accesses
    the key directly from ``get_env()``.
    """
    merged = apply_cf_cli_overrides(dict(os.environ))
    key = merged.get("LITELLM_MASTER_KEY", "").strip()
    return key if key else None


def _proxy_health_url(host: str, port: int) -> str:
    """Return the URL used to probe proxy liveness."""
    return f"http://{host}:{port}/health/liveliness"


def _proxy_model_info_url(host: str, port: int) -> str:
    """Return the URL of the proxy's /v1/model/info endpoint."""
    return f"http://{host}:{port}/v1/model/info"


def _check_proxy_live(host: str, port: int, *, timeout: float = 5.0) -> bool:
    """Return True if the proxy is responding at /health/liveliness."""
    from codefreedom.core.http_client import check_health

    return check_health(_proxy_health_url(host, port), timeout=timeout)


def _fetch_model_info(
    host: str,
    port: int,
    master_key: str,
    *,
    timeout: float = 10.0,
) -> List[Dict[str, Any]]:
    """Fetch the proxy's /v1/model/info and return its `data` list.

    Raises HTTPStatusError on non-2xx responses (e.g. 401 for a bad
    master key) and HTTPError on network failures.
    """
    from codefreedom.core.http_client import get_json

    payload = get_json(
        _proxy_model_info_url(host, port),
        timeout=timeout,
        bearer=master_key,
    )
    if not isinstance(payload, dict):
        raise ValueError("Unexpected /v1/model/info response shape (not an object).")
    data = payload.get("data", [])
    if not isinstance(data, list):
        raise ValueError(
            "Unexpected /v1/model/info response shape (`data` not a list)."
        )
    return data


def _model_to_vscode_entry(
    model: Dict[str, Any],
    base_url: str,
    route_image_models: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Convert a single proxy model dict to a VS Code chatLanguageModels entry.

    `toolCalling` is always advertised as `True` so VS Code's chat UI shows
    the tool-calling affordance for every model.  LiteLLM does not have a
    reliable, model-agnostic capability database -- most providers don't
    populate `supports_function_calling` even when their models do support
    it -- so a permissive default is friendlier than a sparse "no" that
    hides tools the user actually has access to.  If a model truly does
    not support tool calling, the upstream API returns an error and the
    chat will surface it.

    `vision`, `maxInputTokens`, and `maxOutputTokens` are read from the
    LiteLLM `model_info` payload (keys: `supports_vision`, `max_input_tokens`,
    `max_output_tokens`, with `max_tokens` as a shared fallback).

    `supportsReasoningEffort` is always advertised with the full standard
    set (``["none", "low", "medium", "high", "xhigh", "max"]``) for
    every model.  The proxy's reasoning-efforts mapping plugin translates
    standard values to model-native values at runtime.
    """
    model_info = model.get("model_info") or {}
    if not isinstance(model_info, dict):
        model_info = {}

    model_name = model.get("model_name") or model_info.get("id") or "unknown"

    # Vision: be permissive -- anything truthy under these keys counts.
    # Also treat models with route-image-request enabled as vision-capable
    # since the proxy middleware handles image-to-text transcription.
    vision = bool(model_info.get("supports_vision") or model_info.get("vision"))
    if not vision and route_image_models and model_name in route_image_models:
        vision = True

    # Token limits: prefer explicit fields, fall back to defaults.
    max_input = (
        model_info.get("max_input_tokens")
        or model_info.get("max_tokens")
        or _DEFAULT_MAX_INPUT_TOKENS
    )
    max_output = (
        model_info.get("max_output_tokens")
        or model_info.get("max_tokens")
        or _DEFAULT_MAX_OUTPUT_TOKENS
    )

    try:
        max_input_int = int(max_input)
    except (TypeError, ValueError):
        max_input_int = _DEFAULT_MAX_INPUT_TOKENS
    try:
        max_output_int = int(max_output)
    except (TypeError, ValueError):
        max_output_int = _DEFAULT_MAX_OUTPUT_TOKENS

    entry: Dict[str, Any] = {
        "id": str(model_name),
        "name": str(model_name),
        "url": base_url,
        # Always advertise tool support -- see docstring for rationale.
        "toolCalling": True,
        "vision": vision,
        "maxInputTokens": max_input_int,
        "maxOutputTokens": max_output_int,
    }
    # Reasoning effort is always advertised.  The proxy's reasoning-efforts
    # mapping plugin translates standard levels to model-native values at
    # runtime (see ``plugins/reasoning-efforts/reasoning-efforts-mapping.yaml``).
    entry["supportsReasoningEffort"] = _resolve_reasoning_effort(str(model_name))
    return entry


def _resolve_model_id(model: Dict[str, Any]) -> str:
    """Resolve the canonical ID for a model dict from the proxy.

    Uses ``model_name``, falling back to ``model_info.id``, then a sentinel.
    """
    model_info = model.get("model_info") or {}
    if not isinstance(model_info, dict):
        model_info = {}
    return str(model.get("model_name") or model_info.get("id") or "unknown")


def _deduplicate_models(models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate *models* by their resolved ID.

    When two or more entries share the same ID (e.g. from LiteLLM model
    grouping / fallback groups), the entry with the richest ``model_info``
    dict wins — more keys means more capability metadata for VS Code.

    The input order is preserved for the first occurrence of each ID.
    """
    seen: Dict[str, Dict[str, Any]] = {}
    for m in models:
        mid = _resolve_model_id(m)
        if mid not in seen:
            seen[mid] = m
            continue
        existing = seen[mid]
        existing_info = existing.get("model_info") or {}
        if not isinstance(existing_info, dict):
            existing_info = {}
        candidate_info = m.get("model_info") or {}
        if not isinstance(candidate_info, dict):
            candidate_info = {}
        # Prefer the entry with richer model_info (more capability fields).
        if len(candidate_info) > len(existing_info):
            seen[mid] = m
    return list(seen.values())


def _build_vscode_entry(
    provider_name: str,
    base_url: str,
    models: List[Dict[str, Any]],
    route_image_models: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Build a single chatLanguageModels.json-compatible entry."""
    deduped = _deduplicate_models(models)
    return {
        "name": provider_name,
        "vendor": "customendpoint",
        "apiKey": _VSCODE_APIKEY_PLACEHOLDER,
        "apiType": "chat-completions",
        "models": [
            _model_to_vscode_entry(m, base_url, route_image_models) for m in deduped
        ],
    }


def cmd_vscode_proxy_config(args: argparse.Namespace) -> int:
    """Generate a chatLanguageModels.json entry from the running proxy.

    Entry point for ``codefreedom setup config vscode proxy config``.  Probes the proxy
    at /health/liveliness, fetches /v1/model/info with LITELLM_MASTER_KEY,
    and emits a JSON object that can be dropped into VS Code's user-level
    ``chatLanguageModels.json`` file (a list of provider entries).
    """
    host = args.host
    port = args.port or 4000
    provider_name = args.name
    out_path = Path(args.out) if args.out else None
    workspace_dir = Path.cwd()

    # Load the env chain so LITELLM_MASTER_KEY is resolved from CF_CLI_*
    # overrides (highest priority) or bare os.environ.
    eprint(
        f"{tag('VSCODE')} Loading env chain (proxy component) from {workspace_dir}..."
    )
    base_env = apply_cf_cli_overrides(dict(os.environ))

    eprint(f"{tag('VSCODE')} Probing proxy at {_proxy_health_url(host, port)} ...")
    if not _check_proxy_live(host, port):
        eprint(
            f"[ERROR] Proxy is not responding at http://{host}:{port}."
            " Is `codefreedom run proxy start` running?"
        )
        return 1

    master_key = base_env.get("LITELLM_MASTER_KEY", "").strip()
    if not master_key:
        eprint(
            "[ERROR] LITELLM_MASTER_KEY is not set."
            " Export CF_CLI_LITELLM_MASTER_KEY (recommended) or"
            " LITELLM_MASTER_KEY in your shell,"
            " then re-run this command."
        )
        return 1

    eprint(
        f"{tag('VSCODE')} Fetching models from {_proxy_model_info_url(host, port)} ..."
    )
    try:
        models = _fetch_model_info(host, port, master_key)
    except HTTPStatusError as exc:
        if exc.status_code in (401, 403):
            eprint(
                f"[ERROR] Proxy rejected the master key (HTTP {exc.status_code})."
                " Check LITELLM_MASTER_KEY."
            )
        else:
            eprint(f"{tag('ERROR')} /v1/model/info returned HTTP {exc.status_code}.")
        return 1
    except HTTPError as exc:
        eprint(f"{tag('ERROR')} Could not reach the proxy: {exc}")
        return 1
    except (ValueError, json.JSONDecodeError) as exc:
        eprint(f"{tag('ERROR')} Invalid response from /v1/model/info: {exc}")
        return 1

    base_url = f"http://{host}:{port}/v1"
    route_image_models = _load_route_image_models()

    keep_alias = getattr(args, "keep_alias", False)
    if not keep_alias:
        alias_models = _load_alias_models()
        if alias_models:
            before = len(models)
            models = [m for m in models if _resolve_model_id(m) not in alias_models]
            skipped = before - len(models)
            if skipped:
                eprint(
                    f"[vscode] Skipped {skipped} alias model(s)"
                    f" ({', '.join(sorted(alias_models))});"
                    " use --keep-alias to include them."
                )

    entry = _build_vscode_entry(provider_name, base_url, models, route_image_models)
    rendered = json.dumps(entry, indent=2)

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered + "\n", encoding="utf-8")
        eprint(f"{tag('VSCODE')} Wrote: {out_path}")
    else:
        print(rendered)

    model_count = len(entry["models"])
    eprint(
        f"[vscode] Done -- {model_count} model(s) included."
        f" apiKey is a VS Code input placeholder ({_VSCODE_APIKEY_PLACEHOLDER});"
        " create the matching secret in VS Code to wire the real master key."
    )
    return 0
