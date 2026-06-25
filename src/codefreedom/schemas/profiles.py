"""Backward-compatible re-exports — models now live in codefreedom.config.models.

.. deprecated::
    Import from ``codefreedom.config`` directly instead.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field

from codefreedom.config.models import (
    ProfileEntry as _ProfileEntry,
)


class SandboxImages(BaseModel, extra="forbid"):
    """Sandbox images keyed by GPU type."""
    default: Optional[str] = None
    unified: Optional[str] = None
    cuda: Optional[str] = None
    rocm: Optional[str] = None


class ProfileEntry(_ProfileEntry):
    """Re-export from codefreedom.config.models.ProfileEntry."""
    pass


class AgentProfiles(BaseModel, extra="ignore"):
    """One agent's profile block."""
    profiles: Dict[str, ProfileEntry] = Field(default_factory=dict)


class ToolSettings(BaseModel, extra="allow"):
    """Settings for a single tool."""
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


class ProfilesConfig(BaseModel, extra="ignore"):
    """Top-level schema — delegates to codefreedom.config.models.ConfigModel."""
    common: CommonSettings = Field(default_factory=CommonSettings)
    profiles: Dict[str, AgentProfiles] = Field(default_factory=dict)
    tools: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Path) -> "ProfilesConfig":
        from codefreedom.config.models import ConfigModel
        cm = ConfigModel.from_yaml(path)
        return cls._from_config_model(cm)

    @classmethod
    def _from_config_model(cls, cm) -> "ProfilesConfig":
        profiles: Dict[str, AgentProfiles] = {}
        for agent_name, agent_def in cm.agents.items():
            pf: Dict[str, ProfileEntry] = {}
            for pname, pent in agent_def.profiles.items():
                pf[pname] = pent
            profiles[agent_name] = AgentProfiles(profiles=pf)
        return cls(
            common=CommonSettings(
                sandbox_images=dict(cm.common.sandbox_images),
                sandbox_env=dict(cm.common.sandbox_env),
            ),
            profiles=profiles,
            tools=dict(cm.tools),
        )

    def get_agent_profile(self, agent: str) -> Dict[str, ProfileEntry]:
        agent_profiles = self.profiles.get(agent)
        if agent_profiles is None:
            return {}
        return agent_profiles.profiles

    def get_tool_config(self, tool_key: str) -> Dict[str, Any]:
        return self.tools.get(tool_key, {})

    def get_tool_config_with_defaults(
        self, tool_key: str, defaults: Dict[str, Any]
    ) -> Dict[str, Any]:
        cfg = dict(defaults)
        tool = self.tools.get(tool_key, {})
        for key, val in tool.items():
            if val is not None and val != "":
                cfg[key] = val
        return cfg


# ── Singleton loader (deprecated) ───────────────────────────────────────

_config_instance: Optional[ProfilesConfig] = None
_config_path: Optional[Path] = None


def load_config(path: Optional[Path] = None) -> ProfilesConfig:
    """Load config — delegates to codefreedom.config.load_config().

    .. deprecated::
        Use ``codefreedom.config.load_config()`` instead.
    """
    global _config_instance, _config_path

    if path is None:
        from codefreedom.core.config import get_config_dir
        path = get_config_dir() / "profiles.yaml"

    if _config_instance is not None and _config_path == path:
        return _config_instance

    try:
        from codefreedom.config import load_config as _new_load
        new_config = _new_load(path.parent)
        # Build a ProfilesConfig from ResolvedConfig
        profiles: Dict[str, AgentProfiles] = {}
        for agent_name, agent_def in new_config.agents.items():
            pf: Dict[str, Any] = {}
            for pname, pent in agent_def.profiles.items():
                pf[pname] = pent
            profiles[agent_name] = AgentProfiles(profiles=pf)
        _config_instance = ProfilesConfig(
            common=CommonSettings(
                sandbox_images=dict(new_config.common.sandbox_images),
                sandbox_env=dict(new_config.common.sandbox_env),
            ),
            profiles=profiles,
            tools=dict(new_config.tools),
        )
        _config_path = path
        return _config_instance
    except Exception as exc:
        from codefreedom.log import eprint
        eprint(f"[WARN] Failed to load {path}: {exc}")
        _config_instance = ProfilesConfig()
        _config_path = path
        return _config_instance


def reset_config() -> None:
    global _config_instance, _config_path
    _config_instance = None
    _config_path = None


class ClaudeCodeProfiles(BaseModel, extra="ignore"):
    """Legacy schema — backward compatibility only."""
    description: Optional[str] = None
    notes: Optional[List[str]] = None
    common: Optional[Dict[str, Any]] = None
    profiles: Dict[str, ProfileEntry] = Field(default_factory=dict)
    tools: Optional[Dict[str, Any]] = None

    @classmethod
    def from_yaml(cls, path: Path) -> "ClaudeCodeProfiles":
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Expected a mapping in {path}, got {type(data).__name__}")
        return cls.model_validate(data)
