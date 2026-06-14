"""OpenCode subcommand -- sandboxed or local launch with 0-click proxy config.

Auto-detects the running CodeFreedom LiteLLM proxy, generates a complete
``opencode.json`` config with all proxy models, and launches OpenCode
(``opencode``) with zero manual configuration.

Usage:
    codefreedom run agent open-code [--sandbox] [--profile NAME] [--list-profiles] [agent-args...]
    codefreedom run agent open-code [options] [-- <agent-args>]

Proxy auto-config:
    - Detects the proxy at LITELLM_BASE_URL (default: http://localhost:4000)
    - Fetches model list from ``/v1/models``
    - Generates ``~/.codefreedom/opencode/config/opencode.json`` with all models
    - Sets ``OPENCODE_CONFIG`` env var to point at the generated config
    - OpenCode loads all proxy models as ``codefreedom/<model-id>``
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from codefreedom.core.config import (
    get_codefreedom_dir,
    resolve_opencode_profiles_path,
)
from codefreedom.core.profiles import (
    list_profiles,
)
from codefreedom.env_loader import load_env_chain
from codefreedom.log import eprint
from codefreedom.tools.registry import generate_session_id
from codefreedom.sandbox.signals import forward_signal
from codefreedom.sandbox.terminal import terminal_size


def register_args(parser: argparse.ArgumentParser) -> None:
    """Register OpenCode-specific arguments on the agent parser."""
    parser.add_argument(
        "--sandbox",
        action="store_true",
        help="Run inside a sandboxed Docker container (default: native)",
    )
    parser.add_argument(
        "--run-as-me",
        action="store_true",
        help="Run sandbox container as host user (uid/gid match). Only valid with --sandbox.",
    )


# ── Constants ──────────────────────────────────────────────────────────────────

DEFAULT_OPENCODE_IMAGE = "docker.io/nilayparikh/codefreedom:opencode"
PROXY_MODELS_CACHE_FILE = "proxy-models.json"
OPENCODE_CONFIG_NAME = "opencode.json"
_CONTAINER_PREFIX = "codefreedom-opencode-"

CODEFREEDOM_DIR = get_codefreedom_dir()

# ── Helpers ────────────────────────────────────────────────────────────────────


def find_opencode_binary() -> Optional[str]:
    """Locate the ``opencode`` CLI binary on PATH."""
    return shutil.which("opencode")


def _detect_proxy_url(base_env: Dict[str, str]) -> str:
    """Detect the proxy URL from environment or use default.

    Checks (in order):
    1. LITELLM_BASE_URL in the merged env
    2. LITELLM_BASE_URL in os.environ
    3. Default http://localhost:4000
    """
    return (
        base_env.get("LITELLM_BASE_URL")
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
    from codefreedom.core.http_client import get_json

    import httpx

    models_url = f"{proxy_url.rstrip('/')}/v1/models"
    try:
        data = get_json(models_url, timeout=5, bearer=api_key)
        return data.get("data", [])
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            eprint(
                f"[OPENCODE] Proxy returned {exc.response.status_code} — is LITELLM_MASTER_KEY set "
                f"in ~/.codefreedom/.env.opencode.secrets?"
            )
        return []
    except (httpx.HTTPError, json.JSONDecodeError):
        return []


def _build_provider_models(
    proxy_models: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Build a provider models dict from the proxy model list.

    Each model gets a minimal capability profile — just ``tool_call: True``
    and a display name.  Context limits and reasoning support are discovered
    by OpenCode at runtime; the proxy handles the actual routing.
    """
    provider_models: Dict[str, Dict[str, Any]] = {}

    for m in proxy_models:
        model_id = m.get("id", "")
        if not model_id:
            continue

        model_id_lower = model_id.lower()

        # Skip internal LiteLLM models and provider-prefixed helpers
        if model_id_lower.startswith("azure/") or model_id_lower in (
            "gpt-3.5-turbo",
            "custom",
        ):
            continue

        display_name = model_id.split("/")[-1] if "/" in model_id else model_id

        provider_models[model_id] = {
            "name": display_name,
            "tool_call": True,
        }

    return provider_models


def _generate_opencode_config(
    proxy_url: str,
    profile_env: Dict[str, str],
) -> Dict[str, Any]:
    """Generate a complete ``opencode.json`` config pointing at the proxy.

    1. Fetches the live model list from the proxy
    2. Falls back to an empty model list if proxy is unreachable
    3. Creates a ``codefreedom`` provider entry with all models

    Returns the config dict ready to be serialised to JSON.
    """
    eprint(f"[OPENCODE] Detecting proxy at {proxy_url}...")
    api_key = profile_env.get("PROXY_API_KEY", "")
    proxy_models = _fetch_proxy_models(proxy_url, api_key=api_key)

    if proxy_models:
        provider_models = _build_provider_models(proxy_models)
        eprint(
            f"[OPENCODE] Proxy responded with {len(proxy_models)} model(s), "
            f"mapped {len(provider_models)} provider model(s)."
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
        eprint(f"[OPENCODE] Default model set to '{default_model}' from profile.")

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
    eprint(f"[OPENCODE] Generated proxy config at {config_path}")
    return config_path


def _ensure_opencode_sandbox_dir(profile_name: str) -> Tuple[Path, Path]:
    """Create isolated sandbox directories for OpenCode.

    Returns (opencode_data_dir, config_path) — the OPENCODE_HOME data directory
    and the path to the generated ``opencode.json`` config file.
    """
    profile_dir = CODEFREEDOM_DIR / "opencode" / "sandbox" / profile_name
    profile_dir.mkdir(parents=True, exist_ok=True)

    # Isolated OPENCODE_HOME structure: data/config/cache/state subdirs
    opencode_home = profile_dir / "home"
    for sub in ("data", "config", "cache", "state"):
        (opencode_home / sub).mkdir(parents=True, exist_ok=True)

    config_dir = profile_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    return opencode_home, config_dir


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

    eprint("[LOCAL] Running OpenCode natively...")

    env = {**os.environ}
    env.update(profile_env)

    # 0-click proxy config: generate opencode.json and inject OPENCODE_CONFIG
    proxy_url = _detect_proxy_url(profile_env)
    config = _generate_opencode_config(proxy_url, profile_env)
    config_dir = CODEFREEDOM_DIR / "opencode" / "config"
    config_path = _write_opencode_config(config, config_dir)
    env["OPENCODE_CONFIG"] = str(config_path)

    cmd = [opencode_bin]
    cmd.extend(opencode_args)

    try:
        proc = subprocess.Popen(cmd, env=env)
        signal.signal(signal.SIGINT, lambda s, f: forward_signal(proc, s, f))
        signal.signal(signal.SIGTERM, lambda s, f: forward_signal(proc, s, f))
        proc.wait()
        return proc.returncode
    except FileNotFoundError:
        eprint(f"[ERROR] OpenCode binary not found at {opencode_bin}.")
        return 1
    except KeyboardInterrupt:
        return 130


def run_docker(
    profile_env: Dict[str, str],
    opencode_args: List[str],
    workspace_dir: Path,
    profile_name: str,
    sandbox_images: Dict[str, str] | None = None,
    run_as_me: bool = False,
) -> int:
    """Run ``opencode`` inside an ephemeral Docker container.

    Delegates container lifecycle to the shared sandbox launcher.
    """
    from codefreedom.sandbox.launcher import run_sandbox

    sandbox_images = sandbox_images or {}
    image = sandbox_images.get("default") or DEFAULT_OPENCODE_IMAGE

    container_name = f"{_CONTAINER_PREFIX}{secrets.token_hex(2)}"

    eprint(f"[IMAGE] Using sandbox image: {image}.")
    eprint(f"[CONTAINER] Name: {container_name}.")

    # ── Generate proxy config first ────────────────────────────────────────────
    proxy_url = _detect_proxy_url(profile_env)
    config = _generate_opencode_config(proxy_url, profile_env)
    opencode_home_dir, config_dir = _ensure_opencode_sandbox_dir(profile_name)
    config_path = _write_opencode_config(config, config_dir)

    # ── Build env flags ───────────────────────────────────────────────────────
    env_flags: List[str] = []
    for key in sorted(profile_env.keys()):
        val = profile_env[key]
        if val is not None:
            env_flags.extend(["-e", f"{key}={val}"])

    cols, lines = terminal_size()
    env_flags.extend(["-e", f"COLUMNS={cols}", "-e", f"LINES={lines}"])

    # ── Container identity ────────────────────────────────────────────────────
    host_uid = os.getuid()
    host_gid = os.getgid()
    if run_as_me:
        container_home = f"/home/{Path.home().name}"
        container_user_flag = ["-u", f"{host_uid}:{host_gid}"]
        eprint(f"[SANDBOX] --run-as-me: uid={host_uid}({Path.home().name}) gid={host_gid}")
    else:
        container_home = "/home/codefreedom"
        container_user_flag = []
        eprint("[SANDBOX] Running as default container user 'codefreedom' (uid 1000).")

    # ── Docker run base options ───────────────────────────────────────────────
    base_opts = [
        "--network", "host",
        *container_user_flag,
        "--ipc=host",
        "-v", f"{workspace_dir}:/workspace",
        "-w", "/workspace",
        "-v", f"{Path.home() / '.gitconfig'}:{container_home}/.gitconfig:ro",
        "-v", f"{Path.home() / '.ssh'}:{container_home}/.ssh:ro",
        "-v", f"{opencode_home_dir}:{container_home}/.local/share/opencode",
        "-v", f"{config_path}:{container_home}/.config/opencode/opencode.json:ro",
        "-e", f"HOME={container_home}",
        "-e", f"OPENCODE_CONFIG={container_home}/.config/opencode/opencode.json",
        "-e", "IS_SANDBOX=1",
        "-e", "OPENCODE_DISABLE_AUTOUPDATE=1",
    ]

    # ── Exec command ──────────────────────────────────────────────────────────
    exec_image_cmd = (
        ["docker", "exec", "-it"]
        + container_user_flag
        + ["-e", f"HOME={container_home}"]
        + [container_name, "opencode"]
        + opencode_args
    )

    exec_extra_env = [
        "-e",
        f"OPENCODE_CONFIG={container_home}/.config/opencode/opencode.json",
    ]

    return run_sandbox(
        image=image,
        container_name=container_name,
        base_opts=base_opts,
        env_flags=env_flags,
        exec_image_cmd=exec_image_cmd,
        exec_extra_env=exec_extra_env,
    )


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
            "  cf run agent open-code --sandbox    # isolated Docker sandbox",
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
    eprint("[ENV] Loading configuration...")
    base_env = load_env_chain(workspace_dir, component="claude")

    profile_name = getattr(args, "profile", None) or "default"
    profiles_path = resolve_opencode_profiles_path()

    from codefreedom.cli.common import load_profile_env_only

    profile_env, exit_code = load_profile_env_only(
        profile_name, profiles_path, base_env, error_prefix="cf run proxy start"
    )
    if exit_code != 0 and profile_name != "default":
        return 1
    # For default profile, continue with empty profile_env

    # ── Ensure proxy API key is available ──────────────────────────────
    if not profile_env.get("PROXY_API_KEY"):
        master_key = base_env.get("LITELLM_MASTER_KEY", "")
        if master_key:
            profile_env["PROXY_API_KEY"] = master_key

    proxy_url = _detect_proxy_url(profile_env)
    config = _generate_opencode_config(proxy_url, profile_env)

    out_path = getattr(args, "out", None)
    output = json.dumps(config, indent=2)

    if out_path:
        from codefreedom.cli.common import write_output_file

        return write_output_file(output, out_path)

    print(output)
    return 0


# ── Status / Stop ─────────────────────────────────────────────────────────────


def status() -> int:
    """Show all codefreedom run agent open-code sandbox containers. Returns exit code."""
    from codefreedom.sandbox.launcher import sandbox_status

    return sandbox_status(_CONTAINER_PREFIX)


def stop() -> int:
    """Stop and remove all codefreedom run agent open-code sandbox containers. Returns exit code."""
    from codefreedom.sandbox.launcher import sandbox_stop

    return sandbox_stop(_CONTAINER_PREFIX)


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
            eprint(f"[OPENCODE] Could not parse {config_path} — starting fresh.")
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

        url = f"http://127.0.0.1:{port}{path}"
        existing["mcp"][tool.mcp_server_name] = {
            "type": "remote",
            "url": url,
            "enabled": True,
        }

    after_keys = set(existing["mcp"].keys())
    added = after_keys - before_keys

    if added:
        config_path.write_text(
            json.dumps(existing, indent=2) + "\n", encoding="utf-8"
        )
        eprint(
            f"[OPENCODE] Registered MCP in {config_path}:"
            f" {', '.join(sorted(added))}"
        )
    else:
        eprint("[OPENCODE] All MCP servers already registered.")


# ── Main entry point ─────────────────────────────────────────────────────────


def run(args: argparse.Namespace) -> int:
    """Execute the ``opencode`` subcommand. Returns exit code."""

    # Fast-path flags
    if args.list_profiles:
        from codefreedom.cli.common import display_profiles

        profiles_path = resolve_opencode_profiles_path()
        profiles = list_profiles(profiles_path)
        return display_profiles(
            profiles_path, profiles, show_env_keys=False, show_tools=True
        )

    # Actions
    action = getattr(args, "opencode_action", None)
    if action == "config":
        return cmd_config(args)

    # ── Load env chain ─────────────────────────────────────────────────────
    workspace_dir = Path.cwd()
    eprint("[ENV] Loading configuration...")
    base_env = load_env_chain(workspace_dir, component="claude")

    # ── Load profile ───────────────────────────────────────────────────────
    profile_name = args.profile or "default"
    profiles_path = resolve_opencode_profiles_path()
    mode = "sandbox" if args.sandbox else "local"

    from codefreedom.cli.common import load_profile_with_tools

    profile_env, sandbox_images, tools, exit_code = load_profile_with_tools(
        profile_name, profiles_path, base_env, mode
    )
    if exit_code != 0:
        return 1

    # ── Ensure proxy API key is available ──────────────────────────────
    # Safety net: re-inject from base_env in case resolve failed
    if not profile_env.get("PROXY_API_KEY"):
        master_key = base_env.get("LITELLM_MASTER_KEY", "")
        if master_key:
            profile_env["PROXY_API_KEY"] = master_key

    run_as_me = getattr(args, "run_as_me", False)

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
        if args.sandbox:
            return run_docker(
                profile_env,
                args.agent_args,
                workspace_dir,
                profile_name,
                sandbox_images=sandbox_images,
                run_as_me=run_as_me,
            )
        else:
            if run_as_me:
                eprint("[WARN] --run-as-me is only valid with --sandbox; ignoring.")
            return run_local(profile_env, args.agent_args)

    return acquire_and_run(session_id, tools, profile_name, _run)
