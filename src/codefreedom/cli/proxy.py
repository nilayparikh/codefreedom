"""Proxy subcommand -- manage the LLM routing proxy (Docker or native).

Usage:
    codefreedom proxy init [--reset]   Initialize proxy configs
    codefreedom proxy start            Start the proxy (native, default)
    codefreedom proxy start --docker   Start via Docker Compose
    codefreedom proxy stop             Stop the proxy
    codefreedom proxy status           Show proxy status
    codefreedom proxy validate         Validate configuration
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from codefreedom.env_loader import eprint, load_dotenv

# ── Path resolution ──────────────────────────────────────────────────────────

_CODEFREEDOM_DIR = Path.home() / ".codefreedom"

# ── Non-disclaimer banner ────────────────────────────────────────────────────

_NOTICE = """\
--- Notice ----------------------------------------------------------
CodeFreedom is provided \"as is\", without warranty of any kind.
See the Apache 2.0 License for details.
---------------------------------------------------------------------"""


def _find_bundled_examples() -> Path:
    """Find the bundled examples directory inside the installed package."""
    return Path(__file__).resolve().parent.parent / "examples"


def init_proxy(reset: bool = False) -> int:
    """Initialize proxy configs and .env.proxy from bundled examples.

    Delta-aware: skips files that already exist unless --reset is passed.
    Always prints what was copied/skipped, a doc link, and the non-disclaimer.
    """
    bundled = _find_bundled_examples()
    proxy_src = bundled / "proxy"

    cf_dir = _CODEFREEDOM_DIR
    proxy_dst = cf_dir / "proxy"

    created: list[str] = []
    skipped: list[str] = []

    def _copy_file(src: Path, dst: Path) -> None:
        if not reset and dst.exists():
            skipped.append(str(dst))
            print(f"[proxy init] [SKIP] Already exists: {dst}")
        elif src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            created.append(str(dst))
            print(f"[proxy init] [OK]   Created {dst}")
        else:
            print(f"[proxy init] [FAIL] Source not found: {src}")

    # ── config.yaml ────────────────────────────────────────────────────
    _copy_file(
        proxy_src / "config" / "config.yaml",
        proxy_dst / "config" / "config.yaml",
    )

    # ── docker-compose.yaml ────────────────────────────────────────────
    _copy_file(
        proxy_src / "docker-compose.yaml",
        proxy_dst / "docker-compose.yaml",
    )

    # ── Providers ──────────────────────────────────────────────────────
    providers_src = proxy_src / "config" / "providers"
    providers_dst = proxy_dst / "config" / "providers"
    if providers_src.exists():
        for provider_file in sorted(providers_src.glob("*.yaml")):
            _copy_file(provider_file, providers_dst / provider_file.name)

    # ── Env files ──────────────────────────────────────────────────────
    _copy_file(
        proxy_src / ".env.proxy.example",
        cf_dir / ".env.proxy",
    )
    _copy_file(
        proxy_src / ".env.proxy.secrets.example",
        cf_dir / ".env.proxy.secrets",
    )

    # ── Summary ────────────────────────────────────────────────────────
    print()
    if created:
        print(f"[proxy init] Done — {len(created)} created, {len(skipped)} skipped.")
    else:
        print(f"[proxy init] Nothing to do — {len(skipped)} files already exist.")
        print("              Use --reset to overwrite all files.")
    print("              Configure: https://nilayparikh.github.io/codefreedom/proxy/")
    print(_NOTICE)
    return 0


def _find_compose_file() -> Optional[Path]:
    """Find the LiteLLM docker-compose file in ~/.codefreedom/proxy/."""
    candidate = _CODEFREEDOM_DIR / "proxy" / "docker-compose.yaml"
    if candidate.exists():
        return candidate
    return None


def _find_config_file() -> Optional[Path]:
    """Find the LiteLLM config.yaml in ~/.codefreedom/proxy/config/."""
    candidate = _CODEFREEDOM_DIR / "proxy" / "config" / "config.yaml"
    if candidate.exists():
        return candidate
    return None


# ── Entry point ──────────────────────────────────────────────────────────────


def run(args: argparse.Namespace) -> int:
    """Execute the proxy subcommand. Returns exit code."""

    action = args.action or "status"

    if action == "start":
        return _start(args)
    elif action == "stop":
        return _stop()
    elif action == "status":
        return _status()
    elif action == "validate":
        return _validate()
    elif action == "init":
        return init_proxy(reset=args.reset)
    else:
        eprint(
            "[proxy] No action specified."
            " Use start, stop, status, validate, or init."
        )
        return 1


def _load_proxy_env_files() -> Dict[str, str]:
    """Load proxy-specific env files: .env.proxy and .env.proxy.secrets.

    Returns a merged dict (secrets override config).
    """
    merged: Dict[str, str] = {}
    for env_path in [
        _CODEFREEDOM_DIR / ".env.proxy",
        _CODEFREEDOM_DIR / ".env.proxy.secrets",
    ]:
        if env_path.exists():
            merged.update(load_dotenv(env_path))
            eprint(f"[proxy] Loaded env from {env_path}")
        else:
            eprint(f"[proxy] Env file not found (skipping): {env_path}")
    return merged


# ── Start ────────────────────────────────────────────────────────────────────


def _start(args: argparse.Namespace) -> int:
    """Start the LiteLLM proxy. Defaults to native; --docker uses Compose."""
    if args.docker:
        return _start_compose()
    else:
        return _start_native(args)


def _start_compose() -> int:
    """Start LiteLLM via docker compose."""
    compose_file = _find_compose_file()
    if not compose_file:
        eprint("[ERROR] Could not find ~/.codefreedom/proxy/docker-compose.yaml")
        eprint("   Run: codefreedom --init")
        return 1

    eprint(f"[proxy] Starting LiteLLM via Docker Compose ({compose_file})...")

    # Load proxy env files and merge with system env.
    # Proxy env files override system env so docker compose sees
    # configured values even when system env has empty-string vars
    # (e.g. MICROSOFT_FOUNDRY_API_BASE="" in shell).
    proxy_file_env = _load_proxy_env_files()
    merged_env = {**os.environ, **proxy_file_env}

    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(compose_file),
            "--profile",
            "litellm",
            "up",
            "-d",
        ],
        env=merged_env,
        capture_output=False,
        check=False,
    )
    if result.returncode == 0:
        eprint("[proxy] [OK] Proxy started at http://localhost:4000")
    else:
        eprint("[proxy] [FAIL] Failed to start. Check docker logs.")
    return result.returncode


def _start_native(args: argparse.Namespace) -> int:
    """Start LiteLLM directly as a Python process."""
    try:
        __import__("litellm")
    except ImportError:
        eprint("[ERROR] litellm package not installed.")
        eprint("   Install: pip install codefreedom[litellm]")
        eprint("   This installs litellm with proxy extras (websockets, etc.).")
        eprint("   Or use --docker to run via Docker Compose instead.")
        return 1

    litellm_bin = shutil.which("litellm")
    if not litellm_bin:
        eprint("[ERROR] litellm CLI not found on PATH.")
        eprint("   Ensure litellm is installed: pip install codefreedom[litellm]")
        return 1

    config_file = _find_config_file()
    if not config_file:
        eprint("[ERROR] Could not find ~/.codefreedom/proxy/config/config.yaml")
        eprint("   Run: codefreedom --init")
        return 1

    port = args.port or 4000
    host = args.host or "0.0.0.0"

    eprint(f"[proxy] Starting natively on {host}:{port}...")
    eprint(f"[proxy] Config: {config_file}")

    cmd = [
        litellm_bin,
        "--config",
        str(config_file),
        "--port",
        str(port),
        "--host",
        host,
    ]

    # Load proxy env files and merge with system env.
    # Proxy env files override system env so the litellm process sees
    # configured values even when system env has empty-string vars.
    proxy_file_env = _load_proxy_env_files()
    merged_env = {**os.environ, **proxy_file_env}

    try:
        proc = subprocess.Popen(cmd, env=merged_env)
        eprint(f"[proxy] [OK] Proxy starting (PID: {proc.pid})")
        eprint("[proxy]   Press Ctrl+C to stop.")
        proc.wait()
        return proc.returncode
    except KeyboardInterrupt:
        eprint("\n[proxy] Proxy stopped.")
        return 0
    except FileNotFoundError:
        eprint("[ERROR] Could not find litellm executable.")
        return 1


# ── Stop ─────────────────────────────────────────────────────────────────────


def _stop() -> int:
    """Stop the LiteLLM proxy."""
    compose_file = _find_compose_file()
    if not compose_file:
        eprint("[ERROR] Could not find ~/.codefreedom/proxy/docker-compose.yaml")
        eprint("   Run: codefreedom --init")
        return 1

    eprint("[proxy] Stopping LiteLLM proxy...")
    result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "--profile", "litellm", "down"],
        capture_output=False,
        check=False,
    )
    if result.returncode == 0:
        eprint("[proxy] [OK] Proxy stopped.")
    return result.returncode


# ── Status ───────────────────────────────────────────────────────────────────


def _status() -> int:
    """Show LiteLLM proxy status."""
    compose_file = _find_compose_file()
    if not compose_file:
        eprint("[ERROR] Could not find ~/.codefreedom/proxy/docker-compose.yaml")
        eprint("   Run: codefreedom --init")
        return 1

    result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "--profile", "litellm", "ps"],
        capture_output=False,
        check=False,
    )
    return result.returncode


# ── Validate ─────────────────────────────────────────────────────────────────


def _validate() -> int:
    """Validate the LiteLLM configuration."""
    config_file = _find_config_file()
    if not config_file:
        eprint("[ERROR] Could not find ~/.codefreedom/proxy/config/config.yaml")
        eprint("   Run: codefreedom --init")
        return 1

    errors: List[str] = []

    eprint(f"[proxy] Validating {config_file}...")
    eprint()

    try:
        import yaml
    except ImportError:
        eprint("[WARN] PyYAML not installed. Using basic validation only.")
        eprint("   Install: pip install pyyaml")
        _validate_basic(config_file, errors)
        _print_validation_result(errors)
        return 0 if not errors else 1

    try:
        with open(config_file, encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        eprint(f"  [FAIL]  YAML parse error: {e}")
        return 1
    except FileNotFoundError:
        eprint(f"  [FAIL]  File not found: {config_file}")
        return 1

    if not isinstance(config, dict):
        eprint("  [FAIL]  Config must be a YAML dictionary.")
        return 1

    includes = config.get("include", [])
    if not includes:
        eprint("  [WARN]  No provider includes found in config.yaml")
    else:
        config_dir = config_file.parent
        for inc in includes:
            provider_file = config_dir / inc
            if provider_file.exists():
                eprint(f"  [OK]  {inc}")
                try:
                    with open(provider_file, encoding="utf-8") as f:
                        provider_config = yaml.safe_load(f)
                    if provider_config is None:
                        eprint("    [SKIP]  (empty/commented out)")
                        continue
                    models = provider_config.get("model_list", [])
                    for m in models:
                        name = m.get("model_name", "?")
                        params = m.get("litellm_params", {})
                        api_key_ref = params.get("api_key", "")
                        if api_key_ref.startswith("os.environ/"):
                            env_var = api_key_ref[len("os.environ/") :]
                            if not _env_is_set(env_var):
                                eprint(
                                    f"    [WARN]  {name}: env var {env_var} is not set"
                                )
                            else:
                                eprint(f"    [OK]  {name} (auth: {env_var} [OK])")
                        else:
                            eprint(f"    [OK]  {name}")
                except yaml.YAMLError as e:
                    eprint(f"    [FAIL]  {inc}: YAML error -- {e}")
                    errors.append(f"YAML error in {inc}: {e}")
            else:
                eprint(f"  [FAIL]  {inc} -- file not found")
                errors.append(f"Missing provider file: {inc}")

    general = config.get("general_settings", {})
    if not general.get("database_url"):
        eprint("  [WARN]  database_url not set (stateless mode)")

    router = config.get("router_settings", {})
    aliases = router.get("model_group_alias", {})
    if aliases:
        eprint(f"  [OK]  Model aliases: {len(aliases)} defined")
        for alias, model in aliases.items():
            eprint(f"       {alias} → {model}")
    else:
        eprint("  [WARN]  No model_group_alias defined")

    eprint()
    _print_validation_result(errors)
    return 0 if not errors else 1


def _validate_basic(config_file: Path, errors: List[str]) -> None:
    """Basic validation without PyYAML."""
    content = config_file.read_text()
    checks = [
        ("include:", "provider includes"),
        ("general_settings:", "general_settings section"),
        ("router_settings:", "router_settings section"),
        ("litellm_settings:", "litellm_settings section"),
        ("model_group_alias:", "model aliases"),
    ]
    for marker, label in checks:
        if marker in content:
            eprint(f"  [OK]  {label} found")
        else:
            eprint(f"  [FAIL]  {label} missing")
            errors.append(f"Missing: {label}")

    config_dir = config_file.parent
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("- providers/"):
            provider_file = line[2:].strip()
            full = config_dir / provider_file
            if full.exists():
                eprint(f"  [OK]  {provider_file}")
            else:
                eprint(f"  [FAIL]  {provider_file} -- not found")
                errors.append(f"Missing: {provider_file}")


def _env_is_set(var_name: str) -> bool:
    """Check if an environment variable is set and non-empty."""
    import os

    return bool(os.environ.get(var_name))


def _print_validation_result(errors: List[str]) -> None:
    """Print validation summary."""
    if errors:
        eprint(f"  [FAIL]  {len(errors)} issue(s) found.")
        for e in errors:
            eprint(f"       - {e}")
    else:
        eprint("  [OK]  Configuration looks good!")
