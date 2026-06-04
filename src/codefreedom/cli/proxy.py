"""Proxy subcommand -- manage the LLM routing proxy (Docker or native).

Usage:
    codefreedom proxy init            Initialize proxy configs
    codefreedom proxy start            Start the proxy (native, default)
    codefreedom proxy start --docker   Start via Docker Compose
    codefreedom proxy stop             Stop the proxy
    codefreedom proxy restart --docker Restart the proxy (Docker Compose native)
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

from codefreedom.cli.init_utils import find_bundled_examples
from codefreedom.cli.tool_init_utils import _print_non_disclaimer
from codefreedom.config import get_codefreedom_dir
from codefreedom.env_loader import eprint, load_dotenv

# ── Path resolution ──────────────────────────────────────────────────────────


def _get_cf_dir() -> Path:
    """Lazy accessor for the CodeFreedom config directory (test-patchable)."""
    return get_codefreedom_dir()


def init_proxy() -> int:
    """Initialize proxy configs and .env.proxy from bundled examples.

    Only copies files into an empty target — if any config already exists,
    directs user to docs and example configs for manual merging.
    """
    bundled = find_bundled_examples(__file__)
    proxy_src = bundled / "proxy"

    cf_dir = _get_cf_dir()
    proxy_dst = cf_dir / "proxy"

    # Collect all source→destination pairs
    pairs: list[tuple[Path, Path]] = [
        (proxy_src / "config" / "config.yaml", proxy_dst / "config" / "config.yaml"),
        (proxy_src / "docker-compose.yaml", proxy_dst / "docker-compose.yaml"),
        (proxy_src / ".env.proxy.example", cf_dir / ".env.proxy"),
        (proxy_src / ".env.proxy.secrets.example", cf_dir / ".env.proxy.secrets"),
    ]

    providers_src = proxy_src / "config" / "providers"
    providers_dst = proxy_dst / "config" / "providers"
    if providers_src.exists():
        for provider_file in sorted(providers_src.glob("*.yaml")):
            pairs.append((provider_file, providers_dst / provider_file.name))

    # All-or-nothing check: if any destination file exists, skip everything
    existing = [dst for _, dst in pairs if dst.exists()]
    if existing:
        print(
            "[proxy init] Config already exists — init only bootstraps clean directories."
        )
        print("             Docs:    https://nilayparikh.github.io/codefreedom/proxy/")
        print(
            "             Example: https://github.com/nilayparikh/codefreedom/tree/main/src/codefreedom/examples/proxy/"
        )
        print("             Please merge changes manually.")
        print()
        _print_non_disclaimer()
        return 0

    # Nothing exists -- copy all, with rollback on failure
    created: list[Path] = []
    try:
        for src, dst in pairs:
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                created.append(dst)
                print(f"[proxy init] [CREATE] {dst}")
            else:
                print(f"[proxy init] [MISSING] Source not found: {src}")
    except OSError as exc:
        eprint(f"[proxy init] [ERROR] Copy failed: {exc}. Rolling back.")
        for path in created:
            try:
                path.unlink()
            except OSError:
                pass
        return 1

    # ── Summary ────────────────────────────────────────────────────────
    print()
    if created:
        print(f"[proxy init] Done -- {len(created)} created.")
    print("             Configure: https://nilayparikh.github.io/codefreedom/proxy/")
    _print_non_disclaimer()
    return 0


def _find_compose_file() -> Optional[Path]:
    """Find the LiteLLM docker-compose file in ~/.codefreedom/proxy/."""
    candidate = _get_cf_dir() / "proxy" / "docker-compose.yaml"
    if candidate.exists():
        return candidate
    return None


def _find_config_file() -> Optional[Path]:
    """Find the LiteLLM config.yaml in ~/.codefreedom/proxy/config/."""
    candidate = _get_cf_dir() / "proxy" / "config" / "config.yaml"
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
    elif action == "restart":
        return _restart(args)
    elif action == "status":
        return _status()
    elif action == "validate":
        return _validate()
    elif action == "init":
        return init_proxy()
    else:
        eprint(
            "[proxy] No action specified."
            " Use start, stop, restart, status, validate, or init."
        )
        return 1


def _load_proxy_env_files() -> Dict[str, str]:
    """Load proxy-specific env files: .env.proxy and .env.proxy.secrets.

    Returns a merged dict (secrets override config).
    """
    merged: Dict[str, str] = {}
    for env_path in [
        _get_cf_dir() / ".env.proxy",
        _get_cf_dir() / ".env.proxy.secrets",
    ]:
        if env_path.exists():
            merged.update(load_dotenv(env_path))
            eprint(f"[proxy] Loaded env from {env_path}")
        else:
            eprint(f"[proxy] Env file not found (skipping): {env_path}")
    return merged


def _build_proxy_env() -> Dict[str, str]:
    """Build merged environment: proxy env files override system env.

    Proxy env files override system env so the proxy process sees
    configured values even when system env has empty-string vars
    (e.g. MICROSOFT_FOUNDRY_API_BASE="" in shell).
    """
    proxy_file_env = _load_proxy_env_files()
    return {**os.environ, **proxy_file_env}


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
        eprint("   Run: codefreedom proxy init")
        return 1

    eprint(f"[proxy] Starting LiteLLM via Docker Compose ({compose_file})...")

    # Build merged environment (proxy files override system env).
    merged_env = _build_proxy_env()

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
        timeout=120,
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
        eprint("   Run: codefreedom proxy init")
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

    # Build merged environment (proxy files override system env).
    merged_env = _build_proxy_env()

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
        eprint("   Run: codefreedom proxy init")
        return 1

    eprint("[proxy] Stopping LiteLLM proxy...")
    result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "--profile", "litellm", "down"],
        capture_output=False,
        timeout=60,
        check=False,
    )
    if result.returncode == 0:
        eprint("[proxy] [OK] Proxy stopped.")
    return result.returncode


# ── Restart ───────────────────────────────────────────────────────────────────


def _restart(args: argparse.Namespace) -> int:
    """Restart the LiteLLM proxy.

    Docker mode: uses `docker compose restart` (compose's native capability —
    fast, preserves container state, picks up compose-file changes; does not
    pull a new image).

    Native mode: errors out cleanly. The native proxy has no stop path
    (it runs in the foreground and exits on Ctrl+C), so there is nothing
    to restart. Use `codefreedom proxy start` directly, or pass --docker.
    """
    if not args.docker:
        eprint(
            "[proxy] 'restart' is only supported in Docker mode."
            " Use: codefreedom proxy start --docker"
        )
        eprint("   (Native mode runs in the foreground and exits on Ctrl+C.)")
        return 1

    compose_file = _find_compose_file()
    if not compose_file:
        eprint("[ERROR] Could not find ~/.codefreedom/proxy/docker-compose.yaml")
        eprint("   Run: codefreedom proxy init")
        return 1

    eprint(f"[proxy] Restarting LiteLLM via Docker Compose ({compose_file})...")
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(compose_file),
            "--profile",
            "litellm",
            "restart",
        ],
        capture_output=False,
        timeout=60,
        check=False,
    )
    if result.returncode == 0:
        eprint("[proxy] [OK] Proxy restarted at http://localhost:4000")
    else:
        eprint("[proxy] [FAIL] Failed to restart. Check docker logs.")
    return result.returncode


# ── Status ───────────────────────────────────────────────────────────────────


def _status() -> int:
    """Show LiteLLM proxy status."""
    compose_file = _find_compose_file()
    if not compose_file:
        eprint("[ERROR] Could not find ~/.codefreedom/proxy/docker-compose.yaml")
        eprint("   Run: codefreedom proxy init")
        return 1

    result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "--profile", "litellm", "ps"],
        capture_output=False,
        timeout=15,
        check=False,
    )
    return result.returncode


# ── Validate ─────────────────────────────────────────────────────────────────


def _validate() -> int:
    """Validate the LiteLLM configuration."""
    config_file = _find_config_file()
    if not config_file:
        eprint("[ERROR] Could not find ~/.codefreedom/proxy/config/config.yaml")
        eprint("   Run: codefreedom proxy init")
        return 1

    errors: List[str] = []

    eprint(f"[proxy] Validating {config_file}...")
    eprint()

    # Load proxy env files so we can check api_key references against them
    proxy_env = _load_proxy_env_files()

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
                            if not _env_is_set(env_var, proxy_env):
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
            eprint(f"       {alias} -> {model}")
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


def _env_is_set(var_name: str, env: Optional[Dict[str, str]] = None) -> bool:
    """Check if an environment variable is set (including empty strings).

    If *env* is provided, it is checked first, then os.environ.  This lets
    callers (e.g. _validate) include vars loaded from .env.proxy files.
    """
    if env is not None and var_name in env:
        return True
    return var_name in os.environ


def _print_validation_result(errors: List[str]) -> None:
    """Print validation summary."""
    if errors:
        eprint(f"  [FAIL]  {len(errors)} issue(s) found.")
        for e in errors:
            eprint(f"       - {e}")
    else:
        eprint("  [OK]  Configuration looks good!")
