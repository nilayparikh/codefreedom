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


def _parse_model_aliases(raw: str) -> dict[str, str]:
    """Parse CODEX_MODEL_ALIASES env var into {slug: model_id} dict.

    Format: "slug1=model_id1,slug2=model_id2"
    """
    aliases: dict[str, str] = {}
    if not raw:
        return aliases
    for pair in raw.split(","):
        pair = pair.strip()
        if "=" in pair:
            slug, model_id = pair.split("=", 1)
            aliases[slug.strip()] = model_id.strip()
    return aliases


def _generate_model_catalog(
    proxy_models: list[dict],
    aliases: dict[str, str] | None = None,
) -> list[dict]:
    """Generate Codex model catalog from proxy model list.

    Matches the official Codex model catalog schema with all required fields.
    Aliases map short slugs to proxy model IDs.
    """
    catalog = []
    seen = set()
    aliases = aliases or {}

    _REASONING_LEVELS = [
        {"effort": "low", "description": "Fast responses with lighter reasoning"},
        {"effort": "medium", "description": "Balances speed and reasoning depth for everyday tasks"},
        {"effort": "high", "description": "Greater reasoning depth for complex problems"},
        {"effort": "xhigh", "description": "Extra high reasoning depth for complex problems"},
    ]

    _NON_REASONING_LEVELS = [
        {"effort": "low", "description": "Fast responses with lighter reasoning"},
        {"effort": "medium", "description": "Balances speed and reasoning depth for everyday tasks"},
        {"effort": "high", "description": "Greater reasoning depth for complex problems"},
    ]

    # Build reverse map: model_id -> list of alias slugs
    alias_by_model: dict[str, list[str]] = {}
    for alias_slug, model_id in aliases.items():
        alias_by_model.setdefault(model_id, []).append(alias_slug)

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

        # Determine if model supports reasoning based on name heuristics
        is_reasoning = any(
            kw in model_id_lower
            for kw in ("o1", "o3", "o4", "reasoning", "deepseek-r", "think")
        )

        catalog.append({
            "slug": model_id,
            "display_name": display_name,
            "description": f"{display_name} via CodeFreedom proxy",
            "default_reasoning_level": "medium" if is_reasoning else "low",
            "supported_reasoning_levels": (
                _REASONING_LEVELS if is_reasoning else _NON_REASONING_LEVELS
            ),
            "shell_type": "shell_command",
            "visibility": "list",
            "supported_in_api": True,
            "priority": 50,
            "context_window": 131072,
            "supports_reasoning_summaries": True,
            "supports_parallel_tool_calls": True,
            "input_modalities": ["text"],
            "supports_search_tool": False,
        })

        # Add alias entries (short slug -> same model)
        for alias_slug in alias_by_model.get(model_id, []):
            if alias_slug not in seen:
                seen.add(alias_slug)
                catalog.append({
                    "slug": alias_slug,
                    "display_name": f"{display_name} ({alias_slug})",
                    "description": f"{display_name} via CodeFreedom proxy (alias: {alias_slug})",
                    "default_reasoning_level": "medium" if is_reasoning else "low",
                    "supported_reasoning_levels": (
                        _REASONING_LEVELS if is_reasoning else _NON_REASONING_LEVELS
                    ),
                    "shell_type": "shell_command",
                    "visibility": "list",
                    "supported_in_api": True,
                    "priority": 51,
                    "context_window": 131072,
                    "supports_reasoning_summaries": True,
                    "supports_parallel_tool_calls": True,
                    "input_modalities": ["text"],
                    "supports_search_tool": False,
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

    # Parse model aliases from profile env
    aliases = _parse_model_aliases(profile_env.get("CODEX_MODEL_ALIASES", ""))

    # Fetch models from proxy
    eprint(f"{tag('CODEX')} Fetching models from proxy...")
    proxy_models = _fetch_proxy_models(proxy_url, api_key=api_key)
    catalog = _generate_model_catalog(proxy_models, aliases=aliases)

    if catalog:
        eprint(f"{tag('CODEX')} Found {len(catalog)} model(s) from proxy.")
    else:
        eprint(f"{tag('CODEX')} No models found from proxy, using default config.")

    lines = [
        "# Auto-generated by CodeFreedom -- do not edit manually",
        "",
        'model_provider = "codefreedom"',
        "",
    ]

    default_model = profile_env.get("CODEX_DEFAULT_MODEL", "")
    if default_model:
        lines.append(f'model = "{default_model}"')
        lines.append("")

    lines.append("[model_providers.codefreedom]")
    lines.append('name = "CodeFreedom Proxy"')
    lines.append(f'base_url = "{proxy_url.rstrip("/")}/v1"')
    lines.append('wire_api = "responses"')

    if api_key:
        lines.append('env_key = "OPENAI_API_KEY"')

    # Reference model catalog if we have models
    if catalog:
        # Use the provided codex_home path for catalog reference
        effective_home = codex_home or (CODEFREEDOM_DIR / "codex-code" / "home")
        catalog_path = effective_home / "model_catalog.json"
        lines.append(f'model_catalog_json = "{catalog_path.as_posix()}"')

    lines.append("")

    # Add custom_models entries for TUI discovery
    if catalog:
        for m in catalog:
            lines.append('[[model_providers.codefreedom.custom_models]]')
            lines.append(f'id = "{m["id"]}"')
            lines.append(f'name = "{m["name"]}"')
            lines.append("")

    # Wrap catalog in {"models": [...]} format required by Codex
    catalog_content = _json.dumps({"models": catalog}, indent=2) if catalog else ""

    return "\n".join(lines), catalog_content


def _write_codex_config(
    config_content: str,
    config_dir: Path,
) -> Path:
    """Write the generated ``config.toml`` to *config_dir*, merging with existing config.

    Preserves user-added sections (projects, tui, windows, etc.) by parsing
    the existing config and only updating CodeFreedom-managed sections.
    Creates parent directories if they don't exist.
    Returns the path to the written config file.
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / CODEX_CONFIG_NAME

    # If existing config exists, merge instead of overwrite
    if config_path.exists():
        try:
            existing_content = config_path.read_text(encoding="utf-8")
            merged = _merge_toml_configs(existing_content, config_content)
            config_path.write_text(merged, encoding="utf-8")
            eprint(f"{tag('CODEX')} Merged proxy config at {config_path}")
        except Exception:
            # Fallback to overwrite if merge fails
            config_path.write_text(config_content, encoding="utf-8")
            eprint(f"{tag('CODEX')} Regenerated proxy config at {config_path}")
    else:
        config_path.write_text(config_content, encoding="utf-8")
        eprint(f"{tag('CODEX')} Generated proxy config at {config_path}")

    config_path.chmod(0o600)
    return config_path


def _merge_toml_configs(existing: str, new: str) -> str:
    """Merge new CodeFreedom config into existing config, preserving user sections.

    Updates only CodeFreedom-managed keys:
    - model_provider, model
    - [model_providers.codefreedom] and its custom_models
    - model_catalog_json

    Preserves everything else (projects, tui, windows, etc.)
    """
    existing_lines = existing.splitlines()
    new_lines = new.splitlines()

    # Extract sections from new config
    new_sections: dict[str, list[str]] = {}
    current_section = ""
    for line in new_lines:
        stripped = line.strip()
        if stripped.startswith("[") and not stripped.startswith("[["):
            current_section = stripped
            new_sections[current_section] = [line]
        elif stripped.startswith("[["):
            # Array of tables like [[model_providers.codefreedom.custom_models]]
            current_section = stripped
            if current_section not in new_sections:
                new_sections[current_section] = []
            new_sections[current_section].append(line)
        elif current_section:
            new_sections[current_section].append(line)
        else:
            # Top-level keys
            if "" not in new_sections:
                new_sections[""] = []
            new_sections[""].append(line)

    # Build merged config
    result_lines: list[str] = []
    skip_until_next_section = False
    seen_codefreedom_sections: set[str] = set()

    for line in existing_lines:
        stripped = line.strip()

        # Check if this is a section header
        if stripped.startswith("[[") or (stripped.startswith("[") and not stripped.startswith("[[")):
            # Determine if this is a CodeFreedom-managed section
            is_codefreedom = "model_providers.codefreedom" in stripped

            if is_codefreedom:
                # Replace with new content
                if stripped not in seen_codefreedom_sections:
                    seen_codefreedom_sections.add(stripped)
                    if stripped in new_sections:
                        result_lines.extend(new_sections[stripped])
                        result_lines.append("")
                skip_until_next_section = True
                continue
            else:
                skip_until_next_section = False

        # Skip lines in CodeFreedom sections (we already replaced them)
        if skip_until_next_section:
            continue

        # Replace top-level CodeFreedom keys
        if stripped.startswith("model_provider") or stripped.startswith("model =") or stripped.startswith("model_catalog_json"):
            continue  # Will be added from new config

        result_lines.append(line)

    # Add any new sections not in existing config
    for section, lines in new_sections.items():
        if section == "":
            # Add top-level keys that weren't in existing
            for line in lines:
                key = line.split("=")[0].strip() if "=" in line else ""
                if key and not any(ln.strip().startswith(key) for ln in result_lines):
                    result_lines.append(line)
        elif section not in seen_codefreedom_sections:
            result_lines.extend(lines)
            result_lines.append("")

    # Ensure CodeFreedom top-level keys are present
    cf_top_keys = {}
    for line in new_sections.get("", []):
        if "=" in line:
            key = line.split("=")[0].strip()
            cf_top_keys[key] = line

    # Insert CodeFreedom top-level keys at the beginning (after comment)
    insert_pos = 0
    for i, line in enumerate(result_lines):
        if line.strip().startswith("#"):
            insert_pos = i + 1
        else:
            break

    for key, line in cf_top_keys.items():
        if not any(ln.strip().startswith(key) for ln in result_lines):
            result_lines.insert(insert_pos, line)
            insert_pos += 1

    # Clean up empty lines
    cleaned: list[str] = []
    prev_empty = False
    for line in result_lines:
        if line.strip() == "":
            if not prev_empty:
                cleaned.append(line)
            prev_empty = True
        else:
            cleaned.append(line)
            prev_empty = False

    return "\n".join(cleaned)


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

    # Write config.toml with merge support (preserves user sections)
    _write_codex_config(config_content, codex_home)

    # Write model catalog if we have one
    if catalog_content:
        catalog_path = codex_home / "model_catalog.json"
        catalog_path.write_text(catalog_content, encoding="utf-8")
        catalog_path.chmod(0o600)
        eprint(f"{tag('CODEX')} Generated model catalog at {catalog_path}")

    # Inject OPENAI_API_KEY for proxy authentication
    proxy_api_key = profile_env.get("PROXY_API_KEY", "")
    if proxy_api_key:
        env["OPENAI_API_KEY"] = proxy_api_key

    if catalog_content:
        eprint(f"{tag('CODEX')} Tip: Use 'codex -m <model>' to select a custom model.")
        eprint(f"{tag('CODEX')} Example: codex -m MiMo-V2.5 -m sonnet")

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

    # Write config.toml with merge support (preserves user sections)
    _write_codex_config(config_content, codex_home_dir)

    # Write model catalog if we have one
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
    config_content, catalog_content = _generate_codex_config(proxy_url, profile_env)

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
