"""Backward-compatible re-exports — settings now live in codefreedom.config.

.. deprecated::
    Import from ``codefreedom.config`` directly instead.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

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


@dataclass(frozen=True)
class AgentRuntimeConfig:
    """Resolved runtime configuration for an agent entrypoint."""
    agent: str
    component: str
    workspace_dir: Path
    profiles_path: Path
    base_env: dict[str, str]
    profile_env: dict[str, str]
    tools: list[str]
    sandbox_images: dict[str, str]
    settings: "CodeFreedomSettings"


class CodeFreedomSettings:
    """Runtime settings — proxy bind host/port from load_config() + CF_CLI_*."""

    proxy_bind_host: str = "127.0.0.1"
    proxy_bind_port: int = 4000

    def __init__(self) -> None:
        try:
            config = load_config()
            proxy_env = config.for_component("proxy")
            self.proxy_bind_host = proxy_env.get("LITELLM_BIND_HOST", "127.0.0.1")
            self.proxy_bind_port = int(proxy_env.get("LITELLM_PORT", "4000"))
        except ConfigError:
            pass

        # CF_CLI_* always wins (already resolved in for_component via context)
        cf_cli_host = os.environ.get("CF_CLI_LITELLM_BIND_HOST")
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
        return ProxySettings(
            bind_host=host,
            bind_port=port,
            public_base_url=f"http://{host}:{port}",
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


_AGENT_TO_COMPONENT = {
    "claude-code": "claude",
    "mimo-code": "mimo",
    "open-code": "open",
    "pi-code": "pi",
    "codex-code": "codex",
}


def _resolve_component_for_agent(agent: str) -> str:
    if agent not in _AGENT_TO_COMPONENT:
        raise ValueError(f"Unknown agent: {agent}")
    return _AGENT_TO_COMPONENT[agent]


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
    """Resolve agent runtime via the new config system."""
    from codefreedom.core.config import get_config_dir

    component = _resolve_component_for_agent(agent)
    config_dir = get_config_dir()

    try:
        config = load_config(config_dir)
    except ConfigError:
        return AgentRuntimeConfig(
            agent=agent,
            component=component,
            workspace_dir=workspace_dir,
            profiles_path=config_dir / "profiles.yaml",
            base_env=dict(os.environ),
            profile_env={},
            tools=[],
            sandbox_images={},
            settings=CodeFreedomSettings(),
        )

    if not validate_profile:
        return AgentRuntimeConfig(
            agent=agent,
            component=component,
            workspace_dir=workspace_dir,
            profiles_path=config_dir / "profiles.yaml",
            base_env=dict(os.environ),
            profile_env={},
            tools=[],
            sandbox_images={},
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
            sandbox_images={},
            sandbox_env={},
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
        component=component,
        workspace_dir=workspace_dir,
        profiles_path=config_dir / "profiles.yaml",
        base_env=dict(os.environ),
        profile_env=profile_env,
        tools=agent_cfg.tools,
        sandbox_images=agent_cfg.sandbox_images,
        settings=CodeFreedomSettings(),
    )
