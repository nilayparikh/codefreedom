"""MiMoCode subcommand -- sandboxed or local launch with 0-click proxy config.

Auto-detects the running CodeFreedom LiteLLM proxy, generates a complete
``mimocode.json`` config with all proxy models, and launches MiMoCode
(``mimo``) with zero manual configuration.

Usage:
    codefreedom mimo [--sandbox] [--profile NAME] [--list-profiles] [agent-args...]
    cf mc [same]

Proxy auto-config:
    - Detects the proxy at LITELLM_BASE_URL (default: http://localhost:4000)
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

from codefreedom.config import (
    get_codefreedom_dir,
    resolve_mimo_profiles_path,
)
from codefreedom.env_loader import eprint, load_env_chain
from codefreedom.profiles import (
    ProfileError,
    get_profile_sandbox_images,
    get_profile_tools,
    list_profiles,
    load_profile_env,
    load_profiles,
)
from codefreedom.tool_registry import acquire_tools, generate_session_id, release_tools

# ── Constants ──────────────────────────────────────────────────────────────────

DEFAULT_MIMO_IMAGE = "docker.io/nilayparikh/codefreedom:mimo-code"
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
    import urllib.error
    import urllib.request

    models_url = f"{proxy_url.rstrip('/')}/v1/models"
    try:
        req = urllib.request.Request(models_url)
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("data", [])
    except urllib.error.HTTPError as exc:
        # 401/403 = auth problem — warn so the user knows why fallback kicked in
        if exc.code in (401, 403):
            eprint(
                f"[MIMO] Proxy returned {exc.code} — is LITELLM_MASTER_KEY set "
                f"in ~/.codefreedom/.env.claude.secrets?"
            )
        return []
    except (
        urllib.error.URLError,
        json.JSONDecodeError,
        OSError,
    ):
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
    else:
        provider_models = {}
        eprint(
            f"[MIMO] Proxy not reachable at {proxy_url}.\n"
            f"       Start the proxy (``cf proxy start``) and restart MiMoCode\n"
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


# ── Terminal helpers ──────────────────────────────────────────────────────────


def terminal_size() -> Tuple[str, str]:
    """Get terminal width and height as strings."""
    cols = os.environ.get("MIMO_CODE_COLUMNS")
    lines = os.environ.get("MIMO_CODE_LINES")
    try:
        result = subprocess.run(
            ["stty", "size"], capture_output=True, text=True, timeout=2, check=False
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split()
            if len(parts) == 2:
                if not lines:
                    lines = parts[0]
                if not cols:
                    cols = parts[1]
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return cols or "80", lines or "24"


def _forward_signal(
    proc: subprocess.Popen,  # type: ignore[type-arg]
    signum: int,
    _frame: object,
) -> None:
    """Forward a signal to the child process (docker exec or native)."""
    if proc and proc.poll() is None:
        proc.send_signal(signum)


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
        signal.signal(signal.SIGINT, lambda s, f: _forward_signal(proc, s, f))
        signal.signal(signal.SIGTERM, lambda s, f: _forward_signal(proc, s, f))
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
) -> int:
    """Run ``mimo`` inside an ephemeral Docker container.

    Each session gets a fresh container with a random name, cleaned up
    on exit (including Ctrl+C).
    """
    sandbox_images = sandbox_images or {}
    image = sandbox_images.get("default") or DEFAULT_MIMO_IMAGE

    container_name = f"{_CONTAINER_PREFIX}{secrets.token_hex(2)}"

    eprint(f"[IMAGE] Using sandbox image: {image}.")
    eprint(f"[CONTAINER] Name: {container_name}.")

    # ── Generate proxy config first (used both for env vars and mounting) ──
    proxy_url = _detect_proxy_url(profile_env)
    config = _generate_mimo_config(proxy_url, profile_env)
    mimo_home_dir, config_dir = _ensure_mimo_sandbox_dir(profile_name)
    config_path = _write_mimo_config(config, config_dir)

    # ── Build env flags ─────────────────────────────────────────────────────
    env_flags: List[str] = []
    for key in sorted(profile_env.keys()):
        val = profile_env[key]
        if val is not None:
            env_flags.extend(["-e", f"{key}={val}"])

    cols, lines = terminal_size()
    env_flags.extend(["-e", f"COLUMNS={cols}", "-e", f"LINES={lines}"])

    host_uid = os.getuid()
    host_gid = os.getgid()

    # ── Resolve container identity ──────────────────────────────────────────
    if run_as_me:
        container_home = f"/home/{Path.home().name}"
        container_user_flag = ["-u", f"{host_uid}:{host_gid}"]
        eprint(
            f"[SANDBOX] --run-as-me: container will run as "
            f"uid={host_uid}({Path.home().name}) gid={host_gid}"
        )
    else:
        container_home = "/home/codefreedom"
        container_user_flag = []
        eprint("[SANDBOX] Running as default container user 'codefreedom' (uid 1000).")

    # ── Build docker options ───────────────────────────────────────────────
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
        # Isolated MIMOCODE_HOME
        "-v",
        f"{mimo_home_dir}:{container_home}/.local/share/mimocode",
        # Proxy config
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

    # ── Ensure image is available ──────────────────────────────────────────
    _inspect = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if _inspect.returncode != 0:
        eprint(f"[IMAGE] Pulling '{image}'...")
        pull = subprocess.run(
            ["docker", "pull", image],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if pull.returncode != 0:
            eprint(f"[ERROR] Failed to pull image '{image}'.")
            if pull.stderr:
                eprint(f"   {pull.stderr.strip()}")
            return 1
    else:
        eprint(f"[IMAGE] Using cached image '{image}'.")

    # ── Start ephemeral container ─────────────────────────────────────────
    eprint(f"[RUN] Creating ephemeral container '{container_name}'...")
    create = subprocess.run(
        ["docker", "run", "-d", "--rm", "--name", container_name]
        + base_opts
        + env_flags
        + [image, "sleep", "infinity"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if create.returncode != 0:
        eprint("[ERROR] Failed to start container.")
        if create.stderr:
            eprint(f"   {create.stderr.strip()}")
        return 1
    eprint("[SANDBOX] Container started.")

    # ── Exec mimo into the container ───────────────────────────────────────
    eprint("[EXEC] Attaching MiMoCode session...")

    exec_cmd = (
        ["docker", "exec", "-it"]
        + container_user_flag
        + ["-e", f"HOME={container_home}"]
        + ["-e", f"MIMOCODE_CONFIG={container_home}/.config/mimocode/mimocode.json"]
        + env_flags
        + [container_name, "mimo"]
        + mimo_args
    )

    exit_code = 1
    try:
        proc = subprocess.Popen(exec_cmd)
        signal.signal(signal.SIGINT, lambda s, f: _forward_signal(proc, s, f))
        signal.signal(signal.SIGTERM, lambda s, f: _forward_signal(proc, s, f))
        proc.wait()
        exit_code = proc.returncode
    except KeyboardInterrupt:
        exit_code = 130
    finally:
        eprint(f"[CLEAN] Stopping container '{container_name}'...")
        subprocess.run(
            ["docker", "stop", container_name],
            capture_output=True,
            timeout=15,
            check=False,
        )
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            timeout=5,
            check=False,
        )
        eprint("[SANDBOX] Container cleaned up.")

    return exit_code


# ── Init command ─────────────────────────────────────────────────────────────


def init_mimo() -> int:
    """Print initialization help for MiMoCode."""
    from codefreedom.cli.tool_init_utils import print_help_section

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
            "  cf proxy start",
            "",
            "To launch MiMoCode:",
            "  cf mimo              # native mode",
            "  cf mimo --sandbox    # isolated Docker sandbox",
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
    base_env = load_env_chain(workspace_dir, component="claude")

    profile_name = getattr(args, "profile", None) or "default"
    profiles_path = resolve_mimo_profiles_path()

    profile_env: Dict[str, str] = {}
    if profiles_path.exists():
        try:
            profiles_dict = load_profiles(profiles_path)
            profile_env = load_profile_env(
                profile_name,
                profiles_path,
                base_env,
                mode="local",
                profiles=profiles_dict,
            )
        except ProfileError as exc:
            eprint(f"[ERROR] {exc}")
            return 1

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
        out_file = Path(out_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(output, encoding="utf-8")
        out_file.chmod(0o600)
        eprint(f"[CONFIG] Written to {out_file.resolve()}")
        return 0

    print(output)
    return 0


# ── Status / Stop ─────────────────────────────────────────────────────────────


def status() -> int:
    """Show all codefreedom mimo sandbox containers. Returns exit code."""
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"name={_CONTAINER_PREFIX}",
                "--format",
                "{{.Names}}\t{{.Status}}\t{{.CreatedAt}}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        containers = [line for line in result.stdout.strip().split("\n") if line]
        if containers:
            eprint(f"[STATUS] {len(containers)} MiMoCode sandbox container(s):")
            for line in containers:
                name, status_line, _created = line.split("\t", 2)
                marker = "RUNNING" if "Up " in status_line else "STOPPED"
                eprint(f"   {marker} {name}  ({status_line})")
        else:
            eprint("[STATUS] No MiMoCode sandbox containers found.")
        return 0
    except subprocess.TimeoutExpired:
        eprint("[STATUS] Docker command timed out. Is Docker running?")
        return 1
    except FileNotFoundError:
        eprint("[ERROR] Docker not found.")
        return 1


def stop() -> int:
    """Stop and remove all codefreedom mimo sandbox containers. Returns exit code."""
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                f"name={_CONTAINER_PREFIX}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        ids = [c for c in result.stdout.strip().split("\n") if c]
        if not ids:
            eprint("[CLEAN] No MiMoCode sandbox containers to remove.")
            return 0

        eprint(f"[CLEAN] Stopping {len(ids)} container(s)...")
        subprocess.run(
            ["docker", "stop"] + ids,
            capture_output=True,
            timeout=30,
            check=False,
        )
        subprocess.run(
            ["docker", "rm", "-f"] + ids,
            capture_output=True,
            timeout=30,
            check=False,
        )
        eprint("[SANDBOX] All MiMoCode sandbox containers removed.")
        return 0
    except subprocess.TimeoutExpired:
        eprint("[ERROR] Docker command timed out.")
        return 1
    except FileNotFoundError:
        eprint("[ERROR] Docker not found.")
        return 1


# ── Main entry point ─────────────────────────────────────────────────────────


def run(args: argparse.Namespace) -> int:
    """Execute the ``mimo`` subcommand. Returns exit code."""

    # Fast-path flags
    if args.list_profiles:
        profiles_path = resolve_mimo_profiles_path()
        profiles = list_profiles(profiles_path)
        if not profiles:
            eprint("[PROFILES] No profiles found.")
            return 0
        eprint(f"[PROFILES] Available profiles ({profiles_path}):\n")
        for p in profiles:
            override_word = "override" if len(p["env_keys"]) == 1 else "overrides"
            inheritance = (
                "standalone"
                if p["standalone"]
                else f"inherits from 'default' — {len(p['env_keys'])} {override_word}"
            )
            eprint(f"  {p['name']}")
            eprint(f"    {p['description']}")
            eprint(f"    ({inheritance})")
            if p.get("tools"):
                eprint(f"    tools: {', '.join(p['tools'])}")
            eprint()
        return 0

    # Actions
    action = getattr(args, "mimo_action", None)
    if action == "config":
        return cmd_config(args)

    # ── Load env chain ─────────────────────────────────────────────────────
    workspace_dir = Path.cwd()
    eprint("[ENV] Loading configuration...")
    base_env = load_env_chain(workspace_dir, component="claude")

    # ── Load profile ───────────────────────────────────────────────────────
    profile_name = args.profile or "default"
    profiles_path = resolve_mimo_profiles_path()

    profile_env: Dict[str, str] = {}
    sandbox_images: Dict[str, str] = {}
    tools: List[str] = []
    mode = "sandbox" if args.sandbox else "local"

    if profiles_path.exists():
        try:
            profiles_dict = load_profiles(profiles_path)
            profile_env = load_profile_env(
                profile_name, profiles_path, base_env, mode, profiles=profiles_dict
            )
            sandbox_images = get_profile_sandbox_images(
                profile_name, profiles_path, profiles=profiles_dict
            )
            tools = get_profile_tools(
                profile_name, profiles_path, profiles=profiles_dict
            )
        except ProfileError as e:
            eprint(f"[ERROR] {e}")
            return 1
    elif profile_name != "default":
        eprint(
            f"[ERROR] Profile '{profile_name}' requested but no profiles file found."
        )
        return 1
    else:
        eprint("[PROFILE] No profiles file found. Using defaults only.")

    # ── Ensure proxy API key is available ──────────────────────────────
    # Safety net: re-inject from base_env in case resolve failed
    # (e.g. if load_profiles had premature interpolation — fixed now,
    # but kept as defense-in-depth).
    if not profile_env.get("PROXY_API_KEY"):
        master_key = base_env.get("LITELLM_MASTER_KEY", "")
        if master_key:
            profile_env["PROXY_API_KEY"] = master_key

    run_as_me = getattr(args, "run_as_me", False)

    # ── Tools: acquire if declared in profile ────────────────────────────
    session_id = generate_session_id(mode)
    acquired_tools: List[str] = []
    if tools:
        eprint(f"[TOOLS] Profile '{profile_name}' declares tools: {', '.join(tools)}")
        acquired_tools = acquire_tools(session_id, tools, profile_name)
        if acquired_tools:
            eprint(f"[TOOLS] Running: {', '.join(acquired_tools)}")

    try:
        if args.sandbox:
            return run_docker(
                profile_env,
                args.mimo_args,
                workspace_dir,
                profile_name,
                sandbox_images=sandbox_images,
                run_as_me=run_as_me,
            )
        else:
            if run_as_me:
                eprint("[WARN] --run-as-me is only valid with --sandbox; ignoring.")
            return run_local(profile_env, args.mimo_args)
    finally:
        if acquired_tools:
            release_tools(session_id, acquired_tools)
