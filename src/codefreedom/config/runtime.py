"""Agent runtime resolution — config loading for CLI entrypoints.

Migrated from ``core/settings.py`` (deprecated module).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from codefreedom.config import ConfigError, load_config
from codefreedom.config.loader import AgentConfig


@dataclass(frozen=True)
class ResolvedValue:
    """A resolved value together with its provenance."""
    value: str
    source: str


class ProxySettings(BaseModel):
    """Canonical proxy runtime settings."""
    bind_host: str
    bind_port: int
    public_base_url: str
    remote_url: str | None = None


@dataclass(frozen=True)
class AgentRuntimeConfig:
    """Resolved runtime configuration for an agent entrypoint."""
    agent: str
    workspace_dir: Path
    profiles_path: Path
    base_env: dict[str, str]
    profile_env: dict[str, str]
    tools: list[str]
    settings: CodeFreedomSettings
    schema_error: str = ""


class CodeFreedomSettings:
    """Runtime settings — proxy bind host/port from load_config() + CF_CLI_*."""

    proxy_bind_host: str = "0.0.0.0"
    proxy_bind_port: int = 4000
    proxy_remote_url: str | None = None

    def __init__(self) -> None:
        from codefreedom.log import eprint, tag

        try:
            config = load_config()
            proxy_env = config.for_component("proxy")
            self.proxy_bind_host = proxy_env.get("LITELLM_BIND_HOST", "0.0.0.0")
            self.proxy_bind_port = int(proxy_env.get("LITELLM_PORT", "4000"))
            self.proxy_remote_url = proxy_env.get("PROXY_BASE_URL") or None
        except ConfigError as exc:
            eprint(f"{tag('CONFIG')} Failed to load config: {exc}")

        cf_cli_host = os.environ.get("CF_CLI_LITELLM_BIND_HOST") or os.environ.get("CF_CLI_BIND_ADDRESS")
        if cf_cli_host:
            self.proxy_bind_host = cf_cli_host
        cf_cli_port = os.environ.get("CF_CLI_LITELLM_PORT")
        if cf_cli_port:
            try:
                self.proxy_bind_port = int(cf_cli_port)
            except (ValueError, TypeError):
                pass

    @property
    def proxy(self) -> ProxySettings:
        host = self.proxy_bind_host
        port = self.proxy_bind_port
        public_base_url = self.proxy_remote_url or f"http://{host}:{port}"
        return ProxySettings(
            bind_host=host,
            bind_port=port,
            public_base_url=public_base_url,
            remote_url=self.proxy_remote_url,
        )

    def proxy_provenance(self) -> dict[str, ResolvedValue]:
        host = _resolved_env_value("LITELLM_BIND_HOST", self.proxy.bind_host)
        port = _resolved_env_value("LITELLM_PORT", str(self.proxy.bind_port))
        public_url = ResolvedValue(
            self.proxy.public_base_url,
            "derived:proxy.bind_host+proxy.bind_port",
        )
        return {"bind_host": host, "bind_port": port, "public_base_url": public_url}


def _resolved_env_value(env_name: str, default: str) -> ResolvedValue:
    cf_cli = f"CF_CLI_{env_name}"
    if cf_cli in os.environ:
        return ResolvedValue(os.environ[cf_cli], f"CF_CLI_*:{env_name}")
    if env_name in os.environ:
        return ResolvedValue(os.environ[env_name], f"env:{env_name}")
    return ResolvedValue(default, f"default:{env_name}")


def resolve_config_value(
    name: str,
    *,
    workspace_dir: Path | None = None,
    component: str | None = None,
    extra_env_files: list[Path] | None = None,
) -> tuple[str | None, str | None]:
    """Resolve a config/secret value from machine env only."""
    cf_cli = f"CF_CLI_{name}"
    if cf_cli in os.environ and os.environ[cf_cli]:
        return os.environ[cf_cli], "CF_CLI_* override"
    if name in os.environ and os.environ[name]:
        return os.environ[name], "machine env"
    return None, None


def load_codefreedom_settings(workspace_dir: Path) -> CodeFreedomSettings:
    _ = workspace_dir
    return CodeFreedomSettings()


def resolve_agent_runtime(
    agent: str,
    *,
    workspace_dir: Path,
    profile_name: str = "default",
    mode: str = "local",
    validate_profile: bool = True,
) -> AgentRuntimeConfig:
    """Resolve agent runtime via the config system."""
    from codefreedom.core.config import get_config_dir

    config_dir = get_config_dir()

    try:
        config = load_config(config_dir)
    except ConfigError as exc:
        from codefreedom.log import eprint, tag

        eprint(f"{tag('CONFIG')} Failed to load configuration: {exc}")
        eprint("   Run `cf doctor config` to diagnose. Agent will start with defaults only.")
        return AgentRuntimeConfig(
            agent=agent,
            workspace_dir=workspace_dir,
            profiles_path=config_dir / "profiles.yaml",
            base_env=dict(os.environ),
            profile_env={},
            tools=[],
            settings=CodeFreedomSettings(),
            schema_error=str(exc),
        )

    if not validate_profile:
        return AgentRuntimeConfig(
            agent=agent,
            workspace_dir=workspace_dir,
            profiles_path=config_dir / "profiles.yaml",
            base_env=dict(os.environ),
            profile_env={},
            tools=[],
            settings=CodeFreedomSettings(),
        )

    try:
        agent_cfg = config.for_agent(agent, profile=profile_name, mode=mode)
    except ConfigError:
        agent_cfg = AgentConfig(
            agent=agent,
            profile_name=profile_name,
            env={},
            tools=[],
        )

    profile_env = dict(agent_cfg.env)
    if not profile_env.get("PROXY_API_KEY"):
        master_key = os.environ.get("LITELLM_MASTER_KEY") or os.environ.get(
            "CF_CLI_LITELLM_MASTER_KEY", ""
        )
        if master_key:
            profile_env["PROXY_API_KEY"] = master_key

    return AgentRuntimeConfig(
        agent=agent,
        workspace_dir=workspace_dir,
        profiles_path=config_dir / "profiles.yaml",
        base_env=dict(os.environ),
        profile_env=profile_env,
        tools=agent_cfg.tools,
        settings=CodeFreedomSettings(),
    )


def apply_cf_cli_overrides(env: dict[str, str]) -> dict[str, str]:
    """Apply ``CF_CLI_*`` machine env vars as final overrides."""
    for key, val in os.environ.items():
        if key.startswith("CF_CLI_"):
            real_key = key[len("CF_CLI_"):]
            env[real_key] = val
    return env


def list_profiles(
    profiles_path: Path, agent: str | None = None
) -> list[dict[str, Any]]:
    """List available profiles with metadata.

    Args:
        profiles_path: Path to the profiles.yaml file.
        agent: Optional agent name to filter by.

    Returns:
        List of profile dicts with name, description, env_keys, tools, etc.
    """
    try:
        config = load_config(profiles_path.parent)
    except ConfigError:
        return []

    result = []
    for agent_name, agent_def in config.agents.items():
        if agent and agent_name != agent:
            continue
        for profile_name in agent_def.profiles:
            resolved = agent_def.resolve_profile(profile_name)
            result.append({
                "name": profile_name,
                "description": resolved.description or "No description",
                "env_keys": list(resolved.env.keys()),
                "tools": resolved.tools or [],
                "standalone": profile_name in ("default", "bare"),
            })
    return result


def load_profile_env(
    profile_name: str,
    profiles_path: Path,
) -> dict[str, str]:
    """Load profile env (backward compat wrapper).

    Args:
        profile_name: Profile name to load.
        profiles_path: Path to profiles.yaml.

    Returns:
        Resolved profile environment dict.

    Raises:
        ProfileError: If loading fails.
    """
    from codefreedom.config.errors import ProfileError

    try:
        config = load_config(profiles_path.parent)
        agent_name = _detect_agent(config, profile_name)
        agent_cfg = config.for_agent(agent_name, profile=profile_name)
        return agent_cfg.env
    except ConfigError as e:
        raise ProfileError(str(e)) from e


def _detect_agent(config, profile_name: str) -> str:
    """Find the first agent that has the given profile."""
    for agent_name, agent_def in config.agents.items():
        if profile_name in agent_def.profiles:
            return agent_name
    return "claude-code"
