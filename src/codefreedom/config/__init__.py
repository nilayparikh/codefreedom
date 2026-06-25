"""CodeFreedom Configuration Module.

Single entry point for all configuration loading. All components
(agents, tools, proxy, doctor) import from here instead of loading
YAML files independently.

Usage::

    from codefreedom.config import load_config

    config = load_config()
    agent_cfg = config.for_agent("claude-code", profile="default")
    tool_cfg = config.for_tool("chrome")
    proxy_env = config.for_component("proxy")
"""

from __future__ import annotations

from codefreedom.config.errors import (
    ConfigError,
    CrossReferenceError,
    MergeError,
    MissingSecretError,
    SchemaValidationError,
    UnresolvedReferenceError,
)
from codefreedom.config.interpolation import interpolate_all, resolve_dict, resolve_var
from codefreedom.config.loader import (
    AgentConfig,
    ConfigModel,
    ResolvedConfig,
    ToolConfig,
    load_config,
)
from codefreedom.config.models import (
    AgentDefinition,
    CommonSection,
    ProfileEntry,
    ToolDefinition,
)

__all__ = [
    # Public API
    "load_config",
    "ResolvedConfig",
    "AgentConfig",
    "ToolConfig",
    "ConfigModel",
    # Models
    "AgentDefinition",
    "ProfileEntry",
    "ToolDefinition",
    "CommonSection",
    # Interpolation
    "resolve_var",
    "resolve_dict",
    "interpolate_all",
    # Errors
    "ConfigError",
    "SchemaValidationError",
    "CrossReferenceError",
    "MergeError",
    "MissingSecretError",
    "UnresolvedReferenceError",
]
