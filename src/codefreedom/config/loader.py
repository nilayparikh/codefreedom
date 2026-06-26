"""Configuration loader — single entry point for all CodeFreedom configuration.

Usage::

    from codefreedom.config import load_config

    config = load_config()
    agent_cfg = config.for_agent("claude-code", profile="default", mode="sandbox")
    tool_cfg = config.for_tool("chrome")
"""

from __future__ import annotations

import os
import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from codefreedom.config.errors import (
    ConfigError,
    SchemaValidationError,
)
from codefreedom.config.interpolation import interpolate_all
from codefreedom.config.models import (
    AgentDefinition,
    CommonSection,
    ConfigModel,
)


# ── Public return types ──────────────────────────────────────────────────

@dataclass(frozen=True)
class AgentConfig:
    """Resolved configuration for a single agent invocation."""
    agent: str
    profile_name: str
    env: Dict[str, str]
    tools: List[str]
    sandbox_images: Dict[str, str]
    sandbox_env: Dict[str, str]


@dataclass(frozen=True)
class ToolConfig:
    """Resolved configuration for a single tool launch."""
    name: str
    image: str
    container_name: str
    port: int
    env: Dict[str, str]
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedConfig:
    """Fully resolved, validated, immutable configuration.

    Created by :func:`load_config`. Every ${VAR} is resolved.
    Every cross-reference is validated.
    """
    common: CommonSection
    agents: Dict[str, AgentDefinition]
    tools: Dict[str, Dict[str, Any]]
    _config_dir: Path

    def for_agent(
        self,
        agent: str,
        profile: str = "default",
        mode: Optional[str] = None,
    ) -> AgentConfig:
        """Resolve runtime config for an agent.

        Args:
            agent: Canonical agent name (e.g. ``"claude-code"``).
            profile: Profile name (e.g. ``"default"``, ``"bare"``).
            mode: ``"sandbox"``, ``"local"``, or ``None``.

        Returns:
            AgentConfig with resolved env, tools, sandbox_images.
        """
        agent_def = self.agents.get(agent)
        if agent_def is None:
            known = sorted(self.agents.keys())
            raise ConfigError(
                f"Unknown agent '{agent}'. "
                f"Known agents: {known}"
            )

        profile_entry = agent_def.resolve_profile(profile, mode=mode)

        # Inherit sandbox images
        sandbox_images = dict(self.common.sandbox_images)
        if profile_entry.sandbox_images:
            sandbox_images.update(profile_entry.sandbox_images)

        return AgentConfig(
            agent=agent,
            profile_name=profile,
            env=dict(profile_entry.env),
            tools=list(profile_entry.tools or []),
            sandbox_images=sandbox_images,
            sandbox_env=dict(self.common.sandbox_env),
        )

    def for_tool(self, name: str) -> ToolConfig:
        """Resolve runtime config for a tool.

        Returns sensible defaults for known tools even if the
        tool section is sparsely populated. Default ``container_name`` values
        mirror the constants in each tool module (``tools/chrome.py``,
        ``tools/web.py``, ``tools/github.py``, ``tools/web_bridge.py``) so
        callers (e.g. ``cli/manage/doctor.py``) reach the *actual* running
        container rather than the legacy ``codefreedom-{name}-{suffix}`` form.
        """
        cfg = self.tools.get(name, {}) or {}

        _defaults: dict[str, Any] = {
            "chrome": {
                "image": "docker.io/nilayparikh/codefreedom:chrome-latest",
                "container_name": "codefreedom-chrome",
                "port": 9222,
            },
            "web": {
                "image": "docker.io/nilayparikh/codefreedom:web-latest",
                "container_name": "codefreedom-web",
                "port": 8420,
            },
            "github": {
                "image": "docker.io/nilayparikh/codefreedom:github-latest",
                "container_name": "codefreedom-tools-github",
                "port": 8129,
            },
            "git": {
                "model": "gpt-4o-mini",
                "container_name": "",
                "port": 0,
            },
            "web-bridge": {
                "image": "docker.io/nilayparikh/codefreedom:web-bridge-latest",
                "container_name": "codefreedom-web-bridge",
                "port": 8500,
            },
        }.get(name, {})

        defaults = dict(_defaults)
        for key in ("image", "container_name", "port"):
            val = cfg.get(key)
            if val is not None and val != "":
                defaults[key] = val

        extra: dict[str, Any] = {}
        for key, val in cfg.items():
            if key in ("image", "container_name", "port", "env"):
                continue
            extra[key] = val

        return ToolConfig(
            name=name,
            image=str(defaults.get("image", "")),
            container_name=str(defaults.get("container_name", f"codefreedom-{name}")),
            port=int(defaults.get("port", 0)) if defaults.get("port") else 0,
            env=dict(cfg.get("env", {}) or {}),
            extra=extra,
        )

    def for_component(self, name: str) -> Dict[str, str]:
        """Resolve a flat env dict for a named component (e.g. ``"proxy"``)."""
        if name == "proxy":
            proxy = self.common.proxy
            env: Dict[str, str] = {}
            env["LITELLM_BIND_HOST"] = proxy.bind_host
            env["LITELLM_PORT"] = str(proxy.bind_port)
            env.update(proxy.env)
            env["COMPOSE_PROJECT_NAME"] = f"codefreedom-{self.common.suffix_id}"
            env["SUFFIX_ID"] = self.common.suffix_id
            return env
        return {}

    def diagnose(self) -> List[str]:
        """Run diagnostics and return a list of issues found."""
        issues: List[str] = []
        for agent_name, agent_def in self.agents.items():
            for profile_name, profile in agent_def.profiles.items():
                for key, val in profile.env.items():
                    if "${" in val and ":-" not in val:
                        issues.append(
                            f"Agent '{agent_name}' profile '{profile_name}' "
                            f"env '{key}' contains unresolvable reference '{val}'"
                        )
        # Check for unresolved refs in tool defs
        for tool_name, cfg in self.tools.items():
            for key, val in cfg.items():
                if isinstance(val, str) and "${" in val and ":-" not in val:
                    issues.append(
                        f"Tool '{tool_name}' field '{key}' contains "
                        f"unresolvable reference '{val}'"
                    )
        return issues


# ── Internal helpers ────────────────────────────────────────────────────

def _flatten_dict(d: dict, prefix: str = "") -> Dict[str, str]:
    """Flatten nested dict into dotted-key entries for interpolation context."""
    items: Dict[str, str] = {}
    for key, val in d.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(val, dict):
            items.update(_flatten_dict(val, full_key))
        elif isinstance(val, str):
            items[full_key] = val
    return items


def _merge_deep(base: Any, override: Any) -> Any:
    """Recursive deep merge. Override wins. None values are skipped."""
    if override is None:
        return copy.deepcopy(base)
    if not isinstance(base, dict) or not isinstance(override, dict):
        return copy.deepcopy(override)
    result = copy.deepcopy(base)
    for key, val in override.items():
        if val is None:
            continue
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _merge_deep(result[key], val)
        else:
            result[key] = copy.deepcopy(val)
    return result


def _load_yaml_die(path: Path) -> dict:
    """Load a YAML file or raise ConfigError with a clear message."""
    if not path.exists():
        raise ConfigError(
            f"Configuration file not found: {path}\n"
            f"  Run: cf setup init to install a config"
        )
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(
            f"Failed to parse {path}:\n  {e}"
        ) from e
    if not isinstance(data, dict):
        raise ConfigError(
            f"Expected a mapping in {path}, got {type(data).__name__}"
        )
    return data


def _load_yaml_optional(path: Path) -> dict:
    """Load a YAML file if it exists, return empty dict otherwise."""
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            return data
    except yaml.YAMLError:
        pass
    return {}


def _build_context(merged: dict, vars: Dict[str, str] | None = None) -> Dict[str, str]:
    """Build the resolution context from config layers + CF_CLI_* overrides.

    Resolution order (later wins, all merged into context):
      1. common.* dotted keys (for ${common.proxy.bind_host} style refs)
      2. vars from recipe.yaml / override.yaml (dynamic key-value pairs)
      3. CF_CLI_* (stripped prefix — highest priority, overrides all)
    """
    context: Dict[str, str] = {}
    # Dotted keys from common section
    common_section = merged.get("common", {})
    if isinstance(common_section, dict):
        context.update(_flatten_dict(common_section, "common"))
    # Vars — dynamic key-value pairs from config layers
    if vars:
        context.update(vars)
    # CF_CLI_* — highest priority, stripped of prefix
    for key, val in os.environ.items():
        if key.startswith("CF_CLI_"):
            context[key[7:]] = val
    return context


# ── Public API ──────────────────────────────────────────────────────────

def load_config(config_dir: Optional[Path] = None) -> ResolvedConfig:
    """Load and resolve the full CodeFreedom configuration.

    Args:
        config_dir: Path to the config directory
            (defaults to ``~/.codefreedom/config``).

    Resolution order (later wins):
      1. ``profiles.yaml`` (recipe-provided defaults)
      2. ``override.yaml`` (user overrides — same schema)
      3. Machine env (``os.environ``)
      4. ``CF_CLI_*`` overrides (highest priority, prefix stripped)

    Returns:
        Frozen :class:`ResolvedConfig` with all ${VAR} resolved.

    Raises:
        ConfigError: On any configuration issue (missing file,
            malformed YAML, schema violation, missing secret).
    """
    from codefreedom.core.config import get_config_dir as _get_config_dir

    if config_dir is None:
        config_dir = _get_config_dir()

    # Step 1: Load YAML layers (lowest → highest precedence)
    base = _load_yaml_die(config_dir / "profiles.yaml")
    recipe = _load_yaml_optional(config_dir / "recipe.yaml")
    override = _load_yaml_optional(config_dir / "override.yaml")

    # Extract vars from each layer (list-of-dicts or flat dict)
    all_vars: Dict[str, str] = {}
    for layer in (base, recipe, override):
        raw = layer.pop("vars", None)
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    all_vars.update({str(k): str(v) for k, v in item.items()})
        elif isinstance(raw, dict):
            all_vars.update({str(k): str(v) for k, v in raw.items()})

    # Step 2: Full structural merge (later wins)
    merged = _merge_deep(base, recipe)
    merged = _merge_deep(merged, override)

    # Ensure common section exists with defaults so ${VAR} refs are interpolated.
    # CommonSection.suffix_id defaults to "${SUFFIX_ID:-0000}" — if the merged dict
    # has no common section (or an empty one), seed it so interpolation can resolve.
    merged.setdefault("common", {})
    merged["common"].setdefault("suffix_id", "${SUFFIX_ID:-0000}")
    merged["common"].setdefault("postgres", {})
    merged["common"]["postgres"].setdefault("host_port", "${POSTGRES_HOST_PORT:-5433}")
    merged["common"]["postgres"].setdefault("password", "${POSTGRES_PASSWORD:-pgpassword}")

    # Step 3: Build resolution context from config layers + CF_CLI_*
    context = _build_context(merged, vars=all_vars)

    # Step 4: Single-pass ${VAR} resolution
    resolved = copy.deepcopy(merged)
    interpolate_all(resolved, context)

    # Step 5: Fatal schema validation
    try:
        config_model = ConfigModel.model_validate(resolved)
    except Exception as e:
        raise SchemaValidationError(
            f"Configuration error in {config_dir / 'profiles.yaml'}:\n  {e}\n"
            f"Fix the file and try again. Run: cf doctor config"
        ) from e

    return ResolvedConfig(
        common=config_model.common,
        agents=config_model.agents,
        tools=config_model.tools,
        _config_dir=config_dir,
    )
