"""Pydantic model for github.json — GitHub MCP Server tool profile."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class GithubSettings(BaseModel, extra="forbid"):
    """GitHub MCP Server container settings."""

    image: str
    container_name: Optional[str] = None
    port: Optional[int] = Field(default=None, ge=1024, le=65535)
    data_dir: Optional[str] = None
    env: Optional[Dict[str, str]] = None


class GithubConfig(BaseModel, extra="forbid"):
    """Schema for github.json — configures the GitHub MCP Server container."""

    description: Optional[str] = None
    notes: Optional[List[str]] = None
    github: GithubSettings

    @classmethod
    def from_json(cls, path: Path) -> "GithubConfig":
        """Read a JSON file and validate against the model."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls.model_validate(data)
