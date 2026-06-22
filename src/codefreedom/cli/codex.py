"""Codex subcommand -- sandboxed or local launch with 0-click proxy config.

Auto-detects the running CodeFreedom LiteLLM proxy, generates a complete
``config.toml`` with a custom model provider, and launches Codex
(``codex``) with zero manual configuration.

Usage:
    codefreedom run agent codex-code [--sandbox] [--profile NAME] [--list-profiles] [agent-args...]
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
import os
import secrets
import shutil
import signal
import subprocess
from pathlib import Path
from codefreedom.core.config import (
    get_codefreedom_dir,
    resolve_codex_profiles_path,
)
from codefreedom.core.profiles import (
    list_profiles,
)
from codefreedom.env_loader import load_env_chain
from codefreedom.log import eprint, tag
from codefreedom.tools.registry import generate_session_id
from codefreedom.sandbox.signals import forward_signal


def register_args(parser: argparse.ArgumentParser) -> None:
    """Register Codex-specific arguments on the agent parser."""
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

DEFAULT_CODEX_IMAGE = "docker.io/nilayparikh/codefreedom:ubuntu-latest"
CODEX_CONFIG_NAME = "config.toml"
_CONTAINER_PREFIX = "codefreedom-codex-"

CODEFREEDOM_DIR = get_codefreedom_dir()

# ── Helpers ────────────────────────────────────────────────────────────────────


def find_codex_binary() -> str | None:
    """Locate the ``codex`` CLI binary on PATH."""
    return shutil.which("codex")


def _detect_proxy_url(base_env: dict[str, str]) -> str:
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


def _fetch_proxy_models(proxy_url: str, api_key: str = "") -> list[dict]:
    """Fetch the model list from the LiteLLM proxy ``/v1/models`` endpoint.

    Returns a list of model dicts (with at least an ``id`` key).
    Returns an empty list if the proxy is unreachable or returns an error.
    """
    import json as _json

    from codefreedom.core.http_client import get_json, HTTPError, HTTPStatusError

    models_url = f"{proxy_url.rstrip('/')}/v1/models"
    try:
        data = get_json(models_url, timeout=5, bearer=api_key)
        return data.get("data", [])
    except (HTTPStatusError, HTTPError, _json.JSONDecodeError):
        return []


def _generate_model_catalog(proxy_models: list[dict]) -> list[dict]:
    """Generate Codex model catalog from proxy model list."""
    catalog = []
    seen = set()

    for m in proxy_models:
        model_id = m.get("id", "")
        if not model_id or model_id in seen:
            continue

        model_id_lower = model_id.lower()

        # Skip internal LiteLLM models and provider-prefixed helpers
        if model_id_lower.startswith("azure/") or model_id_lower in (
            "gpt-3.5-turbo",
            "custom",
        ):
            continue

        seen.add(model_id)
        display_name = model_id.split("/")[-1] if "/" in model_id else model_id

        catalog.append({
            "id": model_id,
            "slug": model_id,
            "display_name": display_name,
            "description": f"{display_name} via CodeFreedom proxy",
            "default_reasoning_level": "high",
            "supported_reasoning_levels": [
                {"effort": "none", "description": "Think-Off"},
                {"effort": "low", "description": "Fast responses with lighter reasoning"},
                {"effort": "medium", "description": "Balances speed and reasoning depth"},
                {"effort": "high", "description": "Deep reasoning for complex problems"},
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
        })

    return catalog


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
        'model_context_window = 131072',
    ]

    if catalog:
        lines.append(f'model_catalog_json = "{catalog_path.as_posix()}"')

    lines.append("")
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


def _ensure_codex_sandbox_dir(profile_name: str) -> tuple[Path, Path]:
    """Create isolated sandbox directories for Codex.

    Returns (codex_home, config_path) -- the CODEX_HOME directory
    and the path to the generated ``config.toml`` config file.
    """
    profile_dir = CODEFREEDOM_DIR / "codex-code" / "sandbox" / profile_name
    profile_dir.mkdir(parents=True, exist_ok=True)

    codex_home = profile_dir / "home"
    codex_home.mkdir(parents=True, exist_ok=True)

    config_path = codex_home / CODEX_CONFIG_NAME

    return codex_home, config_path


# ── Execution ─────────────────────────────────────────────────────────────────


def run_local(
    profile_env: dict[str, str],
    codex_args: list[str],
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
    config_content, catalog_content = _generate_codex_config(proxy_url, profile_env, codex_home)
    codex_home.mkdir(parents=True, exist_ok=True)
    env["CODEX_HOME"] = str(codex_home)

    # Write config.toml
    _write_codex_config(config_content, codex_home)

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
    cmd.extend(codex_args)

    try:
        proc = subprocess.Popen(cmd, env=env)
        signal.signal(signal.SIGINT, lambda s, f: forward_signal(proc, s, f))
        signal.signal(signal.SIGTERM, lambda s, f: forward_signal(proc, s, f))
        proc.wait()
        return proc.returncode
    except FileNotFoundError:
        eprint(f"{tag('ERROR')} Codex binary not found at {codex_bin}.")
        return 1
    except KeyboardInterrupt:
        return 130


def run_docker(
    profile_env: dict[str, str],
    codex_args: list[str],
    workspace_dir: Path,
    profile_name: str,
    sandbox_images: dict[str, str] | None = None,
    run_as_me: bool = False,
    gpu_type: str | None = None,
) -> int:
    """Run ``codex`` inside an ephemeral Docker container.

    Delegates container lifecycle to the shared sandbox launcher.
    """
    from codefreedom.sandbox.launcher import run_sandbox
    from codefreedom.sandbox.terminal import terminal_size

    sandbox_images = sandbox_images or {}

    if gpu_type:
        image = sandbox_images.get(gpu_type) or f"docker.io/nilayparikh/codefreedom:{gpu_type}-latest"
        eprint(f"{tag('GPU')} Selected '{gpu_type}' sandbox image: {image}.")
    else:
        image = sandbox_images.get("default") or DEFAULT_CODEX_IMAGE

    container_name = f"{_CONTAINER_PREFIX}{secrets.token_hex(2)}"

    eprint(f"{tag('IMAGE')} Using sandbox image: {image}.")
    eprint(f"{tag('CONTAINER')} Name: {container_name}.")

    proxy_url = _detect_proxy_url(profile_env)
    eprint(f"{tag('CODEX')} Detecting proxy at {proxy_url}...")
    codex_home_dir, config_path = _ensure_codex_sandbox_dir(profile_name)
    config_content, catalog_content = _generate_codex_config(proxy_url, profile_env, codex_home_dir)

    # Write config.toml (merge with existing)
    _write_codex_config(config_content, codex_home_dir)

    # Write model catalog
    if catalog_content:
        catalog_path = codex_home_dir / "model_catalog.json"
        catalog_path.write_text(catalog_content, encoding="utf-8")
        catalog_path.chmod(0o600)
        eprint(f"{tag('CODEX')} Generated model catalog at {catalog_path}")

    env_flags: list[str] = []
    for key in sorted(profile_env.keys()):
        val = profile_env[key]
        if val is not None:
            env_flags.extend(["-e", f"{key}={val}"])

    cols, lines = terminal_size()
    env_flags.extend(["-e", f"COLUMNS={cols}", "-e", f"LINES={lines}"])

    if run_as_me and hasattr(os, "getuid"):
        host_uid = os.getuid()
        host_gid = os.getgid()
        container_home = f"/home/{Path.home().name}"
        container_user_flag = ["-u", f"{host_uid}:{host_gid}"]
        eprint(
            f"{tag('SANDBOX')} --run-as-me: uid={host_uid}({Path.home().name}) gid={host_gid}"
        )
    else:
        if run_as_me:
            eprint(f"{tag('WARN')} --run-as-me not supported on Windows; running as default user.")
        container_home = "/home/codefreedom"
        container_user_flag = []
        eprint(f"{tag('SANDBOX')} Running as default container user 'codefreedom' (uid 1000).")

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
        f"{codex_home_dir}:{container_home}/.codex",
        "-e",
        f"HOME={container_home}",
        "-e",
        f"CODEX_HOME={container_home}/.codex",
        "-e",
        "IS_SANDBOX=1",
    ]

    exec_image_cmd = (
        ["docker", "exec", "-it"]
        + container_user_flag
        + ["-e", f"HOME={container_home}"]
        + ["-e", f"CODEX_HOME={container_home}/.codex"]
        + [container_name, "codex"]
        + codex_args
    )

    exec_extra_env = [
        "-e",
        f"CODEX_HOME={container_home}/.codex",
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
            "  cf run agent codex-code --sandbox    # isolated Docker sandbox",
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
    base_env = load_env_chain(workspace_dir, component="codex")

    profile_name = getattr(args, "profile", None) or "default"
    profiles_path = resolve_codex_profiles_path()

    from codefreedom.cli.common import load_profile_env_only

    profile_env, exit_code = load_profile_env_only(
        profile_name, profiles_path, base_env, error_prefix="cf run agent codex-code config"
    )
    if exit_code != 0 and profile_name != "default":
        return 1

    if not profile_env.get("PROXY_API_KEY"):
        master_key = base_env.get("LITELLM_MASTER_KEY", "")
        if master_key:
            profile_env["PROXY_API_KEY"] = master_key

    proxy_url = _detect_proxy_url(profile_env)
    config_content, _ = _generate_codex_config(proxy_url, profile_env)

    out_path = getattr(args, "out", None)
    if out_path:
        from codefreedom.cli.common import write_output_file

        return write_output_file(config_content, out_path)

    print(config_content)
    return 0


# ── Status / Stop ─────────────────────────────────────────────────────────────


def status() -> int:
    """Show all codefreedom codex-code sandbox containers. Returns exit code."""
    from codefreedom.sandbox.launcher import sandbox_status

    return sandbox_status(_CONTAINER_PREFIX)


def stop() -> int:
    """Stop and remove all codefreedom codex-code sandbox containers. Returns exit code."""
    from codefreedom.sandbox.launcher import sandbox_stop

    return sandbox_stop(_CONTAINER_PREFIX)


# ── Main entry point ─────────────────────────────────────────────────────────


def run(args: argparse.Namespace) -> int:
    """Execute the ``codex-code`` subcommand. Returns exit code."""

    if args.list_profiles:
        from codefreedom.cli.common import display_profiles

        profiles_path = resolve_codex_profiles_path()
        profiles = list_profiles(profiles_path)
        return display_profiles(
            profiles_path, profiles, show_env_keys=False, show_tools=True
        )

    action = getattr(args, "codex_action", None)
    if action == "config":
        return cmd_config(args)

    workspace_dir = Path.cwd()
    eprint(f"{tag('ENV')} Loading configuration...")
    base_env = load_env_chain(workspace_dir, component="codex")

    profile_name = args.profile or "default"
    profiles_path = resolve_codex_profiles_path()
    mode = "sandbox" if args.sandbox else "local"

    from codefreedom.cli.common import load_profile_with_tools

    profile_env, sandbox_images, tools, exit_code = load_profile_with_tools(
        profile_name, profiles_path, base_env, mode
    )
    if exit_code != 0:
        return 1

    if not profile_env.get("PROXY_API_KEY"):
        master_key = base_env.get("LITELLM_MASTER_KEY", "")
        if master_key:
            profile_env["PROXY_API_KEY"] = master_key

    run_as_me = getattr(args, "run_as_me", False)

    gpu_type: str | None = None
    if getattr(args, "gpu_cuda", False):
        gpu_type = "cuda"
    elif getattr(args, "gpu_rocm", False):
        gpu_type = "rocm"

    session_id = generate_session_id(mode)

    from codefreedom.cli.common import acquire_and_run

    def _run(acquired_tools: list[str]) -> int:
        if acquired_tools:
            from codefreedom.launcher import _write_mcp_json

            _write_mcp_json(workspace_dir, acquired_tools)
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
                eprint(f"{tag('WARN')} --run-as-me is only valid with --sandbox; ignoring.")
            return run_local(profile_env, args.agent_args)

    return acquire_and_run(session_id, tools, profile_name, _run)
