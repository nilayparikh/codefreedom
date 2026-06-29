"""OpenCode subcommand -- local launch with 0-click proxy config.

Auto-detects the running CodeFreedom LiteLLM proxy, generates a complete
``opencode.json`` config with all proxy models, and launches OpenCode
(``opencode``) with zero manual configuration.

Usage:
    codefreedom run agent open-code [--profile NAME] [--list-profiles] [agent-args...]
    codefreedom run agent open-code [options] [-- <agent-args>]

Proxy auto-config:
    - Detects the proxy at PROXY_BASE_URL (default: http://localhost:4000)
    - Fetches model list from ``/v1/models``
    - Generates ``~/.codefreedom/open-code/config/opencode.json`` with all models
    - Sets ``OPENCODE_CONFIG`` env var to point at the generated config
    - OpenCode loads all proxy models as ``codefreedom/<model-id>``
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
from pathlib import Path

from typing import Any, Dict, List, Optional

from codefreedom.config.runtime import list_profiles, resolve_agent_runtime
from codefreedom.core.config import (
    get_codefreedom_dir,
    resolve_opencode_profiles_path,
)
from codefreedom.log import eprint, tag
from codefreedom.tools.registry import generate_session_id


def register_args(parser: argparse.ArgumentParser) -> None:
    """Register OpenCode-specific arguments on the agent parser."""
    pass


# ── Constants ──────────────────────────────────────────────────────────────────

PROXY_MODELS_CACHE_FILE = "proxy-models.json"
OPENCODE_CONFIG_NAME = "opencode.json"

CODEFREEDOM_DIR = get_codefreedom_dir()

# ── Helpers ────────────────────────────────────────────────────────────────────


def find_opencode_binary() -> Optional[str]:
    """Locate the ``opencode`` CLI binary on PATH."""
    return shutil.which("opencode")


# Backward-compat shim: tests import ``cli.opencode._detect_proxy_url`` directly.
# Implementation lives in :mod:`codefreedom.core.agent_runtime`; this alias
# removes the per-call function-body indirection that the previous wrapper had.
from codefreedom.core.agent_runtime import detect_proxy_url as _detect_proxy_url  # noqa: E402


def _fetch_proxy_models(proxy_url: str, api_key: str = "") -> List[Dict[str, Any]]:
    """Fetch the model list from the LiteLLM proxy ``/v1/models`` endpoint.

    Thin wrapper over :func:`codefreedom.core.agent_runtime.fetch_proxy_models`.
    """
    from codefreedom.core.agent_runtime import fetch_proxy_models

    return fetch_proxy_models(
        proxy_url,
        api_key=api_key,
        label="OPENCODE",
        secrets_hint="~/.codefreedom/.env.opencode.secrets",
    )


def _build_provider_models(
    proxy_models: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Build a provider models dict from the proxy model list.

    Thin wrapper over :func:`codefreedom.core.agent_runtime.build_provider_models`.
    """
    from codefreedom.core.agent_runtime import build_provider_models

    return build_provider_models(proxy_models)


def _generate_opencode_config(
    proxy_url: str,
    profile_env: Dict[str, str],
) -> Dict[str, Any]:
    """Generate a complete ``opencode.json`` config pointing at the proxy.

    1. Fetches the live model list from the proxy
    2. Falls back to an empty model list if proxy is unreachable
    3. Creates a ``codefreedom`` provider entry with all models
    4. Skips alias models unless OPENCODE_SHOW_ALIAS_MODELS is set

    Returns the config dict ready to be serialised to JSON.
    """
    eprint(f"{tag('OPENCODE')} Detecting proxy at {proxy_url}...")
    api_key = profile_env.get("PROXY_API_KEY", "")
    proxy_models = _fetch_proxy_models(proxy_url, api_key=api_key)

    if proxy_models:
        provider_models = _build_provider_models(proxy_models)
        eprint(
            f"[OPENCODE] Proxy responded with {len(proxy_models)} model(s), "
            f"mapped {len(provider_models)} provider model(s)."
        )

        # Filter alias models unless profile explicitly enables them
        show_aliases = profile_env.get("OPENCODE_SHOW_ALIAS_MODELS", "").lower() in (
            "1",
            "true",
            "yes",
        )
        if not show_aliases:
            from codefreedom.agents.vscode.proxy_models import _load_alias_models

            alias_models = _load_alias_models()
            if alias_models:
                before = len(provider_models)
                provider_models = {
                    k: v for k, v in provider_models.items() if k not in alias_models
                }
                skipped = before - len(provider_models)
                if skipped:
                    eprint(
                        f"[OPENCODE] Skipped {skipped} alias model(s)"
                        f" ({', '.join(sorted(alias_models))});"
                        " set OPENCODE_SHOW_ALIAS_MODELS=1 to include them."
                    )
    else:
        provider_models = {}
        eprint(
            f"[OPENCODE] Proxy not reachable at {proxy_url}.\n"
            f"       Start the proxy (``cf run proxy start``) and restart OpenCode\n"
            f"       to load the full proxy model list."
        )

    config: Dict[str, Any] = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            "codefreedom": {
                "name": "CodeFreedom Proxy",
                "npm": "@ai-sdk/openai-compatible",
                "api": f"{proxy_url.rstrip('/')}/v1",
                "env": [],
                "models": provider_models,
                "options": {
                    "apiKey": api_key,
                },
            },
        },
    }

    # Set default model from profile env var if specified
    default_model = profile_env.get("OPENCODE_DEFAULT_MODEL")
    if default_model:
        # Prepend "codefreedom/" prefix if not already qualified
        if "/" not in default_model:
            default_model = f"codefreedom/{default_model}"
        config["model"] = default_model
        eprint(f"{tag('OPENCODE')} Default model set to '{default_model}' from profile.")

    return config


def _write_opencode_config(
    config: Dict[str, Any],
    config_dir: Path,
) -> Path:
    """Write the generated ``opencode.json`` to *config_dir*.

    Creates parent directories if they don't exist.
    Returns the path to the written config file.
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / OPENCODE_CONFIG_NAME
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    config_path.chmod(0o600)
    eprint(f"{tag('OPENCODE')} Generated proxy config at {config_path}")
    return config_path


# ── Execution ─────────────────────────────────────────────────────────────────


def run_local(
    profile_env: Dict[str, str],
    opencode_args: List[str],
) -> int:
    """Run ``opencode`` natively on the host. Returns exit code."""
    opencode_bin = find_opencode_binary()
    if not opencode_bin:
        eprint(
            "[ERROR] OpenCode (opencode) not found on PATH.\n"
            "       Install: curl -fsSL https://opencode.ai/install | bash"
        )
        return 1

    eprint(f"{tag('LOCAL')} Running OpenCode natively...")

    env = {**os.environ}
    env.update(profile_env)

    # 0-click proxy config: generate opencode.json and inject OPENCODE_CONFIG
    proxy_url = _detect_proxy_url(profile_env)
    config = _generate_opencode_config(proxy_url, profile_env)
    config_dir = CODEFREEDOM_DIR / "open-code" / "config"
    config_path = _write_opencode_config(config, config_dir)
    env["OPENCODE_CONFIG"] = str(config_path)

    cmd = [opencode_bin]
    cmd.extend(opencode_args)

    try:
        proc = subprocess.Popen(cmd, env=env)
        signal.signal(signal.SIGINT, lambda s, f: proc.send_signal(s) if proc and proc.poll() is None else None)
        signal.signal(signal.SIGTERM, lambda s, f: proc.send_signal(s) if proc and proc.poll() is None else None)
        proc.wait()
        return proc.returncode
    except FileNotFoundError:
        eprint(f"{tag('ERROR')} OpenCode binary not found at {opencode_bin}.")
        return 1
    except KeyboardInterrupt:
        return 130


# ── Init command ─────────────────────────────────────────────────────────────


def init_opencode() -> int:
    """Print initialization help for OpenCode."""
    from codefreedom.cli.docker_utils import print_help_section

    print_help_section(
        "opencode init",
        [
            "OpenCode requires no init -- 0-click proxy config is generated",
            "automatically on first launch.",
            "",
            "To install OpenCode:",
            "  curl -fsSL https://opencode.ai/install | bash",
            "",
            "To start the proxy (for model routing):",
            "  cf run proxy start",
            "",
            "To launch OpenCode:",
            "  cf run agent open-code              # native mode",
        ],
        docs_url="https://opencode.ai/docs/",
        include_disclaimer=False,
    )
    return 0


# ── Config subcommand ─────────────────────────────────────────────────────────


def cmd_config(args: argparse.Namespace) -> int:
    """Generate and print a proxy-resolved ``opencode.json`` for standalone use.

    Loads the full env chain, detects the proxy, fetches model list,
    generates a complete ``opencode.json`` and outputs it.
    """
    workspace_dir = Path.cwd()
    eprint(f"{tag('ENV')} Loading configuration...")
    runtime = resolve_agent_runtime(
        "open-code",
        workspace_dir=workspace_dir,
        profile_name=getattr(args, "profile", None) or "default",
        mode="local",
    )
    base_env = runtime.base_env

    profile_name = getattr(args, "profile", None) or "default"
    profiles_path = resolve_opencode_profiles_path()

    from codefreedom.cli.common import load_profile_env_only

    profile_env, exit_code = load_profile_env_only(
        profile_name, profiles_path, base_env, error_prefix="cf run proxy start",
        agent="open-code",
    )
    if exit_code != 0 and profile_name != "default":
        return 1
    # For default profile, continue with empty profile_env

    # ── Ensure proxy API key is available ──────────────────────────────
    if not profile_env.get("PROXY_API_KEY"):
        from codefreedom.core.agent_runtime import resolve_proxy_api_key

        api_key = resolve_proxy_api_key(base_env)
        if api_key:
            profile_env["PROXY_API_KEY"] = api_key

    proxy_url = _detect_proxy_url(profile_env)
    config = _generate_opencode_config(proxy_url, profile_env)

    out_path = getattr(args, "out", None)
    output = json.dumps(config, indent=2)

    if out_path:
        from codefreedom.cli.common import write_output_file

        return write_output_file(output, out_path)

    print(output)
    return 0


def _update_opencode_mcp(tools: List[str]) -> None:
    """Register MCP servers in OpenCode config.

    Writes tool endpoints into ``~/.config/opencode/opencode.json``
    using the ``"type": "remote"`` format required by OpenCode/MiMoCode.
    Preserves existing non-tool MCP entries.
    """
    from codefreedom.tools.registry import _MCP_TOOLS

    if not tools:
        return

    config_path = Path.home() / ".config" / "opencode" / "opencode.json"
    if not config_path.parent.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)

    existing: Dict[str, Any] = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            eprint(f"{tag('OPENCODE')} Could not parse {config_path} — starting fresh.")
            existing = {}

    existing.setdefault("mcp", {})
    before_keys = set(existing["mcp"].keys())

    for tool_name in tools:
        if tool_name not in _MCP_TOOLS:
            continue

        tool = _MCP_TOOLS[tool_name]
        try:
            port, path = tool.mcp_endpoint
        except (FileNotFoundError, json.JSONDecodeError):
            continue

        if not path.startswith("/"):
            path = "/" + path

        from codefreedom.core.urls import build_endpoint_url

        url = build_endpoint_url(port, path)
        existing["mcp"][tool.mcp_server_name] = {
            "type": "remote",
            "url": url,
            "enabled": True,
        }

    after_keys = set(existing["mcp"].keys())
    added = after_keys - before_keys

    if added:
        config_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
        eprint(
            f"[OPENCODE] Registered MCP in {config_path}:"
            f" {', '.join(sorted(added))}"
        )
    else:
        eprint(f"{tag('OPENCODE')} All MCP servers already registered.")


# ── Main entry point ─────────────────────────────────────────────────────────


def run(args: argparse.Namespace) -> int:
    """Execute the ``opencode`` subcommand. Returns exit code."""

    # Fast-path flags
    if args.list_profiles:
        from codefreedom.cli.common import display_profiles

        profiles_path = resolve_opencode_profiles_path()
        profiles = list_profiles(profiles_path, agent="open-code")
        return display_profiles(
            profiles_path, profiles, show_env_keys=False, show_tools=True
        )

    # Actions
    action = getattr(args, "opencode_action", None)
    if action == "config":
        return cmd_config(args)

    # ── Load env chain ─────────────────────────────────────────────────────
    workspace_dir = Path.cwd()
    eprint(f"{tag('ENV')} Loading configuration...")

    # ── Load profile ───────────────────────────────────────────────────────
    profile_name = args.profile or "default"
    profiles_path = resolve_opencode_profiles_path()
    mode = "local"
    runtime = resolve_agent_runtime(
        "open-code",
        workspace_dir=workspace_dir,
        profile_name=profile_name,
        mode=mode,
    )

    from codefreedom.cli.common import load_profile_with_tools

    profile_env, tools, exit_code = load_profile_with_tools(
        profile_name, profiles_path, runtime.base_env, mode,
        agent="open-code",
    )
    if exit_code != 0:
        return 1

    # ── Ensure proxy API key is available ──────────────────────────────
    # Safety net: re-inject from base_env in case resolve failed
    if not profile_env.get("PROXY_API_KEY"):
        from codefreedom.core.agent_runtime import resolve_proxy_api_key

        api_key = resolve_proxy_api_key(runtime.base_env)
        if api_key:
            profile_env["PROXY_API_KEY"] = api_key

    # ── Tools: acquire if declared in profile ────────────────────────────
    session_id = generate_session_id(mode)

    from codefreedom.cli.common import acquire_and_run

    def _run(acquired_tools: list[str]) -> int:
        # Write .mcp.json so the agent discovers MCP tool endpoints
        if acquired_tools:
            from codefreedom.launcher import _write_mcp_json

            _write_mcp_json(workspace_dir, acquired_tools)
            # Also register MCP servers in opencode config for OpenCode
            _update_opencode_mcp(acquired_tools)
        return run_local(profile_env, args.agent_args)

    return acquire_and_run(session_id, tools, profile_name, _run)
