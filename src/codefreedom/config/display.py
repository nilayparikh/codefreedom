"""Reusable config display utilities for doctor, debug, and CLI output.

Provides secret redaction, source tracking, and formatted config tree output.
No cyclic dependencies — imports only from config and core layers.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── Secret detection ─────────────────────────────────────────────────────────

_SECRET_SUBSTRINGS: Tuple[str, ...] = (
    "TOKEN",
    "_KEY",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
)


def is_secret_key(name: str) -> bool:
    """Return True if the key name looks like it holds a secret.

    Uses case-insensitive substring matching. False positives are
    acceptable (user can see the redacted value); false negatives are
    a real risk.
    """
    upper = name.upper()
    return any(pat in upper for pat in _SECRET_SUBSTRINGS)


# ── Redaction ────────────────────────────────────────────────────────────────


def redact_value(value: str) -> str:
    """Redact a secret value, keeping first and last char visible.

    Examples:
        "sk-abc123xyz"  → "s********z"
        "abc"           → "***"
        "ab"            → "**"
        ""              → ""
        "x"             → "*"
    """
    if not value:
        return ""
    if len(value) <= 2:
        return "*" * len(value)
    return value[0] + "*" * (len(value) - 2) + value[-1]


# ── Source tracking ──────────────────────────────────────────────────────────


def _load_layer(config_dir: Path, filename: str) -> Dict[str, Any]:
    """Load a YAML layer, return empty dict if missing."""
    import yaml

    path = config_dir / filename
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _walk_values(data: Any, prefix: str = "") -> List[Tuple[str, Any]]:
    """Flatten nested dict into (dotted_key, value) pairs."""
    results: List[Tuple[str, Any]] = []
    if isinstance(data, dict):
        for key, val in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(val, dict):
                results.extend(_walk_values(val, full_key))
            elif isinstance(val, list):
                for i, item in enumerate(val):
                    results.extend(_walk_values(item, f"{full_key}[{i}]"))
            else:
                results.append((full_key, val))
    return results


def resolve_value_source(
    key: str,
    value: str,
    config_dir: Path,
    context: Dict[str, str],
) -> str:
    """Determine which layer provided this resolved value.

    Priority order (first match wins):
      1. CF_CLI_* env var
      2. ``.cf.yaml`` vars (per-folder override, if registered)
      3. override.yaml vars
      4. recipe.yaml vars
      5. profiles.yaml vars
      6. Default (model default)
    """
    from codefreedom.config.loader import _extract_vars, _resolve_cf_yaml_path

    # Strip prefix to get bare var name for CF_CLI check
    bare_key = key.rsplit(".", 1)[-1] if "." in key else key
    cf_cli_key = f"CF_CLI_{bare_key}"
    if cf_cli_key in os.environ:
        return "CF_CLI_*"
    if bare_key in os.environ:
        return "env"

    # Check config layers
    cf_yaml_path = _resolve_cf_yaml_path()
    cf_yaml_vars: Dict[str, str] = {}
    if cf_yaml_path:
        cf_yaml_vars = _extract_vars(
            _load_layer(cf_yaml_path.parent, cf_yaml_path.name)
        )
    override_vars = _extract_vars(_load_layer(config_dir, "override.yaml"))
    recipe_vars = _extract_vars(_load_layer(config_dir, "recipe.yaml"))
    profiles_vars = _extract_vars(_load_layer(config_dir, "profiles.yaml"))

    if bare_key in cf_yaml_vars:
        return ".cf.yaml"
    if bare_key in override_vars:
        return "override.yaml"
    if bare_key in recipe_vars:
        return "recipe.yaml"
    if bare_key in profiles_vars:
        return "profiles.yaml"

    return "default"


# ── Formatted output ─────────────────────────────────────────────────────────


def _format_tree(
    data: Any,
    config_dir: Path,
    context: Dict[str, str],
    indent: int = 0,
    prefix: str = "",
    show_source: bool = True,
) -> List[str]:
    """Format config tree with redaction and source labels."""
    lines: List[str] = []
    pad = "  " * indent

    if isinstance(data, dict):
        for key, val in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            # Special handling for vars section (dict with value + source)
            if isinstance(val, dict) and "value" in val and "source" in val:
                display_val = _display_value(
                    str(val["value"]), key, show_source, config_dir, full_key, context,
                    override_source=val["source"],
                )
                lines.append(f"{pad}{key}: {display_val}")
            elif isinstance(val, dict):
                lines.append(f"{pad}{key}:")
                lines.extend(
                    _format_tree(val, config_dir, context, indent + 1, full_key, show_source)
                )
            elif isinstance(val, list):
                lines.append(f"{pad}{key}:")
                for i, item in enumerate(val):
                    if isinstance(item, dict):
                        lines.extend(
                            _format_tree(item, config_dir, context, indent + 1, f"{full_key}[{i}]", show_source)
                        )
                    else:
                        display_val = _display_value(str(item), key, show_source, config_dir, full_key, context)
                        lines.append(f"{pad}  - {display_val}")
            else:
                display_val = _display_value(str(val), key, show_source, config_dir, full_key, context)
                lines.append(f"{pad}{key}: {display_val}")
    return lines


def _display_value(
    value: str,
    key: str,
    show_source: bool,
    config_dir: Path,
    full_key: str,
    context: Dict[str, str],
    override_source: Optional[str] = None,
) -> str:
    """Format a single value with redaction and optional source label."""
    if is_secret_key(key) and value:
        display = redact_value(value)
    else:
        display = value

    if show_source:
        source = override_source or resolve_value_source(full_key, value, config_dir, context)
        return f"{display} ({source})"
    return display


def format_resolved_config(
    config_dir: Optional[Path] = None,
    show_source: bool = True,
) -> str:
    """Format the full resolved config tree for display.

    Returns a multi-line string showing the config with interpolated
    values, redacted secrets, and source labels.

    Resolved values come from :func:`codefreedom.config.load_config` —
    the single source of truth shared with every other CLI command — so
    ``.cf.yaml`` and the per-folder discovery walk behave identically
    to ``cf run ...`` / ``cf setup ...``. Per-var source attribution is
    derived by re-reading the raw YAML layers (since ``load_config``
    strips ``vars:`` after merging).
    """
    if config_dir is None:
        from codefreedom.core.config import get_config_dir as _get_config_dir
        config_dir = _get_config_dir()

    from codefreedom.config import load_config
    from codefreedom.config.loader import (
        _build_context,
        _extract_vars,
        _load_yaml_die,
        _load_yaml_optional,
        _resolve_cf_yaml_path,
    )
    from codefreedom.config.interpolation import resolve_dict, resolve_var

    # ── Step 1: resolved values from the unified loader ────────────────────
    config = load_config(config_dir)

    # ── Step 2: raw layers for source attribution ────────────────────────
    # The order mirrors load_config(): profiles (lowest) < recipe <
    # override < .cf.yaml. The .cf.yaml path is auto-discovered via the
    # same resolver load_config uses, so display and runtime agree on
    # which file (if any) provides the per-folder layer.
    base = _load_yaml_die(config_dir / "profiles.yaml")
    recipe = _load_yaml_optional(config_dir / "recipe.yaml")
    override = _load_yaml_optional(config_dir / "override.yaml")
    cf_yaml_path = _resolve_cf_yaml_path()
    cf_yaml = _load_yaml_optional(cf_yaml_path) if cf_yaml_path else {}

    profiles_vars = _extract_vars(base)
    recipe_vars = _extract_vars(recipe)
    override_vars = _extract_vars(override)
    cf_yaml_vars = _extract_vars(cf_yaml)

    # Merged vars (later wins). Pop from the layer dicts so re-merging
    # for context building below doesn't carry stale "vars:" entries.
    all_vars: Dict[str, str] = {}
    for layer in (base, recipe, override, cf_yaml):
        all_vars.update(_extract_vars(layer))
        layer.pop("vars", None)

    # ── Step 3: build display dict from the resolved model ────────────────
    display_dict: Dict[str, Any] = {}

    # Common section — pick known fields from the resolved model
    common_data = config.common.model_dump()
    common: Dict[str, Any] = {}
    common["suffix_id"] = common_data.get("suffix_id", "")
    proxy = common_data.get("proxy", {}) or {}
    if proxy:
        common["proxy.bind_host"] = proxy.get("bind_host", "127.0.0.1")
        common["proxy.bind_port"] = str(proxy.get("bind_port", 4000))
        proxy_env = proxy.get("env", {})
        if proxy_env:
            common["proxy.env"] = dict(proxy_env)
    postgres = common_data.get("postgres", {}) or {}
    if postgres:
        common["postgres.host_port"] = postgres.get("host_port", "")
        common["postgres.user"] = postgres.get("user", "")
        common["postgres.password"] = postgres.get("password", "")
    display_dict["common"] = common

    # Vars section — show each var with its resolved value and source layer.
    # The raw_value is re-resolved against the merged context (built from
    # the same vars + CF_CLI_* that load_config uses) so a var that
    # references another var is shown interpolated. CF_CLI_* always wins
    # both the source label and the displayed value.
    if all_vars:
        context = _build_context(common_data, vars=all_vars)
        context = resolve_dict(context, context)

        vars_display: Dict[str, Any] = {}
        for var_name, final_value in all_vars.items():
            if var_name in cf_yaml_vars:
                source = ".cf.yaml"
                raw_value = cf_yaml_vars[var_name]
            elif var_name in override_vars:
                source = "override.yaml"
                raw_value = override_vars[var_name]
            elif var_name in recipe_vars:
                source = "recipe.yaml"
                raw_value = recipe_vars[var_name]
            elif var_name in profiles_vars:
                source = "profiles.yaml"
                raw_value = profiles_vars[var_name]
            else:
                source = "default"
                raw_value = final_value

            resolved_raw = resolve_var(raw_value, context)

            cf_cli_key = f"CF_CLI_{var_name}"
            if cf_cli_key in os.environ:
                source = "CF_CLI_*"
                resolved_raw = os.environ[cf_cli_key]

            vars_display[var_name] = {"value": resolved_raw, "source": source}
        display_dict["vars"] = vars_display

    # Agents section — walk the resolved model (Pydantic AgentDefinition)
    agents_dict: Dict[str, Any] = {}
    for agent_name, agent_def in config.agents.items():
        agent_data: Dict[str, Any] = {}
        for pname, profile in agent_def.profiles.items():
            profile_data: Dict[str, Any] = {}
            if profile.env:
                profile_data["env"] = dict(profile.env)
            if profile.tools:
                profile_data["tools"] = list(profile.tools)
            if profile.local and profile.local.env:
                profile_data["local.env"] = dict(profile.local.env)
            if profile_data:
                agent_data[pname] = profile_data
        if agent_data:
            agents_dict[agent_name] = agent_data
    if agents_dict:
        display_dict["agents"] = agents_dict

    # Tools section — walk the resolved model (raw dicts by design)
    tools_dict: Dict[str, Any] = {}
    for tool_name, tool_cfg in config.tools.items():
        if not isinstance(tool_cfg, dict):
            continue
        tool_data: Dict[str, Any] = {}
        for k in ("image", "container_name", "port", "mcp_port", "mcp_path"):
            if k in tool_cfg:
                v = tool_cfg[k]
                tool_data[k] = str(v) if not isinstance(v, (dict, list)) else v
        env = tool_cfg.get("env", {})
        if env:
            tool_data["env"] = dict(env)
        for k, v in tool_cfg.items():
            if k in ("image", "container_name", "port", "env", "mcp_port", "mcp_path"):
                continue
            if isinstance(v, (dict, list)):
                tool_data[k] = v
            else:
                tool_data[k] = str(v)
        if tool_data:
            tools_dict[tool_name] = tool_data
    if tools_dict:
        display_dict["tools"] = tools_dict

    # ── Step 4: format the tree ───────────────────────────────────────────
    # The formatter needs a flat str→str context for any ${VAR} interpolation
    # inside secret values; reuse the same one we built for the vars section.
    format_context: Dict[str, str] = {}
    if all_vars:
        format_context = _build_context(common_data, vars=all_vars)
        format_context = resolve_dict(format_context, format_context)

    lines = _format_tree(display_dict, config_dir, format_context, indent=0, show_source=show_source)
    return "\n".join(lines)
