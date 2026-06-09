"""Pydantic model for chrome.json — Chrome browser tool profile."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


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
    """Schema for chrome.json — configures the Chrome browser container."""

    description: Optional[str] = None
    notes: Optional[List[str]] = None
    chrome: ChromeSettings

    @classmethod
    def from_json(cls, path: Path) -> "ChromeConfig":
        """Read a JSON file and validate against the model."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls.model_validate(data)
