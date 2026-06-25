"""Configuration error types — all fatal, all actionable."""

from __future__ import annotations


class ConfigError(Exception):
    """Fatal configuration error. System cannot start."""


class MissingSecretError(ConfigError):
    """A required secret is not set in the machine environment."""


class UnresolvedReferenceError(ConfigError):
    """A ${VAR} reference could not be resolved."""


class CrossReferenceError(ConfigError):
    """A profile references a tool or agent that doesn't exist."""


class SchemaValidationError(ConfigError):
    """profiles.yaml or override.yaml failed schema validation."""


class MergeError(ConfigError):
    """Failed to merge configuration layers."""


class ProfileError(ConfigError):
    """Raised when a profile cannot be loaded or is invalid."""
