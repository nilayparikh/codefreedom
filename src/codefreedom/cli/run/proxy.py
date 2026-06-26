"""Proxy subcommand -- manage the LLM routing proxy (Docker Compose only).

Usage:
    codefreedom run proxy start                Start the proxy (Docker Compose)
    codefreedom run proxy stop                 Stop the proxy
    codefreedom run proxy restart              Restart the proxy (Docker Compose)
    codefreedom run proxy status               Show proxy status
    codefreedom run proxy validate             Validate configuration

The proxy is always run via `docker compose` against
`~/.codefreedom/config/proxy/docker-compose.yaml`. The LiteLLM process runs inside
the `codefreedom:litellm-latest` image (see docker/litellm/Dockerfile.LiteLLM)
which bakes in the WebSearch count display patch.  The web-bridge is now a
standalone tool (``cf run tools web-bridge``) — start it separately before the
proxy if you need WebSearch support.

VS Code integration: see `codefreedom setup config vscode proxy`.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from codefreedom.config import load_config
from codefreedom.config.errors import ConfigError
from codefreedom.config.runtime import apply_cf_cli_overrides, load_codefreedom_settings
from codefreedom.core.config import get_codefreedom_dir, get_config_dir
from codefreedom.docker.pull import pull_if_stale
from codefreedom.log import eprint, tag

# ── Path resolution ──────────────────────────────────────────────────────────


def _find_compose_file() -> Optional[Path]:
    """Find the LiteLLM docker-compose file in ~/.codefreedom/config/proxy/."""

    config_dir = get_config_dir()
    candidate = config_dir / "proxy" / "docker-compose.yaml"
    if candidate.exists():
        return candidate
    return None


def _find_config_file() -> Optional[Path]:
    """Find the LiteLLM config.yaml in ~/.codefreedom/config/proxy/config/."""

    config_dir = get_config_dir()
    candidate = config_dir / "proxy" / "config" / "config.yaml"
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
    # `vscode` moved to `codefreedom setup config vscode proxy config`
    # subcommand -- see codefreedom.cli.vscode.
    else:
        eprint(
            "[PROXY] No action specified."
            " Use start, stop, restart, status, or validate."
        )
        return 1


def _load_proxy_env_files() -> Dict[str, str]:
    """Load proxy env from machine environment variables only.

    All secrets must come from CF_CLI_* machine environment variables.
    No .env.* files are read for secrets.

    Used by ``_validate()`` which needs to inspect env values.
    All other callers should use :func:`_build_proxy_env` which goes
    through the full :func:`get_env` chain.
    """
    import os

    merged: Dict[str, str] = {}
    # Only load from os.environ (CF_CLI_* vars are already resolved)
    for key, value in os.environ.items():
        if value:
            merged[key] = value
    return merged


def _build_proxy_env() -> Dict[str, str]:
    """Build merged proxy environment via the canonical :func:`get_env` chain.

    Resolution order (standard — later wins):
      1. .env.proxy (config, skip if missing)
      2. .env (shared config, skip if missing)
      3. workspace .env (skip if missing)
      4. .env.proxy.secrets (secrets, skip if missing)
      5. .env.secrets (shared secrets, skip if missing)
      6. workspace .env.secrets (skip if missing)
      7. .env.user (user overrides, skip if missing)
      8. os.environ (machine env — always wins)
      9. CF_CLI_* overrides (absolute highest)

    Also injects ``POSTGRES_HOST_DATA_DIR`` from ``CODEFREEDOM_HOME``
    so the embedded PostgreSQL always lands inside the correct CodeFreedom
    directory, even when customised.
    """
    cf_dir = get_codefreedom_dir()
    merged = dict(os.environ)
    merged.setdefault("POSTGRES_HOST_DATA_DIR", str(cf_dir / "pg" / "data"))
    merged = apply_cf_cli_overrides(merged)
    settings = load_codefreedom_settings(Path.cwd())
    merged["LITELLM_BIND_HOST"] = settings.proxy.bind_host
    merged["LITELLM_PORT"] = str(settings.proxy.bind_port)
    merged.setdefault("PROXY_PUBLIC_BASE_URL", settings.proxy.public_base_url)

    # Inject SUFFIX_ID from config system so container/project names reflect
    # the user's override.yaml vars (e.g. SUFFIX_ID: "windemo").
    try:
        config = load_config()
        proxy_component = config.for_component("proxy")
        merged.setdefault("SUFFIX_ID", proxy_component.get("SUFFIX_ID", "0000"))
    except (ConfigError, Exception):
        merged.setdefault("SUFFIX_ID", "0000")

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
    system env). Falls back to the published ``docker.io/nilayparikh/codefreedom:web-bridge-latest``
    reference so the local build is directly pushable to Docker Hub without
    a retag step. Override the env var to use a different registry/tag.
    """
    merged = _build_proxy_env()
    return merged.get(
        "WEB_BRIDGE_IMAGE", "docker.io/nilayparikh/codefreedom:web-bridge-latest"
    )


def _ensure_web_bridge_image() -> int:
    """Make sure the web-bridge image (see :func:`_web_bridge_image`) exists.

    Returns 0 on success, 1 on hard failure (Docker error, source tree
    missing, build failure).  A pre-built image is a no-op.

    Follows the same pull-first pattern as other tools (chrome, web,
    github): check local cache, try ``docker pull`` for the correct
    multi-arch image, and only fall back to a local build if both fail.
    """
    image = _web_bridge_image()

    check = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        check=False,
    )
    if check.returncode != 0:
        eprint(f"[PROXY] Web-bridge image '{image}' not found locally, pulling...")
        pull = subprocess.run(
            ["docker", "pull", image],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if pull.returncode != 0:
            build_ctx = _web_bridge_build_context()
            if build_ctx is None:
                eprint(
                    f"{tag('PROXY')} Web-bridge image '{image}' not found."
                    " Source tree unavailable — cannot build."
                )
                return 1
            eprint(
                f"[PROXY] Web-bridge image '{image}' not found locally."
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
                eprint(
                    f"{tag('PROXY')} Failed to build {image}. Check docker output above."
                )
                return 1
            eprint(f"{tag('PROXY')} Built {image}.")
            return 0

    pull_if_stale(image, label="PROXY")
    return 0


def _ensure_codefreedom_network() -> None:
    """Create the shared ``codefreedom`` bridge network if it doesn't exist.

    All proxy instances (regardless of ``SUFFIX_ID``) attach to this
    common network so they can communicate with each other and with
    tools running on the host.
    """
    inspect = subprocess.run(
        ["docker", "network", "inspect", "codefreedom"],
        capture_output=True,
        timeout=10,
        check=False,
    )
    if inspect.returncode == 0:
        return  # network already exists

    eprint(f"{tag('PROXY')} Creating shared 'codefreedom' Docker network...")
    create = subprocess.run(
        ["docker", "network", "create", "codefreedom"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if create.returncode == 0:
        eprint(f"{tag('PROXY')} Network 'codefreedom' created.")
    else:
        eprint(
            f"{tag('PROXY')} Warning: could not create network: {create.stderr.strip()}"
        )


def _start_compose(args: Optional[argparse.Namespace] = None) -> int:
    """Start LiteLLM via docker compose."""
    compose_file = _find_compose_file()
    if not compose_file:
        eprint(
            f"{tag('ERROR')} Could not find ~/.codefreedom/config/proxy/docker-compose.yaml"
        )
        eprint("   Run: cf s i")
        return 1

    eprint(f"{tag('PROXY')} Starting LiteLLM via Docker Compose ({compose_file})...")

    # Ensure tools are running (needed for WebSearch, browser automation, etc.)
    # Non-fatal — proxy starts regardless.
    try:
        from codefreedom.cli.run.tools import ensure_tools

        ensure_tools()
    except Exception as exc:
        eprint(f"{tag('PROXY')} Warning: could not verify tools: {exc}")

    # Build merged environment: proxy files override system env, then CLI
    # flags override everything for this run only, then CF_CLI_* overrides
    # from machine env win everything.
    merged_env = _build_proxy_env()
    if args is not None:
        if getattr(args, "port", None):
            merged_env["LITELLM_PORT"] = str(args.port)
        if getattr(args, "host", None):
            merged_env["LITELLM_BIND_HOST"] = args.host

    # Use SUFFIX_ID from .env.proxy to create deterministic container/project
    # names.  Docker becomes the single source of truth — no /proc needed.
    suffix = merged_env.get("SUFFIX_ID", "0000")
    litellm_base = merged_env.get("LITELLM_CONTAINER_NAME", "litellm-codefreedom")
    litellm_name = f"{litellm_base}-{suffix}"
    merged_env["LITELLM_CONTAINER_NAME"] = litellm_name
    merged_env["COMPOSE_PROJECT_NAME"] = f"codefreedom-{suffix}"

    # Ensure the shared `codefreedom` bridge network exists (external network
    # referenced by docker-compose.yaml).  All proxy instances share this
    # network regardless of SUFFIX_ID.
    _ensure_codefreedom_network()

    litellm_image = merged_env.get("LITELLM_IMAGE", _DEFAULT_LITELLM_IMAGE)
    pull_if_stale(litellm_image, label="PROXY")

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
        eprint(
            f"{tag('PROXY')} Proxy started at http://localhost:{port}"
            f" ({litellm_name})"
        )
    else:
        eprint(f"{tag('PROXY')} Failed to start. Check docker logs.")
    return result.returncode


# ── Compose env helper ────────────────────────────────────────────────────────


def _build_compose_env() -> dict[str, str]:
    """Build the environment dict for docker compose subprocess calls.

    Loads proxy env files (same as ``_build_proxy_env``) and extracts
    ``COMPOSE_PROJECT_NAME`` from ``SUFFIX_ID`` so that ``stop``, ``restart``,
    and other compose commands target the same project that ``start`` created.
    """
    merged = _build_proxy_env()
    suffix = merged.get("SUFFIX_ID", "0000")
    merged["COMPOSE_PROJECT_NAME"] = f"codefreedom-{suffix}"
    return merged


# ── Stop ─────────────────────────────────────────────────────────────────────


def _stop() -> int:
    """Stop the LiteLLM proxy."""
    compose_file = _find_compose_file()
    if not compose_file:
        eprint(
            f"{tag('ERROR')} Could not find ~/.codefreedom/config/proxy/docker-compose.yaml"
        )
        eprint("   Run: cf s i")
        return 1

    eprint(f"{tag('PROXY')} Stopping LiteLLM proxy...")
    compose_env = _build_compose_env()
    result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "--profile", "litellm", "down"],
        env=compose_env,
        capture_output=False,
        timeout=60,
        check=False,
    )
    if result.returncode == 0:
        eprint(f"{tag('PROXY')} Proxy stopped.")
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
        eprint(
            f"{tag('ERROR')} Could not find ~/.codefreedom/config/proxy/docker-compose.yaml"
        )
        eprint("   Run: cf s i")
        return 1

    eprint(f"{tag('PROXY')} Restarting LiteLLM via Docker Compose ({compose_file})...")
    compose_env = _build_compose_env()
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
        env=compose_env,
        capture_output=False,
        timeout=60,
        check=False,
    )
    if result.returncode == 0:
        # Read port from env (resolved at build time, not /proc)
        merged_env = _build_proxy_env()
        port = merged_env.get("LITELLM_PORT", "4000")
        eprint(f"{tag('PROXY')} Proxy restarted at http://localhost:{port}")
    else:
        eprint(f"{tag('PROXY')} Failed to restart. Check docker logs.")
    return result.returncode


# ── Status ───────────────────────────────────────────────────────────────────


def _status() -> int:
    """Show LiteLLM proxy status."""
    compose_file = _find_compose_file()
    if not compose_file:
        eprint(
            f"{tag('ERROR')} Could not find ~/.codefreedom/config/proxy/docker-compose.yaml"
        )
        eprint("   Run: cf s i")
        return 1

    compose_env = _build_compose_env()
    result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "--profile", "litellm", "ps"],
        env=compose_env,
        capture_output=False,
        timeout=15,
        check=False,
    )
    return result.returncode


# ── Database URL check ───────────────────────────────────────────────────────

_DEFAULT_LITELLM_IMAGE = "docker.io/nilayparikh/codefreedom:litellm-latest"
_GHCR_LITELLM_IMAGE = "ghcr.io/nilayparikh/codefreedom:litellm-latest"


def _warn_database_url(
    in_config: bool,
    in_env: bool,
    proxy_env: Dict[str, str],
) -> None:
    """Check database_url and warn if it looks like the DB won't be available.

    The codefreedom litellm image ships an embedded PostgreSQL whose entrypoint
    auto-sets ``DATABASE_URL`` before launching LiteLLM.  Users of the default
    image get database features without setting anything on the host.

    Only warn when:
    - ``database_url`` is missing from both config.yaml *and* the host env,
      AND
    - ``LITELLM_IMAGE`` is overridden to a *non*-codefreedom image (meaning
      the embedded PG is not present).
    """
    if in_config or in_env:
        return  # database_url is explicitly configured — all good

    # Check which litellm image is in use
    litellm_image = proxy_env.get("LITELLM_IMAGE")
    if not litellm_image:
        litellm_image = os.environ.get("LITELLM_IMAGE")

    using_codefreedom_image = (
        litellm_image is None
        or _DEFAULT_LITELLM_IMAGE in litellm_image
        or _GHCR_LITELLM_IMAGE in litellm_image
        or "nilayparikh/codefreedom:litellm" in litellm_image
    )

    if using_codefreedom_image:
        eprint(
            "[PROXY] database_url not required — embedded PG in"
            " nilayparikh/codefreedom:litellm image auto-sets it."
        )
    else:
        eprint(f"{tag('PROXY')} Warning: database_url not set (stateless mode).")
        eprint("   LiteLLM runs without Prisma persistence unless DATABASE_URL is set.")
        eprint(
            "   The codefreedom litellm image (default) ships"
            " embedded PG that auto-sets it."
        )
        eprint(f"   You are using: {litellm_image}")


# ── Validate ─────────────────────────────────────────────────────────────────


def _validate_providers(
    config: dict, config_file: Path, proxy_env: dict, errors: list[str]
) -> None:
    """Validate provider include files and their model api_key references."""
    import yaml

    includes = config.get("include", [])
    if not includes:
        eprint(f"  {tag('WARN')}  No provider includes found in config.yaml")
        return

    config_dir = config_file.parent
    for inc in includes:
        provider_file = config_dir / inc
        if provider_file.exists():
            eprint(f"  {tag('OK')}  {inc}")
            try:
                with open(provider_file, encoding="utf-8") as f:
                    provider_config = yaml.safe_load(f)
                if provider_config is None:
                    eprint(f"    {tag('SKIP')}  (empty/commented out)")
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
                            eprint(
                                f"    {tag('OK')}  {name} (auth: {env_var} {tag('OK')})"
                            )
                    else:
                        eprint(f"    {tag('OK')}  {name}")
            except yaml.YAMLError as e:
                eprint(f"    {tag('FAIL')}  {inc}: YAML error -- {e}")
                errors.append(f"YAML error in {inc}: {e}")
        else:
            eprint(f"  {tag('FAIL')}  {inc} -- file not found")
            errors.append(f"Missing provider file: {inc}")


def _validate_settings(config: dict, proxy_env: dict, errors: list[str]) -> None:
    """Validate general_settings and router_settings."""
    general = config.get("general_settings", {})
    database_url_in_config = general.get("database_url")
    database_url_in_env = _env_is_set("DATABASE_URL", proxy_env)
    _warn_database_url(database_url_in_config, database_url_in_env, proxy_env)

    router = config.get("router_settings", {})
    aliases = router.get("model_group_alias", {})
    if aliases:
        eprint(f"  {tag('OK')}  Model aliases: {len(aliases)} defined")
        for alias, model in aliases.items():
            eprint(f"       {alias} -> {model}")
    else:
        eprint(f"  {tag('WARN')}  No model_group_alias defined")


def _validate() -> int:
    """Validate the LiteLLM configuration."""
    config_file = _find_config_file()
    if not config_file:
        eprint(
            f"{tag('ERROR')} Could not find ~/.codefreedom/config/proxy/config/config.yaml"
        )
        eprint("   Run: cf s i")
        return 1

    errors: List[str] = []

    eprint(f"{tag('PROXY')} Validating {config_file}...")
    eprint()

    proxy_env = _load_proxy_env_files()

    try:
        import yaml
    except ImportError:
        eprint(f"{tag('WARN')} PyYAML not installed. Using basic validation only.")
        eprint("   Install: pip install pyyaml")
        _validate_basic(config_file, errors)
        _print_validation_result(errors)
        return 0 if not errors else 1

    try:
        with open(config_file, encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        eprint(f"  {tag('FAIL')}  YAML parse error: {e}")
        return 1
    except FileNotFoundError:
        eprint(f"  {tag('FAIL')}  File not found: {config_file}")
        return 1

    if not isinstance(config, dict):
        eprint(f"  {tag('FAIL')}  Config must be a YAML dictionary.")
        return 1

    _validate_providers(config, config_file, proxy_env, errors)
    _validate_settings(config, proxy_env, errors)

    eprint()
    _print_validation_result(errors)
    return 0 if not errors else 1


def _validate_basic(config_file: Path, errors: List[str]) -> None:
    """Basic validation without PyYAML."""
    content = config_file.read_text(encoding="utf-8")
    checks = [
        ("include:", "provider includes"),
        ("general_settings:", "general_settings section"),
        ("router_settings:", "router_settings section"),
        ("litellm_settings:", "litellm_settings section"),
        ("model_group_alias:", "model aliases"),
    ]
    for marker, label in checks:
        if marker in content:
            eprint(f"  {tag('OK')}  {label} found")
        else:
            eprint(f"  {tag('FAIL')}  {label} missing")
            errors.append(f"Missing: {label}")

    config_dir = config_file.parent
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("- providers/"):
            provider_file = line[2:].strip()
            full = config_dir / provider_file
            if full.exists():
                eprint(f"  {tag('OK')}  {provider_file}")
            else:
                eprint(f"  {tag('FAIL')}  {provider_file} -- not found")
                errors.append(f"Missing: {provider_file}")


def _env_is_set(var_name: str, env: Optional[Dict[str, str]] = None) -> bool:
    """Check if an environment variable is set (including empty strings).

    Checks (in priority order):
    1. *env* dict (from .env files)
    2. ``CF_CLI_<var_name>`` in ``os.environ`` (machine override)
    3. ``var_name`` directly in ``os.environ``
    """
    if env is not None and var_name in env:
        return True
    cf_cli_key = f"CF_CLI_{var_name}"
    if cf_cli_key in os.environ:
        return True
    return var_name in os.environ


def _print_validation_result(errors: List[str]) -> None:
    """Print validation summary."""
    if errors:
        eprint(f"  {tag('FAIL')}  {len(errors)} issue(s) found.")
        for e in errors:
            eprint(f"       - {e}")
    else:
        eprint(f"  {tag('OK')}  Configuration looks good!")


# VS Code config generation moved to codefreedom.cli.vscode.
