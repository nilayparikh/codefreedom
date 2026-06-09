"""Pydantic model for web.json — Web search tool profile."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class EngineConfig(BaseModel, extra="forbid"):
    """Configuration for a single search engine."""

    url: str
    parser: Optional[str] = None


class ParserConfig(BaseModel, extra="forbid"):
    """Named parser configuration with CSS selectors."""

    result_selectors: Optional[str] = None
    link_selector: Optional[str] = None
    snippet_selectors: Optional[str] = None
    ai_selectors: Optional[List[str]] = None


class WebSettings(BaseModel, extra="forbid"):
    """Web browser container settings."""

    image: Optional[str] = None
    container_name: Optional[str] = None
    port: Optional[int] = None
    data_dir: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    search_cooldown_seconds: Optional[float] = Field(default=None, ge=0)
    search_engines: Optional[Dict[str, EngineConfig]] = None
    parser_registry: Optional[Dict[str, ParserConfig]] = None


class WebConfig(BaseModel, extra="forbid"):
    """Schema for web.json — configures the web browser container."""

    description: Optional[str] = None
    notes: Optional[List[str]] = None
    web: WebSettings

    @classmethod
    def from_json(cls, path: Path) -> "WebConfig":
        """Read a JSON file and validate against the model."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls.model_validate(data)
