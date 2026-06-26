"""Pydantic models for the unified CodeFreedom configuration schema.

Single source of truth for profiles.yaml and override.yaml structure.
New components add a top-level section. New agents add an entry to agents:.
New tools add an entry to tools:.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, model_validator

from codefreedom.config.errors import SchemaValidationError


def unwrap_double_nested(data: dict[str, Any]) -> bool:
    """Repair accidentally double-wrapped ``agents`` in-place; return True if repaired.

    Symptom (seen in the wild): an older codefreedom run wrote
    ``agents.claude-code.profiles.<agent>.profiles.<profile>`` instead of
    ``agents.<agent>.profiles.<profile>``. The flat-format fallback had run
    on already-wrapped data and produced a single outer ``claude-code`` agent
    whose ``profiles`` map keys are *agent names*, not profile names.

    Detection: a single outer agent whose ``profiles`` keys are a subset of
    :data:`_AGENT_NAMES` and whose values each carry a nested ``profiles``
    dict. We rewrite ``agents`` to the inner per-agent dict.
    """
    agents = data.get("agents")
    if not isinstance(agents, dict) or len(agents) != 1:
        return False
    (outer_name, outer_val), = agents.items()
    if not isinstance(outer_val, dict):
        return False
    inner = outer_val.get("profiles")
    if not isinstance(inner, dict) or not inner:
        return False
    if not all(k in _AGENT_NAMES for k in inner.keys()):
        return False
    if not all(isinstance(v, dict) and isinstance(v.get("profiles"), dict)
               for v in inner.values()):
        return False
    data["agents"] = inner
    return True


# Backwards-compat alias used by the validator (renamed public helper above).
_unwrap_double_nested = unwrap_double_nested


# ── Common Settings ──────────────────────────────────────────────────────

class ProxySettings(BaseModel, extra="forbid"):
    bind_host: str = "127.0.0.1"
    bind_port: int = 4000
    env: Dict[str, str] = Field(default_factory=dict)


class PostgresSettings(BaseModel, extra="forbid"):
    host_data_dir: str = "~/.codefreedom/config/pg/data"
    host_port: str = "${POSTGRES_HOST_PORT:-5433}"
    user: str = "pguser"
    password: str = "${POSTGRES_PASSWORD:-pgpassword}"


class CommonSection(BaseModel, extra="forbid"):
    proxy: ProxySettings = Field(default_factory=ProxySettings)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    suffix_id: str = "${SUFFIX_ID:-0000}"



# ── Mode-specific overrides ─────────────────────────────────────────────

class ModeEnv(BaseModel, extra="forbid"):
    env: Dict[str, str] = Field(default_factory=dict)


# ── Single profile ──────────────────────────────────────────────────────

class ProfileEntry(BaseModel, extra="forbid"):
    description: str = ""
    tools: Optional[List[str]] = None
    env: Dict[str, str] = Field(default_factory=dict)
    local: Optional[ModeEnv] = None
    extensions: Optional[List[str]] = None
    lsp_servers: Optional[Dict[str, List[str]]] = None

    @classmethod
    def merge(cls, base: ProfileEntry, override: ProfileEntry) -> ProfileEntry:
        """Merge two profile entries — override wins."""
        env = {**base.env, **override.env}
        tools: list[str] | None
        if override.tools is not None and base.tools is not None:
            seen = set(base.tools)
            tools = list(base.tools) + [t for t in override.tools if t not in seen]
        else:
            tools = override.tools if override.tools is not None else base.tools
        local_env = {
            **((base.local.env) if base.local else {}),
            **((override.local.env) if override.local else {}),
        }
        return cls(
            env=env,
            tools=tools,
            local=ModeEnv(env=local_env) if local_env else None,
            extensions=override.extensions if override.extensions is not None else base.extensions,
            lsp_servers=override.lsp_servers if override.lsp_servers is not None else base.lsp_servers,
        )


# ── Agent definition ────────────────────────────────────────────────────

class AgentDefinition(BaseModel, extra="forbid"):
    """One agent block in profiles.yaml (e.g. claude-code, mimo-code)."""
    profiles: Dict[str, ProfileEntry] = Field(default_factory=dict)

    def resolve_profile(
        self, name: str, mode: Optional[str] = None
    ) -> ProfileEntry:
        """Resolve a named profile with inheritance.

        ``default`` and ``bare`` are standalone (no inheritance).
        All other profiles inherit from ``default``.
        If *mode* is provided ("local"), mode-specific
        env overrides are layered on top.
        """
        if name == "bare":
            return self._with_mode(self.profiles.get("bare", ProfileEntry()), mode)

        default = self.profiles.get("default", ProfileEntry())

        if name == "default":
            return self._with_mode(default, mode)

        child = self.profiles.get(name, ProfileEntry())
        merged = ProfileEntry.merge(default, child)
        return self._with_mode(merged, mode)

    @staticmethod
    def _with_mode(
        entry: ProfileEntry, mode: Optional[str]
    ) -> ProfileEntry:
        if mode != "local":
            return entry
        mode_env = getattr(entry, mode, None)
        if mode_env and mode_env.env:
            entry.env = {**entry.env, **mode_env.env}
        return entry


# ── Tool configuration ──────────────────────────────────────────────────

class ToolDefinition(BaseModel, extra="allow"):
    """Settings for a single tool (chrome, web, github, web-bridge, git).

    Uses extra="allow" because each tool has different fields.
    Consumers access fields via getattr or .model_extra.
    """
    image: Optional[str] = None
    container_name: Optional[str] = None
    port: Optional[int] = None
    env: Dict[str, str] = Field(default_factory=dict)


# ── Top-level config model ─────────────────────────────────────────────

# ── Canonical agent names used to detect old vs. new format ────────────

_AGENT_NAMES = frozenset({
    "claude-code", "mimo-code", "open-code", "pi-code", "codex-code",
})

# Keys that may appear in a recipe *manifest* (recipe.yaml) but are NOT
# part of the config schema. They leak into the merged config dict when
# ``load_config`` layers recipe.yaml on top of profiles.yaml (recipe.yaml
# contributes ``vars``; the rest is manifest metadata). Stripping them here
# keeps ``extra="forbid"`` strict for genuine schema drift while tolerating
# a recipe manifest sitting next to the config. The single source of truth
# for this set; ``loader.py`` and ``display.py`` reuse it.
RECIPE_MANIFEST_KEYS: frozenset[str] = frozenset({
    "name", "description", "version", "files", "dirs",
    "generated_artifacts", "required_secrets", "config_vars",
    "advice", "common_blocks", "profile_presets", "tools_optional",
    "extends", "optional_config", "service_groups",
    "vars",  # extracted separately before validation
})

# Legacy ``common:`` keys from older recipe profiles.yaml versions. They
# survive DeepDiff merges (which never delete) so users with config created
# by an older recipe keep validating after upgrade. By the time the
# before-validator runs, ``${...}`` interpolation has already baked their
# values into the consuming fields, so they are residual and safe to drop.
_LEGACY_COMMON_KEYS: frozenset[str] = frozenset({
    "proxy_env",   # old: {PROXY_BASE_URL, PROXY_API_KEY} -> now common.proxy.env / vars
    "tools",        # old: [chrome, web, ...] -> now top-level tools: dict
    "tool_images",  # old: {base, tag} -> now inline in tools.<name>.image
})


class ConfigModel(BaseModel, extra="forbid"):
    """Top-level schema for profiles.yaml — the single configuration file.

    Supports both the new ``agents:`` format and the legacy ``profiles:``
    format. In legacy mode, top-level ``profiles:`` entries are detected
    and automatically converted: if every key is a known agent name, they
    become ``agents.<name>.profiles``; otherwise they become
    ``agents.claude-code.profiles``.

    Structure::

        common:
          proxy: {bind_host, bind_port, env}
          postgres: {host_port, user, password}
          suffix_id
        agents:
          claude-code:
            profiles:
              default: {env, tools, local}
              bare: {env}
        tools:
          chrome: {image, port, container_name, env}
          web: {image, port, ...}
          github: {image, port, ...}
          git: {model, conventional_commit}
    """
    common: CommonSection = Field(default_factory=CommonSection)
    agents: Dict[str, AgentDefinition] = Field(default_factory=dict)
    tools: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_format(cls, data: Any) -> Any:
        """Normalize legacy/foreign keys before strict field validation.

        Handles four classes of drift so ``extra="forbid"`` stays strict
        for genuine schema errors while tolerating config produced by
        older recipes or layered next to a recipe manifest:

        1. ``comment`` / ``vars`` (override.yaml) — stripped.
        2. Recipe-manifest keys (``name``, ``files``, ``required_secrets`` …)
           that leak in when ``load_config`` layers recipe.yaml on top of
           profiles.yaml. Stripped via :data:`RECIPE_MANIFEST_KEYS`.
        3. Legacy ``common:`` keys (``proxy_env``, ``tools`` list,
           ``tool_images``) from older recipe profiles.yaml. By the time
           this before-validator runs, ``${...}`` interpolation has already
           baked their values into the consuming fields, so they are
           residual and safe to drop.
        4. Legacy ``profiles:`` → ``agents:`` conversion (unified/flat),
           plus unwrapping of accidentally double-wrapped agents produced by
           the flat-format fallback running on already-wrapped data.
        """
        if not isinstance(data, dict):
            return data

        # 1. Non-schema keys from override.yaml
        data.pop("comment", None)
        data.pop("vars", None)

        # 2. Recipe-manifest metadata that leaked in via load_config merge
        for key in RECIPE_MANIFEST_KEYS:
            data.pop(key, None)

        # 3. Legacy common: keys (residual post-interpolation)
        common = data.get("common")
        if isinstance(common, dict):
            for key in _LEGACY_COMMON_KEYS:
                common.pop(key, None)
            if not common:
                data.pop("common", None)

        # 4a. If the file already uses the new format, keep it — but first
        # strip a stray "profiles" key merged from override.yaml and repair
        # accidentally double-wrapped agents (see _unwrap_double_nested).
        if "agents" in data:
            data.pop("profiles", None)
            _unwrap_double_nested(data)
            return data

        # 4b. Detect legacy format: top-level "profiles" key exists
        raw_profiles = data.get("profiles")
        if raw_profiles is None or not isinstance(raw_profiles, dict):
            return data

        # Classify entries: agent-keyed (have "profiles" subkey and key is
        # a known agent name) vs. flat entries (old per-agent format).
        agent_entries: dict[str, Any] = {}
        flat_entries: dict[str, Any] = {}
        for key, val in raw_profiles.items():
            if (isinstance(val, dict) and "profiles" in val
                    and key in _AGENT_NAMES):
                agent_entries[key] = val
            else:
                flat_entries[key] = val

        if agent_entries:
            # Unified format — possibly mixed with flat entries from an
            # override.yaml deep-merge (override had flat `profiles:`
            # which merged into the base's agent-keyed `profiles:`).
            # Extract agent entries as-is and fold remaining flat entries
            # into claude-code.profiles (old flat format always targeted
            # claude-code).
            data["agents"] = agent_entries
            if flat_entries and "claude-code" in agent_entries:
                agent_entries["claude-code"]["profiles"].update(flat_entries)
            del data["profiles"]
            return data

        # Pure flat format: profiles: {default: {env: ...}, bare: {env: ...}}
        #   → agents: {claude-code: {profiles: {default: {...}, bare: {...}}}}
        data["agents"] = {"claude-code": {"profiles": raw_profiles}}
        del data["profiles"]
        return data

    @model_validator(mode="after")
    def _validate_cross_references(self) -> "ConfigModel":
        """All tool references in agent profiles must exist in tools section."""
        known_tools = set(self.tools.keys())
        for agent_name, agent_def in self.agents.items():
            for profile_name, profile in agent_def.profiles.items():
                if not profile.tools:
                    continue
                for tool_name in profile.tools:
                    if tool_name not in known_tools:
                        raise ValueError(
                            f"Agent '{agent_name}' profile '{profile_name}' "
                            f"references unknown tool '{tool_name}'. "
                            f"Known tools: {sorted(known_tools)}"
                        )
        return self

    @classmethod
    def from_yaml(cls, path: Path) -> "ConfigModel":
        """Read a YAML file and validate against the model.

        Raises SchemaValidationError on failure.
        """
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except (yaml.YAMLError, OSError) as e:
            raise SchemaValidationError(
                f"Failed to parse {path}:\n  {e}"
            ) from e

        if not isinstance(data, dict):
            raise SchemaValidationError(
                f"Expected a mapping in {path}, got {type(data).__name__}"
            )

        try:
            return cls.model_validate(data)
        except Exception as e:
            raise SchemaValidationError(
                f"Schema validation error in {path}:\n  {e}"
            ) from e

    @classmethod
    def from_yaml_optional(cls, path: Path) -> Optional["ConfigModel"]:
        """Read a YAML file if it exists, return None otherwise."""
        if not path.exists():
            return None
        return cls.from_yaml(path)
