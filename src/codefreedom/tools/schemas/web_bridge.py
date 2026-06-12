"""Pydantic model for web-bridge.yaml — Web search bridge tool profile."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel, Field


class WebBridgeSettings(BaseModel, extra="forbid"):
    """Web search bridge container settings."""

    image: Optional[str] = None
    container_name: Optional[str] = None
    port: Optional[int] = Field(default=None, ge=1024, le=65535)
    data_dir: Optional[str] = None
    env: Optional[Dict[str, str]] = None


class WebBridgeConfig(BaseModel, extra="forbid"):
    """Schema for web-bridge.yaml — configures the web search bridge container."""

    description: Optional[str] = None
    notes: Optional[List[str]] = None
    web_bridge: WebBridgeSettings

    @classmethod
    def from_yaml(cls, path: Path) -> "WebBridgeConfig":
        """Read a YAML file and validate against the model."""
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Expected a mapping in {path}, got {type(data).__name__}")
        return cls.model_validate(data)
