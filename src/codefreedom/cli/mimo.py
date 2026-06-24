"""MiMoCode subcommand -- sandboxed or local launch with 0-click proxy config.

Auto-detects the running CodeFreedom LiteLLM proxy, generates a complete
``mimocode.json`` config with all proxy models, and launches MiMoCode
(``mimo``) with zero manual configuration.

Usage:
    codefreedom run agent mimo-code [--sandbox] [--profile NAME] [--list-profiles] [agent-args...]
    codefreedom run agent mimo-code [options] [-- <agent-args>]

Proxy auto-config:
    - Detects the proxy at PROXY_BASE_URL (default: http://localhost:4000)
    - Fetches model list from ``/v1/models``
    - Generates ``~/.codefreedom/mimo-code/mimocode.json`` with all models
    - Sets ``MIMOCODE_CONFIG`` env var to point at the generated config
    - MiMoCode loads all proxy models as ``codefreedom/<model-id>``
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
    resolve_mimo_profiles_path,
)
from codefreedom.core.profiles import (
    list_profiles,
)
from codefreedom.core.settings import resolve_agent_runtime
from codefreedom.log import eprint
from codefreedom.tools.registry import generate_session_id
from codefreedom.sandbox.signals import forward_signal
from codefreedom.sandbox.terminal import terminal_size


def register_args(parser: argparse.ArgumentParser) -> None:
    """Register MiMo-specific arguments on the agent parser."""
    gpu_group = parser.add_mutually_exclusive_group()
    gpu_group.add_argument(
        "--cuda",
        action="store_true",
        dest="gpu_cuda",
        help="Use CUDA sandbox image for NVIDIA GPUs (only with --sandbox)",
    )
    gpu_group.add_argument(
        "--rocm",
        action="store_true",
        dest="gpu_rocm",
        help="Use ROCm sandbox image for AMD GPUs (only with --sandbox)",
    )
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

DEFAULT_MIMO_IMAGE = "docker.io/nilayparikh/codefreedom:ubuntu-latest"
PROXY_MODELS_CACHE_FILE = "proxy-models.json"
MIMOCODE_CONFIG_NAME = "mimocode.json"
_CONTAINER_PREFIX = "codefreedom-mimo-"

CODEFREEDOM_DIR = get_codefreedom_dir()

# ── Helpers ────────────────────────────────────────────────────────────────────


def find_mimo_binary() -> Optional[str]:
    """Locate the ``mimo`` CLI binary on PATH."""
    return shutil.which("mimo")


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
                f"[MIMO] Proxy returned {exc.status_code} — is LITELLM_MASTER_KEY set "
                f"in ~/.codefreedom/.env.claude.secrets?"
            )
        return []
    except (HTTPError, json.JSONDecodeError):
        return []


def _build_provider_models(
    proxy_models: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Build a provider models dict from the proxy model list.

    Each model gets a minimal capability profile — just ``tool_call: True``
    and a display name.  Context limits and reasoning support are discovered
    by MiMoCode at runtime; the proxy handles the actual routing.
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


def _generate_mimo_config(
    proxy_url: str,
    profile_env: Dict[str, str],
) -> Dict[str, Any]:
    """Generate a complete ``mimocode.json`` config pointing at the proxy.

    1. Fetches the live model list from the proxy
    2. Falls back to an empty model list if proxy is unreachable
    3. Creates a ``codefreedom`` provider entry with all models
    4. Skips alias models unless MIMOCODE_SHOW_ALIAS_MODELS is set

    Returns the config dict ready to be serialised to JSON.
    """
    eprint(f"[MIMO] Detecting proxy at {proxy_url}...")
    api_key = profile_env.get("PROXY_API_KEY", "")
    proxy_models = _fetch_proxy_models(proxy_url, api_key=api_key)

    if proxy_models:
        provider_models = _build_provider_models(proxy_models)
        eprint(
            f"[MIMO] Proxy responded with {len(proxy_models)} model(s), "
            f"mapped {len(provider_models)} provider model(s)."
        )

        # Filter alias models unless profile explicitly enables them
        show_aliases = profile_env.get("MIMOCODE_SHOW_ALIAS_MODELS", "").lower() in (
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
                        f"[MIMO] Skipped {skipped} alias model(s)"
                        f" ({', '.join(sorted(alias_models))});"
                        " set MIMOCODE_SHOW_ALIAS_MODELS=1 to include them."
                    )
    else:
        provider_models = {}
        eprint(
            f"[MIMO] Proxy not reachable at {proxy_url}.\n"
            f"       Start the proxy (``cf run proxy start``) and restart MiMoCode\n"
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
    default_model = profile_env.get("MIMOCODE_DEFAULT_MODEL")
    if default_model:
        # Prepend "codefreedom/" prefix if not already qualified
        if "/" not in default_model:
            default_model = f"codefreedom/{default_model}"
        config["model"] = default_model
        eprint(f"[MIMO] Default model set to '{default_model}' from profile.")

    return config


def _write_mimo_config(
    config: Dict[str, Any],
    config_dir: Path,
) -> Path:
    """Write the generated ``mimocode.json`` to *config_dir*.

    Creates parent directories if they don't exist.
    Returns the path to the written config file.
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / MIMOCODE_CONFIG_NAME
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    config_path.chmod(0o600)
    eprint(f"[MIMO] Generated proxy config at {config_path}")
    return config_path


def _ensure_mimo_sandbox_dir(profile_name: str) -> Tuple[Path, Path]:
    """Create isolated sandbox directories for MiMoCode.

    Returns (mimo_data_dir, config_path) — the MIMOCODE_HOME data directory
    and the path to the generated ``mimocode.json`` config file.
    """
    profile_dir = CODEFREEDOM_DIR / "mimo-code" / "sandbox" / profile_name
    profile_dir.mkdir(parents=True, exist_ok=True)

    # Isolated MIMOCODE_HOME structure: data/config/cache/state subdirs
    mimo_home = profile_dir / "home"
    for sub in ("data", "config", "cache", "state"):
        (mimo_home / sub).mkdir(parents=True, exist_ok=True)

    config_dir = profile_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    return mimo_home, config_dir


# ── Execution ─────────────────────────────────────────────────────────────────


def run_local(
    profile_env: Dict[str, str],
    mimo_args: List[str],
) -> int:
    """Run ``mimo`` natively on the host. Returns exit code."""
    mimo_bin = find_mimo_binary()
    if not mimo_bin:
        eprint(
            "[ERROR] MiMoCode (mimo) not found on PATH.\n"
            "       Install: npm install -g @mimo-ai/cli"
        )
        return 1

    eprint("[LOCAL] Running MiMoCode natively...")

    env = {**os.environ}
    env.update(profile_env)

    # 0-click proxy config: generate mimocode.json and inject MIMOCODE_CONFIG
    proxy_url = _detect_proxy_url(profile_env)
    config = _generate_mimo_config(proxy_url, profile_env)
    config_dir = CODEFREEDOM_DIR / "mimo-code" / "config"
    config_path = _write_mimo_config(config, config_dir)
    env["MIMOCODE_CONFIG"] = str(config_path)

    cmd = [mimo_bin]
    cmd.extend(mimo_args)

    try:
        proc = subprocess.Popen(cmd, env=env)
        signal.signal(signal.SIGINT, lambda s, f: forward_signal(proc, s, f))
        signal.signal(signal.SIGTERM, lambda s, f: forward_signal(proc, s, f))
        proc.wait()
        return proc.returncode
    except FileNotFoundError:
        eprint(f"[ERROR] MiMoCode binary not found at {mimo_bin}.")
        return 1
    except KeyboardInterrupt:
        return 130


def run_docker(
    profile_env: Dict[str, str],
    mimo_args: List[str],
    workspace_dir: Path,
    profile_name: str,
    sandbox_images: Dict[str, str] | None = None,
    run_as_me: bool = False,
    gpu_type: str | None = None,
) -> int:
    """Run ``mimo`` inside an ephemeral Docker container.

    Delegates container lifecycle to the shared sandbox launcher.
    """
    from codefreedom.sandbox.launcher import run_sandbox

    sandbox_images = sandbox_images or {}

    if gpu_type:
        image = (
            sandbox_images.get(gpu_type)
            or f"docker.io/nilayparikh/codefreedom:{gpu_type}-latest"
        )
        eprint(f"[GPU] Selected '{gpu_type}' sandbox image: {image}.")
    else:
        image = sandbox_images.get("default") or DEFAULT_MIMO_IMAGE

    container_name = f"{_CONTAINER_PREFIX}{secrets.token_hex(2)}"

    eprint(f"[IMAGE] Using sandbox image: {image}.")
    eprint(f"[CONTAINER] Name: {container_name}.")

    # ── Generate proxy config first ────────────────────────────────────────────
    proxy_url = _detect_proxy_url(profile_env)
    config = _generate_mimo_config(proxy_url, profile_env)
    mimo_home_dir, config_dir = _ensure_mimo_sandbox_dir(profile_name)
    config_path = _write_mimo_config(config, config_dir)

    # ── Build env flags ───────────────────────────────────────────────────────
    env_flags: List[str] = []
    for key in sorted(profile_env.keys()):
        val = profile_env[key]
        if val is not None:
            env_flags.extend(["-e", f"{key}={val}"])

    cols, lines = terminal_size()
    env_flags.extend(["-e", f"COLUMNS={cols}", "-e", f"LINES={lines}"])

    # ── Container identity ────────────────────────────────────────────────────
    if run_as_me and hasattr(os, "getuid"):
        host_uid = os.getuid()
        host_gid = os.getgid()
        container_home = f"/home/{Path.home().name}"
        container_user_flag = ["-u", f"{host_uid}:{host_gid}"]
        eprint(
            f"[SANDBOX] --run-as-me: uid={host_uid}({Path.home().name}) gid={host_gid}"
        )
    else:
        if run_as_me:
            eprint(
                "[SANDBOX] --run-as-me not supported on Windows; running as default user."
            )
        container_home = "/home/codefreedom"
        container_user_flag = []
        eprint("[SANDBOX] Running as default container user 'codefreedom' (uid 1000).")

    # ── Docker run base options ───────────────────────────────────────────────
    base_opts = [
        "--network",
        "host",
        *container_user_flag,
        "--ipc=host",
        "-v",
        f"{workspace_dir}:/workspace",
        "-w",
        "/workspace",
        "-v",
        f"{Path.home() / '.gitconfig'}:{container_home}/.gitconfig:ro",
        "-v",
        f"{Path.home() / '.ssh'}:{container_home}/.ssh:ro",
        "-v",
        f"{mimo_home_dir}:{container_home}/.local/share/mimocode",
        "-v",
        f"{config_path}:{container_home}/.config/mimocode/mimocode.json:ro",
        "-e",
        f"HOME={container_home}",
        "-e",
        f"MIMOCODE_CONFIG={container_home}/.config/mimocode/mimocode.json",
        "-e",
        "IS_SANDBOX=1",
        "-e",
        "MIMOCODE_DISABLE_AUTOUPDATE=1",
    ]

    # ── Exec command ──────────────────────────────────────────────────────────
    exec_image_cmd = (
        ["docker", "exec", "-it"]
        + container_user_flag
        + ["-e", f"HOME={container_home}"]
        + [container_name, "mimo"]
        + mimo_args
    )

    exec_extra_env = [
        "-e",
        f"MIMOCODE_CONFIG={container_home}/.config/mimocode/mimocode.json",
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


def init_mimo() -> int:
    """Print initialization help for MiMoCode."""
    from codefreedom.cli.docker_utils import print_help_section

    print_help_section(
        "mimo init",
        [
            "MiMoCode requires no init -- 0-click proxy config is generated",
            "automatically on first launch.",
            "",
            "To install MiMoCode (mimo):",
            "  npm install -g @mimo-ai/cli",
            "",
            "To start the proxy (for model routing):",
            "  cf run proxy start",
            "",
            "To launch MiMoCode:",
            "  cf run agent mimo-code              # native mode",
            "  cf run agent mimo-code --sandbox    # isolated Docker sandbox",
        ],
        docs_url="https://github.com/XiaomiMiMo/MiMo-Code",
        include_disclaimer=False,
    )
    return 0


# ── Config subcommand ─────────────────────────────────────────────────────────


def cmd_config(args: argparse.Namespace) -> int:
    """Generate and print a proxy-resolved ``mimocode.json`` for standalone use.

    Loads the full env chain, detects the proxy, fetches model list,
    generates a complete ``mimocode.json`` and outputs it.
    """
    workspace_dir = Path.cwd()
    eprint("[ENV] Loading configuration...")
    runtime = resolve_agent_runtime(
        "mimo-code",
        workspace_dir=workspace_dir,
        profile_name=getattr(args, "profile", None) or "default",
        mode="local",
    )
    base_env = runtime.base_env

    profile_name = getattr(args, "profile", None) or "default"
    profiles_path = resolve_mimo_profiles_path()

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
    config = _generate_mimo_config(proxy_url, profile_env)

    out_path = getattr(args, "out", None)
    output = json.dumps(config, indent=2)

    if out_path:
        from codefreedom.cli.common import write_output_file

        return write_output_file(output, out_path)

    print(output)
    return 0


# ── Status / Stop ─────────────────────────────────────────────────────────────


def status() -> int:
    """Show all codefreedom run agent mimo-code sandbox containers. Returns exit code."""
    from codefreedom.sandbox.launcher import sandbox_status

    return sandbox_status(_CONTAINER_PREFIX)


def stop() -> int:
    """Stop and remove all codefreedom run agent mimo-code sandbox containers. Returns exit code."""
    from codefreedom.sandbox.launcher import sandbox_stop

    return sandbox_stop(_CONTAINER_PREFIX)


# ── Main entry point ─────────────────────────────────────────────────────────


def _update_mimocode_mcp(tools: List[str]) -> None:
    """Register MCP servers in MiMoCode config.

    Writes tool endpoints into ``~/.config/mimocode/mimocode.jsonc``
    using the ``"type": "remote"`` format required by MiMoCode/OpenCode.
    Preserves existing non-tool MCP entries.
    """
    from codefreedom.tools.registry import _MCP_TOOLS

    if not tools:
        return

    config_path = Path.home() / ".config" / "mimocode" / "mimocode.jsonc"
    if not config_path.parent.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)

    existing: Dict[str, Any] = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            eprint(f"[MIMO] Could not parse {config_path} — starting fresh.")
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
        config_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
        eprint(
            f"[MIMO] Registered MCP in {config_path}:" f" {', '.join(sorted(added))}"
        )
    else:
        eprint("[MIMO] All MCP servers already registered.")


def run(args: argparse.Namespace) -> int:
    """Execute the ``mimo`` subcommand. Returns exit code."""

    # Fast-path flags
    if args.list_profiles:
        from codefreedom.cli.common import display_profiles

        profiles_path = resolve_mimo_profiles_path()
        profiles = list_profiles(profiles_path)
        return display_profiles(
            profiles_path, profiles, show_env_keys=False, show_tools=True
        )

    # Actions
    action = getattr(args, "mimo_action", None)
    if action == "config":
        return cmd_config(args)

    # ── Load env chain ─────────────────────────────────────────────────────
    workspace_dir = Path.cwd()
    eprint("[ENV] Loading configuration...")

    # ── Load profile ───────────────────────────────────────────────────────
    profile_name = args.profile or "default"
    profiles_path = resolve_mimo_profiles_path()
    mode = "sandbox" if args.sandbox else "local"
    runtime = resolve_agent_runtime(
        "mimo-code",
        workspace_dir=workspace_dir,
        profile_name=profile_name,
        mode=mode,
    )

    from codefreedom.cli.common import load_profile_with_tools

    profile_env, sandbox_images, tools, exit_code = load_profile_with_tools(
        profile_name, profiles_path, runtime.base_env, mode
    )
    if exit_code != 0:
        return 1

    # ── Ensure proxy API key is available ──────────────────────────────
    # Safety net: re-inject from base_env in case resolve failed
    # (e.g. if load_profiles had premature interpolation — fixed now,
    # but kept as defense-in-depth).
    if not profile_env.get("PROXY_API_KEY"):
        master_key = runtime.base_env.get("LITELLM_MASTER_KEY", "")
        if master_key:
            profile_env["PROXY_API_KEY"] = master_key

    run_as_me = getattr(args, "run_as_me", False)

    # ── GPU type from --cuda / --rocm flags ────────────────────────────────
    gpu_type: str | None = None
    if getattr(args, "gpu_cuda", False):
        gpu_type = "cuda"
    elif getattr(args, "gpu_rocm", False):
        gpu_type = "rocm"

    # ── Tools: acquire if declared in profile ────────────────────────────
    session_id = generate_session_id(mode)

    from codefreedom.cli.common import acquire_and_run

    def _run(acquired_tools: list[str]) -> int:
        # Write .mcp.json so the agent discovers MCP tool endpoints
        if acquired_tools:
            from codefreedom.launcher import _write_mcp_json

            _write_mcp_json(workspace_dir, acquired_tools)
            # Also register MCP servers in mimocode.jsonc for MiMoCode
            _update_mimocode_mcp(acquired_tools)
        if args.sandbox:
            return run_docker(
                profile_env,
                args.agent_args,
                workspace_dir,
                profile_name,
                sandbox_images=sandbox_images,
                run_as_me=run_as_me,
                gpu_type=gpu_type,
            )
        else:
            if run_as_me:
                eprint("[WARN] --run-as-me is only valid with --sandbox; ignoring.")
            return run_local(profile_env, args.agent_args)

    return acquire_and_run(session_id, tools, profile_name, _run)
