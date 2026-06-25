"""Pydantic models for profiles.yaml — the single source of config."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator

from codefreedom.core.interpolate import interpolate_all_strings


class SandboxImages(BaseModel, extra="forbid"):
    """Sandbox images keyed by GPU type."""

    default: Optional[str] = None
    unified: Optional[str] = None
    cuda: Optional[str] = None
    rocm: Optional[str] = None


class ModeEnv(BaseModel, extra="forbid"):
    """Mode-specific environment overrides."""

    env: Optional[Dict[str, str]] = None


class ProfileEntry(BaseModel, extra="forbid"):
    """A single named profile."""

    description: str = ""
    sandbox_images: Optional[SandboxImages] = None
    tools: Optional[List[str]] = None
    env: Dict[str, str] = Field(default_factory=dict)
    sandbox: Optional[ModeEnv] = None
    local: Optional[ModeEnv] = None
    extensions: Optional[List[str]] = None
    lsp_servers: Optional[Dict[str, List[str]]] = None

    @field_validator("env", mode="before")
    @classmethod
    def _coerce_none_env_values(cls, v: Any) -> Any:
        """Convert None values in env dicts to empty strings."""
        if isinstance(v, dict):
            return {k: ("" if val is None else val) for k, val in v.items()}
        return v


class AgentProfiles(BaseModel, extra="ignore"):
    """One agent's profile block (e.g. claude-code, mimo-code)."""

    profiles: Dict[str, ProfileEntry] = Field(default_factory=dict)


class ToolSettings(BaseModel, extra="allow"):
    """Settings for a single tool (chrome, web, github, web-bridge, git).

    Uses ``extra="allow"`` because each tool has a different shape and
    the fields are tool-specific. Consumers access fields via dict-style
    ``settings.get("port", 9223)``.
    """

    image: Optional[str] = None
    container_name: Optional[str] = None
    port: Optional[int] = None
    env: Dict[str, str] = Field(default_factory=dict)


class GitToolSettings(BaseModel, extra="allow"):
    """Settings for the git commit tool."""

    model: str = "gpt-4o-mini"
    conventional_commit: bool = True
    signed_commit: bool = True
    templates: Dict[str, str] = Field(default_factory=dict)
    modules: List[str] = Field(default_factory=list)


class CommonSettings(BaseModel, extra="allow"):
    """Common settings shared across agents and tools."""

    sandbox_images: Dict[str, str] = Field(default_factory=dict)
    sandbox_env: Dict[str, str] = Field(default_factory=dict)
    proxy_env: Dict[str, str] = Field(default_factory=dict)
    tools: List[str] = Field(default_factory=list)
    tool_images: Dict[str, str] = Field(default_factory=dict)

    @field_validator("sandbox_env", "proxy_env", mode="before")
    @classmethod
    def _coerce_none_values(cls, v: Any) -> Any:
        """Convert None values in env dicts to empty strings."""
        if isinstance(v, dict):
            return {k: ("" if val is None else val) for k, val in v.items()}
        return v


class ProfilesConfig(BaseModel, extra="ignore"):
    """Top-level schema for profiles.yaml — the single source of config.

    Structure::

        common:
          sandbox_images: { default: ..., cuda: ..., rocm: ... }
          tools: [chrome, web, github]
          tool_images: { base: ..., tag: ... }
        profiles:
          claude-code:
            profiles:
              default: { env: { ... } }
        tools:
          chrome: { image: ..., port: ..., ... }
          git: { model: ..., ... }
    """

    common: CommonSettings = Field(default_factory=CommonSettings)
    profiles: Dict[str, AgentProfiles] = Field(default_factory=dict)
    tools: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Path) -> "ProfilesConfig":
        """Read a YAML file and validate against the model."""
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Expected a mapping in {path}, got {type(data).__name__}")
        return cls.model_validate(data)

    def get_agent_profile(self, agent: str) -> Dict[str, ProfileEntry]:
        """Return the profiles dict for a named agent (e.g. 'claude-code')."""
        agent_profiles = self.profiles.get(agent)
        if agent_profiles is None:
            return {}
        return agent_profiles.profiles

    def get_tool_config(self, tool_key: str) -> Dict[str, Any]:
        """Return the raw tool config dict for a named tool."""
        return self.tools.get(tool_key, {})

    def get_tool_config_with_defaults(
        self, tool_key: str, defaults: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Return tool config merged with defaults (defaults are lowest priority)."""
        cfg = dict(defaults)
        tool = self.tools.get(tool_key, {})
        for key, val in tool.items():
            if val is not None and val != "":
                cfg[key] = val
        return cfg


# ── Singleton loader ─────────────────────────────────────────────────────

_config_instance: Optional[ProfilesConfig] = None
_config_path: Optional[Path] = None


def load_config(path: Optional[Path] = None) -> ProfilesConfig:
    """Load and return the unified profiles.yaml config (singleton).

    When *path* is ``None``, resolves from ``get_config_dir() / "profiles.yaml"``.
    The instance is cached; pass a new *path* to force a reload.
    """
    global _config_instance, _config_path

    if path is None:
        from codefreedom.core.config import get_config_dir

        path = get_config_dir() / "profiles.yaml"

    if _config_instance is not None and _config_path == path:
        return _config_instance

    if not path.exists():
        _config_instance = ProfilesConfig()
        _config_path = path
        return _config_instance

    try:
        _config_instance = ProfilesConfig.from_yaml(path)
        _config_path = path
    except Exception as exc:
        from codefreedom.log import eprint

        eprint(f"[WARN] Failed to load {path}: {exc}")
        _config_instance = ProfilesConfig()
        _config_path = path

    return _config_instance


def reset_config() -> None:
    """Clear the cached config instance (for testing)."""
    global _config_instance, _config_path
    _config_instance = None
    _config_path = None


# ── Backward-compatible alias ───────────────────────────────────────────

# Keep ClaudeCodeProfiles working for code that still uses the old model.
# It reads the same file but only cares about the ``profiles:`` section.


class ClaudeCodeProfiles(BaseModel, extra="ignore"):
    """Legacy schema — wraps ProfilesConfig for backward compatibility.

    New code should use :func:`load_config` instead.
    """

    description: Optional[str] = None
    notes: Optional[List[str]] = None
    common: Optional[Dict[str, Any]] = None
    profiles: Dict[str, ProfileEntry] = Field(default_factory=dict)
    tools: Optional[Dict[str, Any]] = None

    @classmethod
    def from_yaml(cls, path: Path) -> "ClaudeCodeProfiles":
        """Read a YAML file and validate against the model."""
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Expected a mapping in {path}, got {type(data).__name__}")
        return cls.model_validate(data)

    def interpolate_envs(self, context: dict[str, str] | None = None) -> None:
        """Interpolate ${VAR} in all env dicts within profiles, in-place."""
        for entry in self.profiles.values():
            if entry.env:
                interpolate_all_strings(entry.env, context)
            if entry.sandbox and entry.sandbox.env:
                interpolate_all_strings(entry.sandbox.env, context)
            if entry.local and entry.local.env:
                interpolate_all_strings(entry.local.env, context)
