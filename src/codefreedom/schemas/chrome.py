"""Pydantic model for chrome.yaml — Chrome browser tool profile."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel, Field

from codefreedom.interpolate import interpolate_all_strings


class ChromeSettings(BaseModel, extra="forbid"):
    """Chrome browser container settings."""

    image: Optional[str] = None
    container_name: Optional[str] = None
    port: Optional[int] = Field(default=None, ge=1024, le=65535)
    data_dir: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    mcp_port: Optional[int] = Field(default=None, ge=1024, le=65535)
    mcp_path: Optional[str] = None


class ChromeConfig(BaseModel, extra="forbid"):
    """Schema for chrome.yaml — configures the Chrome browser container."""

    description: Optional[str] = None
    notes: Optional[List[str]] = None
    chrome: ChromeSettings

    @classmethod
    def from_yaml(cls, path: Path) -> "ChromeConfig":
        """Read a YAML file and validate against the model."""
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Expected a mapping in {path}, got {type(data).__name__}")
        return cls.model_validate(data)

    def interpolate_envs(self, context: dict[str, str] | None = None) -> None:
        """Interpolate ${VAR} in the chrome env dict, in-place."""
        if self.chrome.env:
            interpolate_all_strings(self.chrome.env, context)
