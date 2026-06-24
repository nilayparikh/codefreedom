"""Pydantic model for recipe.yaml — defines a CodeFreedom configuration recipe."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator


class FileEntry(BaseModel, extra="forbid"):
    """A file to copy from the recipe into ~/.codefreedom/."""

    path: str
    target: Optional[str] = None
    merge: Optional[str] = Field(
        default=None, pattern=r"^(deepdiff|env|auto|overwrite)$"
    )
    split_by_key: Optional[str] = Field(
        default=None,
        description="Key to split file into multiple target files",
    )
    copy_dir: Optional[bool] = Field(
        default=None,
        description="Copy entire directory recursively instead of single file",
    )


class SecretEntry(BaseModel, extra="forbid"):
    """A required secret environment variable."""

    var: str
    prompt: Optional[str] = None
    hint: Optional[str] = None
    default: Optional[str] = None
    env: Optional[str] = Field(
        default=None,
        description="Interpolation format for use in profiles/config",
    )


class ConfigEntry(BaseModel, extra="forbid"):
    """An optional config environment variable with a sensible default."""

    var: str
    default: Optional[str] = None
    prompt: Optional[str] = None
    hint: Optional[str] = None
    env: Optional[str] = Field(
        default=None,
        description="Interpolation format for use in profiles/config",
    )


class DirEntry(BaseModel, extra="forbid"):
    """A directory to create in ~/.codefreedom/ (mountable volume host path)."""

    path: str
    _target: Optional[str] = None  # resolved at runtime


class GeneratedArtifact(BaseModel, extra="forbid"):
    """An artifact to generate from a recipe (e.g., setup scripts, env templates)."""

    kind: str
    target: str
    source_recipe: Optional[str] = None


class RecipeConfig(BaseModel, extra="forbid"):
    """Schema for recipe.yaml — defines a CodeFreedom configuration recipe."""

    name: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    description: Optional[str] = None
    version: Optional[int] = Field(default=None, ge=1)
    extends: Optional[str] = Field(default=None, pattern=r"^[a-zA-Z0-9_-]+$")
    vars: Optional[str] = Field(default=None, description="Path to recipe.vars.yaml file")
    files: List[FileEntry]
    dirs: Optional[List[str]] = None
    required_secrets: Optional[List[SecretEntry]] = None
    config_vars: Optional[List[ConfigEntry]] = None
    optional_config: Optional[List[ConfigEntry]] = None
    tools_optional: Optional[List[str]] = None
    advice: Optional[str] = None
    common_blocks: Optional[dict] = None
    generated_artifacts: Optional[List[GeneratedArtifact]] = None
    profile_presets: Optional[dict] = None

    @field_validator("tools_optional")
    @classmethod
    def _validate_tools(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is not None:
            allowed = {"chrome", "web", "github", "web-bridge"}
            for t in v:
                if t not in allowed:
                    raise ValueError(
                        f"tools_optional item must be one of {allowed}, got {t!r}"
                    )
        return v

    @classmethod
    def from_yaml(cls, path: Path) -> "RecipeConfig":
        """Read a YAML file and validate against the model."""
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Expected a mapping in {path}, got {type(data).__name__}")
        return cls.model_validate(data)
