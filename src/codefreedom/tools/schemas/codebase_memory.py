"""Pydantic model for codebase_memory.yaml — Codebase Memory MCP tool profile."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator


_VALID_LOG_LEVELS = {"debug", "info", "warn", "warning", "error", "none"}


class CodebaseMemorySettings(BaseModel, extra="forbid"):
    """Codebase Memory container settings."""

    image: str
    container_name: Optional[str] = None
    port: Optional[int] = Field(default=None, ge=1024, le=65535)
    ui_port: Optional[int] = Field(default=None, ge=1024, le=65535)
    data_dir: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    bind_host: Optional[str] = None
    remote_url: Optional[str] = None
    enable_ui: Optional[bool] = None
    log_level: Optional[str] = None
    auto_index: Optional[bool] = None

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v_lower = v.lower()
        if v_lower not in _VALID_LOG_LEVELS:
            raise ValueError(
                f"log_level must be one of {sorted(_VALID_LOG_LEVELS)}, got {v!r}"
            )
        return v_lower


class CodebaseMemoryConfig(BaseModel, extra="forbid"):
    """Schema for codebase_memory.yaml — configures the Codebase Memory container."""

    description: Optional[str] = None
    notes: Optional[List[str]] = None
    codebase_memory: CodebaseMemorySettings

    @classmethod
    def from_yaml(cls, path: Path) -> "CodebaseMemoryConfig":
        """Read a YAML file and validate against the model."""
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Expected a mapping in {path}, got {type(data).__name__}")
        return cls.model_validate(data)
