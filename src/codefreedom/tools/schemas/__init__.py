"""Pydantic models for tool-specific configuration."""

from __future__ import annotations

from .chrome import ChromeConfig
from .github import GithubConfig
from .web import WebConfig
from .web_bridge import WebBridgeConfig

# Note: codebase-memory's profile schema is intentionally NOT a Pydantic
# model. The manifest is a permissive user-editable YAML file managed
# at runtime by the package in ``docker/codebase-memory/src/codebase_memory/``.
# See the v7 design notes in the docs.

__all__ = [
    "ChromeConfig",
    "GithubConfig",
    "WebConfig",
    "WebBridgeConfig",
]
