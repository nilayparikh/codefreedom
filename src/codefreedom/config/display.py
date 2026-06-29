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


def _extract_vars(layer: Dict[str, Any]) -> Dict[str, str]:
    """Extract vars dict from a layer (already popped before merge in load_config)."""
    raw = layer.get("vars", {})
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
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
    # Strip prefix to get bare var name for CF_CLI check
    bare_key = key.rsplit(".", 1)[-1] if "." in key else key
    cf_cli_key = f"CF_CLI_{bare_key}"
    if cf_cli_key in os.environ:
        return "CF_CLI_*"
    if bare_key in os.environ:
        return "env"

    # Check config layers
    from codefreedom.config.loader import _resolve_cf_yaml_path
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

    Builds the display dict directly from merged+interpolated layers,
    skipping ConfigModel validation so extra recipe fields don't block output.
    """
    from codefreedom.config.interpolation import interpolate_all
    import copy

    if config_dir is None:
        from codefreedom.core.config import get_config_dir as _get_config_dir
        config_dir = _get_config_dir()

    from codefreedom.config.loader import (
        _build_context,
        _load_yaml_die,
        _load_yaml_optional,
        _resolve_cf_yaml_path,
    )

    # Load layers to get vars for source tracking. The order matches
    # load_config(): profiles (lowest) < recipe < override < .cf.yaml.
    # The auto-discovered .cf.yaml path comes from the same resolver
    # the unified config uses, so display and runtime agree on what
    # file (if any) provides the per-folder layer.
    base = _load_yaml_die(config_dir / "profiles.yaml")
    recipe = _load_yaml_optional(config_dir / "recipe.yaml")
    override = _load_yaml_optional(config_dir / "override.yaml")
    cf_yaml_path = _resolve_cf_yaml_path()
    cf_yaml = _load_yaml_optional(cf_yaml_path) if cf_yaml_path else {}

    profiles_vars = _extract_vars(base)
    recipe_vars = _extract_vars(recipe)
    override_vars = _extract_vars(override)
    cf_yaml_vars = _extract_vars(cf_yaml)

    all_vars: Dict[str, str] = {}
    for layer in (base, recipe, override, cf_yaml):
        raw = layer.pop("vars", None)
        if isinstance(raw, dict):
            all_vars.update({str(k): str(v) for k, v in raw.items()})

    from codefreedom.config.loader import _merge_deep
    merged = _merge_deep(base, recipe)
    merged = _merge_deep(merged, override)
    merged = _merge_deep(merged, cf_yaml)

    # Strip recipe metadata that isn't part of config schema
    for key in ("name", "description", "version", "files", "dirs",
                "generated_artifacts", "required_secrets", "config_vars",
                "advice", "common_blocks", "profile_presets", "tools_optional"):
        merged.pop(key, None)

    merged.setdefault("common", {})
    merged["common"].setdefault("suffix_id", "${SUFFIX_ID:-0000}")
    merged["common"].setdefault("postgres", {})
    merged["common"]["postgres"].setdefault("host_port", "${POSTGRES_HOST_PORT:-5433}")
    merged["common"]["postgres"].setdefault("password", "${POSTGRES_PASSWORD:-pgpassword}")

    context = _build_context(merged, vars=all_vars)

    resolved = copy.deepcopy(merged)
    interpolate_all(resolved, context)

    # Build display dict from resolved data
    display_dict: Dict[str, Any] = {}

    # Common section — pick known fields from resolved.common
    common_data = resolved.get("common", {})
    common: Dict[str, Any] = {}
    if isinstance(common_data, dict):
        common["suffix_id"] = common_data.get("suffix_id", "")
        proxy = common_data.get("proxy", {})
        if isinstance(proxy, dict):
            common["proxy.bind_host"] = proxy.get("bind_host", "127.0.0.1")
            common["proxy.bind_port"] = str(proxy.get("bind_port", 4000))
            proxy_env = proxy.get("env", {})
            if proxy_env:
                common["proxy.env"] = dict(proxy_env)
        postgres = common_data.get("postgres", {})
        if isinstance(postgres, dict):
            common["postgres.host_port"] = postgres.get("host_port", "")
            common["postgres.user"] = postgres.get("user", "")
            common["postgres.password"] = postgres.get("password", "")
    display_dict["common"] = common

    # Vars section — show each var with its resolved value and source layer
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

        from codefreedom.config.interpolation import resolve_var
        resolved_raw = resolve_var(raw_value, context)

        cf_cli_key = f"CF_CLI_{var_name}"
        if cf_cli_key in os.environ:
            source = "CF_CLI_*"
            resolved_raw = os.environ[cf_cli_key]

        vars_display[var_name] = {"value": resolved_raw, "source": source}
    if vars_display:
        display_dict["vars"] = vars_display

    # Agents section — walk resolved.agents (legacy format with profiles: key)
    agents_data = resolved.get("agents", resolved.get("profiles", {}))
    agents_dict: Dict[str, Any] = {}
    if isinstance(agents_data, dict):
        for agent_name, agent_def in agents_data.items():
            if not isinstance(agent_def, dict):
                continue
            agent_data: Dict[str, Any] = {}
            # Unified format: agent_def.profiles.default.env
            agent_profiles = agent_def.get("profiles", agent_def)
            if isinstance(agent_profiles, dict):
                for pname, pdata in agent_profiles.items():
                    if not isinstance(pdata, dict):
                        continue
                    profile_data: Dict[str, Any] = {}
                    env = pdata.get("env", {})
                    if env:
                        profile_data["env"] = dict(env)
                    tools = pdata.get("tools")
                    if tools:
                        profile_data["tools"] = tools
                    local = pdata.get("local", {})
                    if isinstance(local, dict) and local.get("env"):
                        profile_data["local.env"] = dict(local["env"])
                    if profile_data:
                        agent_data[pname] = profile_data
            if agent_data:
                agents_dict[agent_name] = agent_data
    if agents_dict:
        display_dict["agents"] = agents_dict

    # Tools section
    tools_data = resolved.get("tools", {})
    tools_dict: Dict[str, Any] = {}
    if isinstance(tools_data, dict):
        for tool_name, tool_cfg in tools_data.items():
            if not isinstance(tool_cfg, dict):
                continue
            tool_data: Dict[str, Any] = {}
            for k in ("image", "container_name", "port", "mcp_port", "mcp_path"):
                if k in tool_cfg:
                    tool_data[k] = str(tool_cfg[k]) if not isinstance(tool_cfg[k], (dict, list)) else tool_cfg[k]
            env = tool_cfg.get("env", {})
            if env:
                tool_data["env"] = dict(env)
            # Extra fields
            for k, v in tool_cfg.items():
                if k not in ("image", "container_name", "port", "env", "mcp_port", "mcp_path"):
                    if isinstance(v, (dict, list)):
                        tool_data[k] = v
                    else:
                        tool_data[k] = str(v)
            if tool_data:
                tools_dict[tool_name] = tool_data
    if tools_dict:
        display_dict["tools"] = tools_dict

    # Format tree
    lines = _format_tree(display_dict, config_dir, context, indent=0, show_source=show_source)
    return "\n".join(lines)
