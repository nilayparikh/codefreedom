"""Proxy subcommand -- manage the LLM routing proxy (Docker Compose only).

Usage:
    codefreedom proxy init                  Initialize proxy configs
    codefreedom proxy start                Start the proxy (Docker Compose)
    codefreedom proxy stop                 Stop the proxy
    codefreedom proxy restart              Restart the proxy (Docker Compose)
    codefreedom proxy status               Show proxy status
    codefreedom proxy validate             Validate configuration

The proxy is always run via `docker compose` against
`~/.codefreedom/proxy/docker-compose.yaml`. The LiteLLM process runs inside
the `codefreedom:litellm-latest` image (see docker/litellm/Dockerfile.LiteLLM)
which bakes in the WebSearch count display patch. The web-bridge sidecar is
started as a sibling service in the same compose stack.

VS Code integration: see `codefreedom vscode proxy config`.
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

    # Bundled LiteLLM plugins live under config/plugins/ alongside
    # config.yaml.  Each plugin has its own subfolder (e.g.
    # plugins/reasoning-efforts/) containing a .yaml config table.
    # The .py module is baked into the Docker image (see
    # docker/litellm/Dockerfile.LiteLLM and entrypoint.sh) -- we
    # only copy the user-editable YAML to the host config directory.
    plugins_src = proxy_src / "config" / "plugins"
    plugins_dst = proxy_dst / "config" / "plugins"
    if plugins_src.exists():
        for plugin_file in sorted(plugins_src.rglob("*")):
            if plugin_file.is_file() and plugin_file.suffix == ".yaml":
                rel = plugin_file.relative_to(plugins_src)
                pairs.append((plugin_file, plugins_dst / rel))

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

    action = args.action

    if action == "start":
        return _start(args)
    elif action == "stop":
        return _stop()
    elif action == "restart":
        return _restart()
    elif action == "status":
        return _status()
    elif action == "validate":
        return _validate()
    elif action == "init":
        return init_proxy()
    # `vscode` moved to the top-level `codefreedom vscode proxy config`
    # subcommand -- see codefreedom.cli.vscode.
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

    Also injects ``POSTGRES_HOST_DATA_DIR`` and
    ``POSTGRES_HOST_BACKUP_DIR`` from ``CODEFREEDOM_HOME`` so the
    embedded PostgreSQL always lands inside the correct CodeFreedom
    directory, even when ``CODEFREEDOM_HOME`` is customised.
    """
    proxy_file_env = _load_proxy_env_files()
    merged = {**os.environ, **proxy_file_env}

    # Inject PostgreSQL data/backup dirs from CODEFREEDOM_HOME
    cf_dir = get_codefreedom_dir()
    merged.setdefault("POSTGRES_HOST_DATA_DIR", str(cf_dir / "pg" / "data"))
    merged.setdefault("POSTGRES_HOST_BACKUP_DIR", str(cf_dir / "pg" / "backup"))

    return merged


# ── Start ────────────────────────────────────────────────────────────────────


def _start(args: argparse.Namespace) -> int:
    """Start the LiteLLM proxy via `docker compose up -d`.

    --port and --host override LITELLM_PORT / LITELLM_BIND_HOST in the
    compose process environment for this run only (they do not edit
    .env.proxy).
    """
    return _start_compose(args)


def _web_bridge_build_context() -> Optional[Path]:
    """Locate the ``docker/web-bridge`` directory in the installed source tree.

    Returns ``None`` if the source tree is not available (e.g. installed from
    a wheel without the docker/ directory).  The caller should treat that as
    "skip the auto-build" and rely on a pre-built image instead.
    """
    # codefreedom.__file__ is .../src/codefreedom/__init__.py.  Walk up two
    # levels to the project root, then into docker/web-bridge.
    try:
        import codefreedom
    except ImportError:
        return None
    pkg_dir = Path(codefreedom.__file__).resolve().parent
    project_root = pkg_dir.parent.parent
    candidate = project_root / "docker" / "web-bridge"
    if (candidate / "Dockerfile.Bridge").is_file():
        return candidate
    return None


def _web_bridge_image() -> str:
    """Return the fully-qualified image tag used for the web-bridge sidecar.

    Reads ``WEB_BRIDGE_IMAGE`` from the merged env (proxy env files override
    system env). Falls back to the published ``docker.io/nilayparikh/codefreedom:web-bridge``
    reference so the local build is directly pushable to Docker Hub without
    a retag step. Override the env var to use a different registry/tag.
    """
    merged = _build_proxy_env()
    return merged.get(
        "WEB_BRIDGE_IMAGE", "docker.io/nilayparikh/codefreedom:web-bridge"
    )


def _ensure_web_bridge_image() -> int:
    """Make sure the web-bridge image (see :func:`_web_bridge_image`) exists.

    Returns 0 on success, 1 on hard failure (Docker error, source tree
    missing, build failure).  A pre-built image is a no-op.
    """
    image = _web_bridge_image()

    # Fast path: image already present?
    check = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        check=False,
    )
    if check.returncode == 0:
        return 0

    # Try to auto-build from the source tree.
    build_ctx = _web_bridge_build_context()
    if build_ctx is None:
        eprint(
            f"[proxy] [WARN] '{image}' image is missing and the source tree"
            " (docker/web-bridge/) could not be located."
        )
        eprint(
            "   Build it manually:"
            f"  docker build -t {image} -f docker/web-bridge/Dockerfile.Bridge"
            " docker/web-bridge/"
        )
        eprint("   The web-bridge sidecar will fail to start until the image exists.")
        # Don't hard-fail: the rest of the proxy stack can still come up.
        return 0

    eprint(
        f"[proxy] Web-bridge image '{image}' not found locally."
        " Building from source tree..."
    )
    eprint("   This is a one-time build (may take ~30 s).")
    result = subprocess.run(
        [
            "docker",
            "build",
            "-t",
            image,
            "-f",
            str(build_ctx / "Dockerfile.Bridge"),
            str(build_ctx),
        ],
        capture_output=False,
        timeout=300,
        check=False,
    )
    if result.returncode != 0:
        eprint(f"[proxy] [FAIL] Failed to build {image}. Check docker output above.")
        return 1
    eprint(f"[proxy] [OK] Built {image}.")
    return 0


def _start_compose(args: Optional[argparse.Namespace] = None) -> int:
    """Start LiteLLM via docker compose."""
    compose_file = _find_compose_file()
    if not compose_file:
        eprint("[ERROR] Could not find ~/.codefreedom/proxy/docker-compose.yaml")
        eprint("   Run: codefreedom proxy init")
        return 1

    # Auto-build the web-bridge image if it isn't present locally. The image
    # is referenced (not built) by docker-compose.yaml because a relative
    # build context would not survive the example → ~/.codefreedom copy step.
    if _ensure_web_bridge_image() != 0:
        return 1

    eprint(f"[proxy] Starting LiteLLM via Docker Compose ({compose_file})...")

    # Build merged environment: proxy files override system env, then CLI
    # flags override everything for this run only.
    merged_env = _build_proxy_env()
    if args is not None:
        if getattr(args, "port", None):
            merged_env["LITELLM_PORT"] = str(args.port)
        if getattr(args, "host", None):
            merged_env["LITELLM_BIND_HOST"] = args.host

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
        port = merged_env.get("LITELLM_PORT", "4000")
        eprint(f"[proxy] [OK] Proxy started at http://localhost:{port}")
    else:
        eprint("[proxy] [FAIL] Failed to start. Check docker logs.")
    return result.returncode


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


def _restart() -> int:
    """Restart the LiteLLM proxy.

    Uses `docker compose restart` (compose's native capability — fast,
    preserves container state, picks up compose-file changes; does not
    pull a new image).
    """
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
    database_url_in_config = general.get("database_url")
    database_url_in_env = _env_is_set("DATABASE_URL", proxy_env)
    if not database_url_in_config and not database_url_in_env:
        eprint("  [WARN]  database_url not set (stateless mode)")
        eprint(
            "         LiteLLP runs w/out Prisma persistence unless DATABASE_URL is set."
        )
        eprint(
            "         The codefreedom litellm image (default) auto-sets DATABASE_URL"
        )
        eprint(
            "         inside the container — no host-side config needed for DB features."
        )
    elif not database_url_in_config and database_url_in_env:
        eprint("  [OK]  DATABASE_URL found in environment (config.yaml not required)")

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


# VS Code config generation moved to codefreedom.cli.vscode.
