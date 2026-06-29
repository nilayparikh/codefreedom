"""Codex subcommand -- local launch with 0-click proxy config.

Auto-detects the running CodeFreedom LiteLLM proxy, generates a complete
``config.toml`` with a custom model provider, and launches Codex
(``codex``) with zero manual configuration.

Usage:
    codefreedom run agent codex-code [--profile NAME] [--list-profiles] [agent-args...]
    codefreedom run agent codex-code [options] [-- <agent-args>]

Proxy auto-config:
    - Detects the proxy at PROXY_BASE_URL (default: http://localhost:4000)
    - Generates ``~/.codefreedom/codex-code/config/config.toml`` with proxy provider
    - Sets ``CODEX_HOME`` env var to point at the generated config directory
    - Custom models must be selected via ``codex -m <model_name>`` (the /model
      picker only shows built-in OpenAI models)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
from pathlib import Path
from codefreedom.config.runtime import list_profiles, resolve_agent_runtime
from codefreedom.core.config import (
    get_codefreedom_dir,
    resolve_codex_profiles_path,
)
from codefreedom.log import eprint, tag
from codefreedom.tools.registry import generate_session_id


def register_args(parser: argparse.ArgumentParser) -> None:
    """Register Codex-specific arguments on the agent parser."""
    pass


# ── Constants ──────────────────────────────────────────────────────────────────

CODEX_CONFIG_NAME = "config.toml"

CODEFREEDOM_DIR = get_codefreedom_dir()

# ── Helpers ────────────────────────────────────────────────────────────────────


def find_codex_binary() -> str | None:
    """Locate the ``codex`` CLI binary on PATH."""
    return shutil.which("codex")


# Backward-compat shim: tests import ``cli.codex._detect_proxy_url`` directly.
# Implementation lives in :mod:`codefreedom.core.agent_runtime`; this alias
# removes the per-call function-body indirection that the previous wrapper had.
from codefreedom.core.agent_runtime import detect_proxy_url as _detect_proxy_url  # noqa: E402


def _fetch_proxy_models(proxy_url: str, api_key: str = "") -> list[dict]:
    """Fetch the model list from the LiteLLM proxy ``/v1/models`` endpoint.

    Thin wrapper over :func:`codefreedom.core.agent_runtime.fetch_proxy_models`.
    """
    from codefreedom.core.agent_runtime import fetch_proxy_models

    return fetch_proxy_models(proxy_url, api_key=api_key)


def _generate_model_catalog(proxy_models: list[dict]) -> list[dict]:
    """Generate Codex model catalog from proxy model list.

    Filters out all alias models (Anthropic + OpenAI/Codex aliases).
    """
    _ALIAS_MODELS = {
        # Anthropic aliases
        "fable",
        "opus",
        "sonnet",
        "haiku",
        "custom",
        # OpenAI/Codex aliases
        "gpt-5.5",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.3-codex",
        "gpt-5.2",
    }

    catalog = []
    seen = set()

    for m in proxy_models:
        model_id = m.get("id", "")
        if not model_id or model_id in seen:
            continue

        model_id_lower = model_id.lower()

        # Skip internal LiteLLM models, provider-prefixed helpers, and aliases
        if model_id_lower.startswith("azure/") or model_id_lower in (
            "gpt-3.5-turbo",
            "custom",
            *_ALIAS_MODELS,
        ):
            continue

        seen.add(model_id)
        display_name = model_id.split("/")[-1] if "/" in model_id else model_id

        catalog.append(
            {
                "id": model_id,
                "slug": model_id,
                "display_name": display_name,
                "description": f"{display_name} via CodeFreedom proxy",
                "default_reasoning_level": "high",
                "supported_reasoning_levels": [
                    {"effort": "none", "description": "Think-Off"},
                    {
                        "effort": "low",
                        "description": "Fast responses with lighter reasoning",
                    },
                    {
                        "effort": "medium",
                        "description": "Balances speed and reasoning depth",
                    },
                    {
                        "effort": "high",
                        "description": "Deep reasoning for complex problems",
                    },
                ],
                "shell_type": "shell_command",
                "visibility": "list",
                "supported_in_api": True,
                "priority": 0,
                "base_instructions": f"You are Codex, a coding agent based on {display_name}. You and the user share the same workspace and collaborate to achieve the user's goals.",
                "supports_reasoning_summaries": True,
                "default_reasoning_summary": "none",
                "support_verbosity": False,
                "truncation_policy": {"mode": "bytes", "limit": 10000},
                "supports_parallel_tool_calls": True,
                "experimental_supported_tools": [],
                "input_modalities": ["text"],
            }
        )

    return catalog


def _inject_default_model(
    codex_args: list[str], profile_env: dict[str, str]
) -> list[str]:
    """Inject -m <model> into codex_args if not already present.

    Codex CLI requires the -m flag for custom providers (the /model picker
    only shows built-in OpenAI models). This ensures the default model from
    the profile is passed automatically.
    """
    has_model_flag = any(a in ("-m", "--model") for a in codex_args)
    if has_model_flag:
        return codex_args

    default_model = profile_env.get("CODEX_DEFAULT_MODEL", "")
    if not default_model:
        return codex_args

    return ["-m", default_model, *codex_args]


def _update_codex_mcp(tools: list[str], codex_home: Path) -> None:
    """Register MCP servers in codex config.toml.

    Writes tool endpoints into ``config.toml`` using the TOML format
    required by Codex CLI. Preserves existing non-tool MCP entries.
    """
    import tomlkit

    from codefreedom.tools.registry import _MCP_TOOLS

    if not tools:
        return

    config_path = codex_home / CODEX_CONFIG_NAME
    if not config_path.exists():
        return

    try:
        existing = tomlkit.loads(config_path.read_text(encoding="utf-8"))
    except (tomlkit.exceptions.TOMLKitError, OSError):
        eprint(f"{tag('CODEX')} Could not parse {config_path} — skipping MCP update.")
        return

    existing.setdefault("mcp_servers", tomlkit.table())
    before_keys = set(existing["mcp_servers"].keys())

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
        server_table = tomlkit.table()
        server_table.add("url", url)
        existing["mcp_servers"][tool.mcp_server_name] = server_table

    after_keys = set(existing["mcp_servers"].keys())
    added = after_keys - before_keys

    if added:
        config_path.write_text(tomlkit.dumps(existing), encoding="utf-8")
        eprint(
            f"{tag('CODEX')} Registered MCP in {config_path}:"
            f" {', '.join(sorted(added))}"
        )
    else:
        eprint(f"{tag('CODEX')} All MCP servers already registered.")


def _generate_codex_config(
    proxy_url: str,
    profile_env: dict[str, str],
    codex_home: Path | None = None,
) -> tuple[str, str]:
    """Generate codex config.toml and model_catalog.json content pointing at the proxy.

    Returns (config_content, catalog_content).
    """
    import json as _json

    api_key = profile_env.get("PROXY_API_KEY", "")
    default_model = profile_env.get("CODEX_DEFAULT_MODEL", "gpt-5.5")

    # Fetch models from proxy
    eprint(f"{tag('CODEX')} Fetching models from proxy...")
    proxy_models = _fetch_proxy_models(proxy_url, api_key=api_key)
    catalog = _generate_model_catalog(proxy_models)

    if catalog:
        eprint(f"{tag('CODEX')} Found {len(catalog)} model(s) from proxy.")

    # Build config.toml — model_catalog_json MUST be at root level
    effective_home = codex_home or (CODEFREEDOM_DIR / "codex-code" / "home")
    catalog_path = effective_home / "model_catalog.json"

    lines = [
        "# Auto-generated by CodeFreedom -- do not edit manually",
        "",
        f'model = "{default_model}"',
        'model_provider = "codefreedom"',
        'model_reasoning_effort = "medium"',
        "model_context_window = 131072",
        f'model_catalog_json = "{catalog_path.as_posix()}"',
        "",
    ]
    lines.append("[model_providers.codefreedom]")
    lines.append('name = "CodeFreedom Proxy"')
    lines.append(f'base_url = "{proxy_url.rstrip("/")}/v1"')
    lines.append('wire_api = "responses"')

    if api_key:
        lines.append('env_key = "OPENAI_API_KEY"')

    lines.append("")

    # Wrap catalog in {"models": [...]} format
    catalog_content = _json.dumps({"models": catalog}, indent=2) if catalog else ""

    return "\n".join(lines), catalog_content


def _write_codex_config(
    config_content: str,
    config_dir: Path,
) -> Path:
    """Write the generated ``config.toml`` to *config_dir*, merging with existing.

    Only replaces CodeFreedom-managed keys and sections. Preserves
    user-added sections (projects, tui, windows, etc.) that Codex adds at runtime.
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / CODEX_CONFIG_NAME

    if config_path.exists():
        try:
            existing = config_path.read_text(encoding="utf-8")
            merged = _merge_codex_config(existing, config_content)
            config_path.write_text(merged, encoding="utf-8")
            eprint(f"{tag('CODEX')} Merged proxy config at {config_path}")
        except Exception:
            config_path.write_text(config_content, encoding="utf-8")
            eprint(f"{tag('CODEX')} Regenerated proxy config at {config_path}")
    else:
        config_path.write_text(config_content, encoding="utf-8")
        eprint(f"{tag('CODEX')} Generated proxy config at {config_path}")

    config_path.chmod(0o600)
    return config_path


def _merge_codex_config(existing: str, new: str) -> str:
    """Merge CodeFreedom config keys into existing config, preserving user sections.

    Replaces:
    - Top-level keys: model, model_provider, model_reasoning_effort,
      model_context_window, model_catalog_json
    - Section: [model_providers.codefreedom]

    Preserves everything else (projects, tui, windows, etc.)
    """
    import re

    # Extract the new [model_providers.codefreedom] section
    new_section_match = re.search(
        r"(\[model_providers\.codefreedom\].*?)(?=\n\[|\Z)", new, re.DOTALL
    )
    new_section = new_section_match.group(1).strip() if new_section_match else ""

    # Extract top-level keys from new config
    new_keys: dict[str, str] = {}
    for line in new.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("["):
            if "=" in stripped:
                key = stripped.split("=")[0].strip()
                new_keys[key] = stripped

    result = existing

    # Replace top-level keys (model, model_provider, etc.)
    for key, new_line in new_keys.items():
        pattern = re.compile(rf"^{re.escape(key)}\s*=.*$", re.MULTILINE)
        if pattern.search(result):
            result = pattern.sub(new_line, result)
        else:
            # Key doesn't exist, add it at the top after comments
            result = new_line + "\n" + result

    # Replace [model_providers.codefreedom] section
    section_pattern = re.compile(
        r"\[model_providers\.codefreedom\].*?(?=\n\[|\Z)", re.DOTALL
    )
    if section_pattern.search(result):
        result = section_pattern.sub(new_section, result)
    elif new_section:
        result = result.rstrip() + "\n\n" + new_section + "\n"

    return result


# ── Execution ─────────────────────────────────────────────────────────────────


def run_local(
    profile_env: dict[str, str],
    codex_args: list[str],
    acquired_tools: list[str] | None = None,
) -> int:
    """Run ``codex`` natively on the host. Returns exit code."""
    codex_bin = find_codex_binary()
    if not codex_bin:
        eprint(
            f"{tag('ERROR')} Codex (codex) not found on PATH.\n"
            "       Install: npm install -g @openai/codex"
        )
        return 1

    eprint(f"{tag('LOCAL')} Running Codex natively...")

    env = {**os.environ}
    env.update(profile_env)

    proxy_url = _detect_proxy_url(profile_env)
    eprint(f"{tag('CODEX')} Detecting proxy at {proxy_url}...")

    codex_home = CODEFREEDOM_DIR / "codex-code" / "home"
    config_content, catalog_content = _generate_codex_config(
        proxy_url, profile_env, codex_home
    )
    codex_home.mkdir(parents=True, exist_ok=True)
    env["CODEX_HOME"] = str(codex_home)

    # Write config.toml
    _write_codex_config(config_content, codex_home)

    # Register MCP servers in config.toml
    if acquired_tools:
        _update_codex_mcp(acquired_tools, codex_home)

    # Write model catalog
    if catalog_content:
        catalog_path = codex_home / "model_catalog.json"
        catalog_path.write_text(catalog_content, encoding="utf-8")
        catalog_path.chmod(0o600)
        eprint(f"{tag('CODEX')} Generated model catalog at {catalog_path}")

    # Inject OPENAI_API_KEY for proxy authentication
    proxy_api_key = profile_env.get("PROXY_API_KEY", "")
    if proxy_api_key:
        env["OPENAI_API_KEY"] = proxy_api_key

    eprint(f"{tag('CODEX')} Tip: Use 'codex -m <model>' to select a custom model.")
    eprint(f"{tag('CODEX')} Example: codex -m MiMo-V2.5")

    cmd = [codex_bin]
    cmd.extend(_inject_default_model(codex_args, profile_env))

    try:
        proc = subprocess.Popen(cmd, env=env)
        signal.signal(signal.SIGINT, lambda s, f: proc.send_signal(s) if proc and proc.poll() is None else None)
        signal.signal(signal.SIGTERM, lambda s, f: proc.send_signal(s) if proc and proc.poll() is None else None)
        proc.wait()
        return proc.returncode
    except FileNotFoundError:
        eprint(f"{tag('ERROR')} Codex binary not found at {codex_bin}.")
        return 1
    except KeyboardInterrupt:
        return 130


# ── Init command ─────────────────────────────────────────────────────────────


def init_codex() -> int:
    """Print initialization help for Codex."""
    from codefreedom.cli.docker_utils import print_help_section

    print_help_section(
        "codex init",
        [
            "Codex requires no init -- 0-click proxy config is generated",
            "automatically on first launch.",
            "",
            "To install Codex:",
            "  npm install -g @openai/codex",
            "",
            "To start the proxy (for model routing):",
            "  cf run proxy start",
            "",
            "To launch Codex:",
            "  cf run agent codex-code              # native mode",
        ],
        docs_url="https://developers.openai.com/codex",
        include_disclaimer=False,
    )
    return 0


# ── Config subcommand ─────────────────────────────────────────────────────────


def cmd_config(args: argparse.Namespace) -> int:
    """Generate and print a proxy-resolved ``config.toml`` for standalone use."""
    workspace_dir = Path.cwd()
    eprint(f"{tag('ENV')} Loading configuration...")
    runtime = resolve_agent_runtime(
        "codex-code",
        workspace_dir=workspace_dir,
        profile_name=getattr(args, "profile", None) or "default",
        mode="local",
    )
    base_env = runtime.base_env

    profile_name = getattr(args, "profile", None) or "default"
    profiles_path = resolve_codex_profiles_path()

    from codefreedom.cli.common import load_profile_env_only

    profile_env, exit_code = load_profile_env_only(
        profile_name,
        profiles_path,
        base_env,
        error_prefix="cf run agent codex-code config",
        agent="codex-code",
    )
    if exit_code != 0 and profile_name != "default":
        return 1

    if not profile_env.get("PROXY_API_KEY"):
        from codefreedom.core.agent_runtime import resolve_proxy_api_key

        api_key = resolve_proxy_api_key(base_env)
        if api_key:
            profile_env["PROXY_API_KEY"] = api_key

    proxy_url = _detect_proxy_url(profile_env)
    config_content, _ = _generate_codex_config(proxy_url, profile_env)

    out_path = getattr(args, "out", None)
    if out_path:
        from codefreedom.cli.common import write_output_file

        return write_output_file(config_content, out_path)

    print(config_content)
    return 0


# ── Main entry point ─────────────────────────────────────────────────────────


def run(args: argparse.Namespace) -> int:
    """Execute the ``codex-code`` subcommand. Returns exit code."""

    if args.list_profiles:
        from codefreedom.cli.common import display_profiles

        profiles_path = resolve_codex_profiles_path()
        profiles = list_profiles(profiles_path, agent="codex-code")
        return display_profiles(
            profiles_path, profiles, show_env_keys=False, show_tools=True
        )

    action = getattr(args, "codex_action", None)
    if action == "config":
        return cmd_config(args)

    workspace_dir = Path.cwd()
    eprint(f"{tag('ENV')} Loading configuration...")

    profile_name = args.profile or "default"
    profiles_path = resolve_codex_profiles_path()
    mode = "local"
    runtime = resolve_agent_runtime(
        "codex-code",
        workspace_dir=workspace_dir,
        profile_name=profile_name,
        mode=mode,
    )

    from codefreedom.cli.common import load_profile_with_tools

    profile_env, tools, exit_code = load_profile_with_tools(
        profile_name, profiles_path, runtime.base_env, mode,
        agent="codex-code",
    )
    if exit_code != 0:
        return 1

    if not profile_env.get("PROXY_API_KEY"):
        from codefreedom.core.agent_runtime import resolve_proxy_api_key

        api_key = resolve_proxy_api_key(runtime.base_env)
        if api_key:
            profile_env["PROXY_API_KEY"] = api_key

    session_id = generate_session_id(mode)

    from codefreedom.cli.common import acquire_and_run

    def _run(acquired_tools: list[str]) -> int:
        if acquired_tools:
            from codefreedom.launcher import _write_mcp_json

            _write_mcp_json(workspace_dir, acquired_tools)
        return run_local(
            profile_env, args.agent_args, acquired_tools=acquired_tools
        )

    return acquire_and_run(session_id, tools, profile_name, _run)
