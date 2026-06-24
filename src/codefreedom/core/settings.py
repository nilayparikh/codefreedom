"""Typed runtime settings and provenance helpers for CodeFreedom."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from codefreedom.core.config import (
    resolve_codex_profiles_path,
    resolve_mimo_profiles_path,
    resolve_opencode_profiles_path,
    resolve_pi_profiles_path,
    resolve_profiles_path,
)
from codefreedom.core.profiles import (
    get_profile_sandbox_images,
    get_profile_tools,
    load_profile_env,
    load_profiles,
)
from codefreedom.env_loader import get_env, load_dotenv


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
    settings: CodeFreedomSettings


class CodeFreedomSettings(BaseSettings):
    """Phase A runtime settings seam for central configuration."""

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    proxy_bind_host: str = Field(default="127.0.0.1", alias="LITELLM_BIND_HOST")
    proxy_bind_port: int = Field(default=4000, alias="LITELLM_PORT")

    @property
    def proxy(self) -> ProxySettings:
        """Return canonical proxy settings."""
        host = self.proxy_bind_host
        port = self.proxy_bind_port
        return ProxySettings(
            bind_host=host,
            bind_port=port,
            public_base_url=f"http://{host}:{port}",
        )

    def proxy_provenance(self) -> dict[str, ResolvedValue]:
        """Return provenance for canonical proxy fields."""
        host = _resolved_env_value("LITELLM_BIND_HOST", self.proxy.bind_host)
        port = _resolved_env_value("LITELLM_PORT", str(self.proxy.bind_port))
        public_url = ResolvedValue(
            self.proxy.public_base_url,
            "derived:proxy.bind_host+proxy.bind_port",
        )
        return {
            "bind_host": host,
            "bind_port": port,
            "public_base_url": public_url,
        }


def _resolved_env_value(env_name: str, default: str) -> ResolvedValue:
    """Return a resolved env-backed value with its source."""
    if env_name in os.environ:
        return ResolvedValue(os.environ[env_name], f"env:{env_name}")
    return ResolvedValue(default, f"default:{env_name}")


def _resolve_component_for_agent(agent: str) -> str:
    """Map a canonical agent name to its env component."""
    mapping = {
        "claude-code": "claude",
        "mimo-code": "mimo",
        "open-code": "open",
        "pi-code": "pi",
        "codex-code": "codex",
    }
    if agent not in mapping:
        raise ValueError(f"Unknown agent: {agent}")
    return mapping[agent]


def _resolve_profiles_path_for_agent(agent: str) -> Path:
    """Resolve the profile file path for a canonical agent name."""
    mapping = {
        "claude-code": resolve_profiles_path,
        "mimo-code": resolve_mimo_profiles_path,
        "open-code": resolve_opencode_profiles_path,
        "pi-code": resolve_pi_profiles_path,
        "codex-code": resolve_codex_profiles_path,
    }
    if agent not in mapping:
        raise ValueError(f"Unknown agent: {agent}")
    return mapping[agent]()


def resolve_config_value(
    name: str,
    *,
    workspace_dir: Path,
    component: str | None = None,
    extra_env_files: list[Path] | None = None,
) -> tuple[str | None, str | None]:
    """Resolve a config or secret value through the common module.

    Priority:
      1. ``CF_CLI_<NAME>`` in machine env
      2. ``NAME`` in machine env
      3. ``.env.user`` in CodeFreedom home
      4. extra env files passed by caller
      5. canonical merged env chain via get_env()
    """
    cf_cli = f"CF_CLI_{name}"
    if cf_cli in os.environ and os.environ[cf_cli]:
        return os.environ[cf_cli], "CF_CLI_* override"

    if name in os.environ and os.environ[name]:
        return os.environ[name], "machine env"

    user_env_path = (
        Path(os.environ.get("CODEFREEDOM_HOME", "")).expanduser() / ".env.user"
    )
    if os.environ.get("CODEFREEDOM_HOME"):
        if user_env_path.exists():
            user_env = load_dotenv(user_env_path)
            value = user_env.get(name)
            if value and value != "CHANGE_ME":
                return value, ".env.user"

    if extra_env_files:
        for env_file in extra_env_files:
            if env_file.exists():
                parsed = load_dotenv(env_file)
                value = parsed.get(name)
                if value and value != "CHANGE_ME":
                    return value, env_file.name

    merged = get_env(workspace_dir, component=component, verbose=False)
    value = merged.get(name)
    if value:
        return value, "merged env chain"

    return None, None


def load_codefreedom_settings(workspace_dir: Path) -> CodeFreedomSettings:
    """Load central runtime settings for the current workspace."""
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
    """Resolve all common config and secret inputs for an agent runtime."""
    component = _resolve_component_for_agent(agent)
    profiles_path = _resolve_profiles_path_for_agent(agent)
    settings = load_codefreedom_settings(workspace_dir)
    base_env = get_env(workspace_dir, component=component, verbose=False)
    profiles = load_profiles(profiles_path)
    if validate_profile:
        profile_env = load_profile_env(
            profile_name,
            profiles_path,
            base_env,
            mode=mode,
            profiles=profiles,
        )
        if not profile_env.get("PROXY_API_KEY"):
            master_key = base_env.get("LITELLM_MASTER_KEY", "")
            if master_key:
                profile_env["PROXY_API_KEY"] = master_key

        tools = get_profile_tools(profile_name, profiles_path, profiles=profiles)
        sandbox_images = get_profile_sandbox_images(
            profile_name, profiles_path, profiles=profiles
        )
    else:
        profile_env = {}
        tools = []
        sandbox_images = {}

    return AgentRuntimeConfig(
        agent=agent,
        component=component,
        workspace_dir=workspace_dir,
        profiles_path=profiles_path,
        base_env=base_env,
        profile_env=profile_env,
        tools=tools,
        sandbox_images=sandbox_images,
        settings=settings,
    )
