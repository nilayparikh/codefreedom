"""Pydantic model for claude-code-profiles.yaml — defines named profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel, Field

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


class ClaudeCodeProfiles(BaseModel, extra="forbid"):
    """Schema for claude-code-profiles.yaml."""

    description: Optional[str] = None
    notes: Optional[List[str]] = None
    profiles: Dict[str, ProfileEntry]

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
