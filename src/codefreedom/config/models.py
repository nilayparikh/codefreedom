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
    sandbox_images: Dict[str, str] = Field(default_factory=dict)
    sandbox_env: Dict[str, str] = Field(default_factory=dict)
    proxy: ProxySettings = Field(default_factory=ProxySettings)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    suffix_id: str = "${SUFFIX_ID:-0000}"


# ── Mode-specific overrides ─────────────────────────────────────────────

class ModeEnv(BaseModel, extra="forbid"):
    env: Dict[str, str] = Field(default_factory=dict)


# ── Single profile ──────────────────────────────────────────────────────

class ProfileEntry(BaseModel, extra="forbid"):
    description: str = ""
    sandbox_images: Optional[Dict[str, str]] = None
    tools: Optional[List[str]] = None
    env: Dict[str, str] = Field(default_factory=dict)
    sandbox: Optional[ModeEnv] = None
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
        sandbox_images = {
            **(base.sandbox_images or {}),
            **(override.sandbox_images or {}),
        }
        sandbox_env = {
            **((base.sandbox.env) if base.sandbox else {}),
            **((override.sandbox.env) if override.sandbox else {}),
        }
        local_env = {
            **((base.local.env) if base.local else {}),
            **((override.local.env) if override.local else {}),
        }
        return cls(
            env=env,
            tools=tools,
            sandbox_images=sandbox_images or None,
            sandbox=ModeEnv(env=sandbox_env) if sandbox_env else None,
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
        If *mode* is provided ("sandbox" | "local"), mode-specific
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
        if mode not in ("sandbox", "local"):
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


class ConfigModel(BaseModel, extra="forbid"):
    """Top-level schema for profiles.yaml — the single configuration file.

    Supports both the new ``agents:`` format and the legacy ``profiles:``
    format. In legacy mode, top-level ``profiles:`` entries are detected
    and automatically converted: if every key is a known agent name, they
    become ``agents.<name>.profiles``; otherwise they become
    ``agents.claude-code.profiles``.

    Structure::

        common:
          sandbox_images: {default, cuda, rocm}
          proxy: {bind_host, bind_port, env}
          postgres: {host_port, user, password}
          suffix_id
        agents:
          claude-code:
            profiles:
              default: {env, tools, sandbox_images, sandbox, local}
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
        """Convert legacy ``profiles:`` → ``agents:`` automatically."""
        if not isinstance(data, dict):
            return data

        # If the file already uses the new format, keep it as-is.
        if "agents" in data:
            return data

        # Detect legacy format: top-level "profiles" key exists
        raw_profiles = data.get("profiles")
        if raw_profiles is None or not isinstance(raw_profiles, dict):
            return data

        # If every key in profiles is a known agent name, wrap them.
        # e.g. profiles: {claude-code: {profiles: {default: {...}}}}
        #   → agents: {claude-code: {profiles: {default: {...}}}}
        is_unified = all(
            isinstance(v, dict) and "profiles" in v
            for v in raw_profiles.values()
        )
        if is_unified:
            # Map the top-level "profiles" to "agents"
            data["agents"] = raw_profiles
            del data["profiles"]
            return data

        # Flat format: profiles: {default: {env: ...}, bare: {env: ...}}
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
