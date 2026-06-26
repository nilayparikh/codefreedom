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

from codefreedom.config.display import (
    format_resolved_config,
    is_secret_key,
    redact_value,
    resolve_value_source,
)
from codefreedom.config.errors import (
    ConfigError,
    CrossReferenceError,
    MergeError,
    MissingSecretError,
    ProfileError,
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
    SandboxImages,
    ToolDefinition,
)
from codefreedom.config.runtime import (
    AgentRuntimeConfig,
    CodeFreedomSettings,
    ProxySettings,
    ResolvedValue,
    apply_cf_cli_overrides,
    list_profiles,
    load_codefreedom_settings,
    load_profile_env,
    resolve_agent_runtime,
    resolve_config_value,
)

__all__ = [
    # Public API
    "load_config",
    "ResolvedConfig",
    "AgentConfig",
    "ToolConfig",
    "ConfigModel",
    # Display
    "format_resolved_config",
    "is_secret_key",
    "redact_value",
    "resolve_value_source",
    # Models
    "AgentDefinition",
    "ProfileEntry",
    "SandboxImages",
    "ToolDefinition",
    "CommonSection",
    # Runtime
    "AgentRuntimeConfig",
    "CodeFreedomSettings",
    "ProxySettings",
    "ResolvedValue",
    "resolve_agent_runtime",
    "resolve_config_value",
    "load_codefreedom_settings",
    "apply_cf_cli_overrides",
    "list_profiles",
    "load_profile_env",
    # Interpolation
    "resolve_var",
    "resolve_dict",
    "interpolate_all",
    # Errors
    "ConfigError",
    "ProfileError",
    "SchemaValidationError",
    "CrossReferenceError",
    "MergeError",
    "MissingSecretError",
    "UnresolvedReferenceError",
    # YAML utilities
    "safe_load",
    "safe_load_or_warn",
    "safe_dump",
]

from codefreedom.config.yaml_utils import safe_load, safe_load_or_warn, safe_dump  # noqa: E402
