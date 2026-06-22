"""Eigent subcommand -- desktop app launch with 0-click proxy config.

Auto-detects the running CodeFreedom LiteLLM proxy, generates Eigent
backend environment configuration with proxy model routing, and launches
the Eigent desktop app with zero manual configuration.

Usage:
    codefreedom run agent eigent-code [--profile NAME] [--list-profiles] [agent-args...]
    codefreedom run agent eigent-code [options] [-- <agent-args>]

Proxy auto-config:
    - Detects the proxy at PROXY_BASE_URL (default: http://localhost:4000)
    - Fetches model list from ``/v1/models``
    - Sets CAMEL framework env vars to route through the proxy:
      * OPENAI_API_KEY → proxy master key
      * OPENAI_BASE_URL → proxy URL
      * ANTHROPIC_API_KEY → proxy master key
      * ANTHROPIC_BASE_URL → proxy URL
    - Launches Eigent Electron app with proxy-routed model config
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from codefreedom.core.config import (
    get_codefreedom_dir,
    resolve_eigent_profiles_path,
)
from codefreedom.core.profiles import (
    list_profiles,
)
from codefreedom.env_loader import load_env_chain
from codefreedom.log import eprint, tag
from codefreedom.sandbox.signals import forward_signal
from codefreedom.tools.registry import generate_session_id


def register_args(parser: argparse.ArgumentParser) -> None:
    """Register Eigent-specific arguments on the agent parser."""
    parser.add_argument(
        "--eigent-dir",
        type=str,
        default=None,
        metavar="DIR",
        help="Path to Eigent installation directory (default: auto-detect)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Eigent backend only (no Electron GUI)",
    )


# ── Constants ──────────────────────────────────────────────────────────────────

CODEFREEDOM_DIR = get_codefreedom_dir()

# Eigent installation paths (standard locations)
_EIGENT_SEARCH_PATHS = [
    Path.home() / "eigent",
    Path.home() / ".eigent",
    Path("/opt/eigent"),
    Path("/usr/local/eigent"),
]


# ── Helpers ────────────────────────────────────────────────────────────────────


def find_eigent_dir(custom_dir: str | None = None) -> Path | None:
    """Locate the Eigent installation directory.

    Checks (in order):
    1. Custom directory from --eigent-dir flag
    2. EIGENT_DIR environment variable
    3. Standard installation paths
    """
    if custom_dir:
        path = Path(custom_dir)
        if path.exists():
            return path
        return None

    env_dir = os.environ.get("EIGENT_DIR")
    if env_dir:
        path = Path(env_dir)
        if path.exists():
            return path

    for search_path in _EIGENT_SEARCH_PATHS:
        if search_path.exists():
            return search_path

    return None


def find_eigent_binary(eigent_dir: Path | None = None) -> str | None:
    """Locate the Eigent binary or launcher.

    For Electron apps, this is typically the app executable or npm script.
    """
    if eigent_dir:
        # Check for packaged release (Electron app)
        for name in ["eigent", "Eigent", "Eigent.exe"]:
            app_path = eigent_dir / name
            if app_path.exists():
                return str(app_path)

        # Check for npm start script
        package_json = eigent_dir / "package.json"
        if package_json.exists():
            npm_bin = shutil.which("npm")
            if npm_bin:
                return npm_bin

    # Fall back to system-installed eigent
    for name in ["eigent", "eigent-desktop"]:
        binary = shutil.which(name)
        if binary:
            return binary

    return None


def _detect_proxy_url(base_env: Dict[str, str]) -> str:
    """Detect the proxy URL from environment or use default.

    Checks (in order):
    1. PROXY_BASE_URL in the merged env
    2. PROXY_BASE_URL in os.environ
    3. LITELLM_BASE_URL (legacy) in the merged env
    4. LITELLM_BASE_URL (legacy) in os.environ
    5. Default http://localhost:4000
    """
    return (
        base_env.get("PROXY_BASE_URL")
        or os.environ.get("PROXY_BASE_URL")
        or base_env.get("LITELLM_BASE_URL")
        or os.environ.get("LITELLM_BASE_URL")
        or "http://localhost:4000"
    )


def _fetch_proxy_models(proxy_url: str, api_key: str = "") -> List[Dict[str, Any]]:
    """Fetch the model list from the LiteLLM proxy ``/v1/models`` endpoint.

    If *api_key* is provided it is sent as a ``Bearer`` token so the
    call succeeds even when the proxy requires authentication.

    Returns a list of model dicts (with at least an ``id`` key).
    Returns an empty list if the proxy is unreachable or returns an error.
    """
    from codefreedom.core.http_client import get_json, HTTPError, HTTPStatusError

    models_url = f"{proxy_url.rstrip('/')}/v1/models"
    try:
        data = get_json(models_url, timeout=5, bearer=api_key)
        return data.get("data", [])
    except HTTPStatusError as exc:
        if exc.status_code in (401, 403):
            eprint(
                f"{tag('EIGENT')} Proxy returned {exc.status_code} — is LITELLM_MASTER_KEY set "
                f"in ~/.codefreedom/.env.eigent.secrets?"
            )
        return []
    except (HTTPError, json.JSONDecodeError):
        return []


def _build_model_summary(
    proxy_models: List[Dict[str, Any]],
) -> Dict[str, str]:
    """Build a summary of available models for logging.

    Returns a dict mapping model ID to display name.
    """
    summary: Dict[str, str] = {}
    for m in proxy_models:
        model_id = m.get("id", "")
        if not model_id:
            continue
        model_id_lower = model_id.lower()
        if model_id_lower.startswith("azure/") or model_id_lower in (
            "gpt-3.5-turbo",
            "custom",
        ):
            continue
        display_name = model_id.split("/")[-1] if "/" in model_id else model_id
        summary[model_id] = display_name
    return summary


def _generate_eigent_env(
    proxy_url: str,
    profile_env: Dict[str, str],
    eigent_dir: Path | None = None,
) -> Dict[str, str]:
    """Generate Eigent backend environment with proxy routing.

    Sets CAMEL framework environment variables to route all model
    requests through the CodeFreedom LiteLLM proxy.

    Returns the env dict ready to be passed to Eigent.
    """
    eprint(f"{tag('EIGENT')} Detecting proxy at {proxy_url}...")
    api_key = profile_env.get("PROXY_API_KEY", "")
    proxy_models = _fetch_proxy_models(proxy_url, api_key=api_key)

    if proxy_models:
        model_summary = _build_model_summary(proxy_models)
        eprint(
            f"{tag('EIGENT')} Proxy responded with {len(proxy_models)} model(s), "
            f"mapped {len(model_summary)} provider model(s)."
        )
    else:
        eprint(
            f"{tag('EIGENT')} Proxy not reachable at {proxy_url}.\n"
            f"       Start the proxy (``cf run proxy start``) and restart Eigent\n"
            f"       to load the full proxy model list."
        )

    # Build CAMEL framework env vars for proxy routing
    eigent_env: Dict[str, str] = {}

    # Backend (Python/CAMEL) - reads these
    eigent_env["OPENAI_API_KEY"] = api_key
    eigent_env["OPENAI_BASE_URL"] = f"{proxy_url.rstrip('/')}/v1"
    eigent_env["OPENAI_API_BASE"] = f"{proxy_url.rstrip('/')}/v1"

    # Anthropic provider routing through proxy
    eigent_env["ANTHROPIC_API_KEY"] = api_key
    eigent_env["ANTHROPIC_BASE_URL"] = proxy_url.rstrip('/')

    # Frontend (React/Vite) - reads these for BYOK configuration
    eigent_env["VITE_OPENAI_API_BASE"] = f"{proxy_url.rstrip('/')}/v1"
    eigent_env["VITE_OPENAI_API_KEY"] = api_key

    # Eigent-specific: disable cloud services for local-only operation
    eigent_env["VITE_USE_LOCAL_PROXY"] = "true"
    eigent_env["SERVER_URL"] = "http://localhost:3001"

    # Set default model from profile if specified
    default_model = profile_env.get("EIGENT_DEFAULT_MODEL")
    if default_model:
        eigent_env["EIGENT_DEFAULT_MODEL"] = default_model
        eprint(f"{tag('EIGENT')} Default model set to '{default_model}' from profile.")

    return eigent_env


def _write_eigent_env(
    eigent_env: Dict[str, str],
    config_dir: Path,
) -> Path:
    """Write the generated environment to a .env file for Eigent.

    Creates parent directories if they don't exist.
    Returns the path to the written .env file.
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    env_path = config_dir / ".env.codefreedom"

    lines = [
        "# CodeFreedom proxy configuration — auto-generated by cf run agent eigent-code",
        "# Do not edit manually. Regenerated on each launch.",
        "",
    ]
    for key in sorted(eigent_env.keys()):
        val = eigent_env[key]
        escaped = val.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{key}="{escaped}"')

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    env_path.chmod(0o600)
    eprint(f"{tag('EIGENT')} Generated proxy config at {env_path}")
    return env_path


def _merge_eigent_env(
    base_env: Dict[str, str],
    eigent_env: Dict[str, str],
    profile_env: Dict[str, str],
) -> Dict[str, str]:
    """Merge all env sources for Eigent launch.

    Priority (highest to lowest):
    1. eigent_env (proxy config generated by this module)
    2. profile_env (user profile settings)
    3. base_env (env chain)
    """
    merged = {**base_env}
    merged.update(profile_env)
    merged.update(eigent_env)
    return merged


# ── MCP Tool Integration ──────────────────────────────────────────────────────


def _update_eigent_mcp(tools: List[str], workspace_dir: Path) -> None:
    """Register MCP servers in Eigent's config.

    Writes tool endpoints into ``.mcp.json`` in the workspace directory
    using the standard MCP format. Eigent reads this file to discover
    available MCP servers.

    Preserves existing non-tool MCP entries.
    """
    from codefreedom.launcher import _write_mcp_json

    if not tools:
        return

    _write_mcp_json(workspace_dir, tools)


# ── Execution ─────────────────────────────────────────────────────────────────


def run_local(
    profile_env: Dict[str, str],
    eigent_args: List[str],
    eigent_dir: Path | None = None,
    headless: bool = False,
    workspace_dir: Path | None = None,
    acquired_tools: List[str] | None = None,
) -> int:
    """Run Eigent natively on the host. Returns exit code."""
    binary = find_eigent_binary(eigent_dir)
    if not binary:
        eprint(
            f"{tag('ERROR')} Eigent not found.\n"
            f"       Install: git clone https://github.com/eigent-ai/eigent.git && cd eigent && npm install\n"
            f"       Or specify path: cf r ag ec --eigent-dir /path/to/eigent"
        )
        return 1

    eprint(f"{tag('LOCAL')} Running Eigent natively...")

    # Generate proxy config
    proxy_url = _detect_proxy_url(profile_env)
    eigent_env = _generate_eigent_env(proxy_url, profile_env, eigent_dir)

    # Write .env file for Eigent backend
    config_dir = CODEFREEDOM_DIR / "eigent-code" / "config"
    _write_eigent_env(eigent_env, config_dir)

    # Register MCP tools if acquired
    if acquired_tools and workspace_dir:
        _update_eigent_mcp(acquired_tools, workspace_dir)

    # Merge environments
    env = {**os.environ}
    env.update(_merge_eigent_env({}, profile_env, eigent_env))

    # Source the generated .env file in the environment
    env_file = config_dir / ".env.codefreedom"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                env[key] = value

    # Build command
    if eigent_dir and binary == shutil.which("npm"):
        # npm start in eigent directory
        cmd = [binary, "start"]
    else:
        cmd = [binary]
        cmd.extend(eigent_args)

    # Set working directory to Eigent dir if available
    cwd = str(eigent_dir) if eigent_dir else None

    try:
        proc = subprocess.Popen(cmd, env=env, cwd=cwd)
        signal.signal(signal.SIGINT, lambda s, f: forward_signal(proc, s, f))
        signal.signal(signal.SIGTERM, lambda s, f: forward_signal(proc, s, f))
        proc.wait()
        return proc.returncode
    except FileNotFoundError:
        eprint(f"{tag('ERROR')} Eigent binary not found at {binary}.")
        return 1
    except KeyboardInterrupt:
        return 130


# ── Init command ─────────────────────────────────────────────────────────────


def init_eigent() -> int:
    """Print initialization help for Eigent."""
    from codefreedom.cli.docker_utils import print_help_section

    print_help_section(
        "eigent init",
        [
            "Eigent requires no init — 0-click proxy config is generated",
            "automatically on first launch.",
            "",
            "To install Eigent:",
            "  git clone https://github.com/eigent-ai/eigent.git",
            "  cd eigent && npm install",
            "",
            "To start the proxy (for model routing):",
            "  cf run proxy start",
            "",
            "To launch Eigent:",
            "  cf run agent eigent-code              # native mode",
            "  cf run agent eigent-code --eigent-dir /path/to/eigent",
        ],
        docs_url="https://docs.eigent.ai/",
        include_disclaimer=False,
    )
    return 0


# ── Config subcommand ─────────────────────────────────────────────────────────


def cmd_config(args: argparse.Namespace) -> int:
    """Generate and print proxy-resolved Eigent env for standalone use.

    Loads the full env chain, detects the proxy, fetches model list,
    generates the CAMEL framework env vars and outputs them.
    """
    workspace_dir = Path.cwd()
    eprint(f"{tag('ENV')} Loading configuration...")
    base_env = load_env_chain(workspace_dir, component="eigent")

    profile_name = getattr(args, "profile", None) or "default"
    profiles_path = resolve_eigent_profiles_path()

    from codefreedom.cli.common import load_profile_env_only

    profile_env, exit_code = load_profile_env_only(
        profile_name, profiles_path, base_env, error_prefix="cf run agent eigent-code config"
    )
    if exit_code != 0 and profile_name != "default":
        return 1

    # Ensure proxy API key is available
    if not profile_env.get("PROXY_API_KEY"):
        master_key = base_env.get("LITELLM_MASTER_KEY", "")
        if master_key:
            profile_env["PROXY_API_KEY"] = master_key

    proxy_url = _detect_proxy_url(profile_env)
    eigent_env = _generate_eigent_env(proxy_url, profile_env)

    out_path = getattr(args, "out", None)
    lines = [
        "# Eigent proxy configuration — generated by cf run agent eigent-code config",
        f"# Profile: {profile_name}",
        "",
    ]
    for key in sorted(eigent_env.keys()):
        val = eigent_env[key]
        escaped = val.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'export {key}="{escaped}"')

    output = "\n".join(lines) + "\n"

    if out_path:
        from codefreedom.cli.common import write_output_file
        return write_output_file(output, out_path)

    print(output)
    return 0


# ── Main entry point ─────────────────────────────────────────────────────────


def run(args: argparse.Namespace) -> int:
    """Execute the ``eigent-code`` subcommand. Returns exit code."""

    # Fast-path flags
    if args.list_profiles:
        from codefreedom.cli.common import display_profiles

        profiles_path = resolve_eigent_profiles_path()
        profiles = list_profiles(profiles_path)
        return display_profiles(
            profiles_path, profiles, show_env_keys=False, show_tools=True
        )

    # Actions
    action = getattr(args, "eigent_action", None)
    if action == "config":
        return cmd_config(args)

    # ── Load env chain ─────────────────────────────────────────────────────
    workspace_dir = Path.cwd()
    eprint(f"{tag('ENV')} Loading configuration...")
    base_env = load_env_chain(workspace_dir, component="eigent")

    # ── Load profile ───────────────────────────────────────────────────────
    profile_name = args.profile or "default"
    profiles_path = resolve_eigent_profiles_path()

    from codefreedom.cli.common import load_profile_with_tools

    profile_env, _sandbox_images, tools, exit_code = load_profile_with_tools(
        profile_name, profiles_path, base_env, "local"
    )
    if exit_code != 0:
        return 1

    # ── Ensure proxy API key is available ──────────────────────────────
    if not profile_env.get("PROXY_API_KEY"):
        master_key = base_env.get("LITELLM_MASTER_KEY", "")
        if master_key:
            profile_env["PROXY_API_KEY"] = master_key

    # ── Resolve Eigent directory ────────────────────────────────────────
    eigent_dir_str = getattr(args, "eigent_dir", None)
    eigent_dir = find_eigent_dir(eigent_dir_str)
    if eigent_dir:
        eprint(f"{tag('EIGENT')} Found Eigent at {eigent_dir}")
    else:
        eprint(f"{tag('WARN')} Eigent directory not found; will try system PATH.")

    headless = getattr(args, "headless", False)

    # ── Tools: acquire if declared in profile ────────────────────────────
    session_id = generate_session_id("local")

    from codefreedom.cli.common import acquire_and_run

    def _run(acquired_tools: List[str]) -> int:
        return run_local(
            profile_env,
            args.agent_args,
            eigent_dir=eigent_dir,
            headless=headless,
            workspace_dir=workspace_dir,
            acquired_tools=acquired_tools,
        )

    return acquire_and_run(session_id, tools, profile_name, _run)
