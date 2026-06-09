"""Pydantic model for claude-code-profiles.json — defines named profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SandboxImages(BaseModel, extra="forbid"):
    """Sandbox images keyed by GPU type."""

    default: Optional[str] = None
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


class ClaudeCodeProfiles(BaseModel, extra="forbid"):
    """Schema for claude-code-profiles.json."""

    description: Optional[str] = None
    notes: Optional[List[str]] = None
    profiles: Dict[str, ProfileEntry]

    @classmethod
    def from_json(cls, path: Path) -> "ClaudeCodeProfiles":
        """Read a JSON file and validate against the model."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls.model_validate(data)
