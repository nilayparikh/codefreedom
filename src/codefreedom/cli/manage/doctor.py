"""Doctor subcommand -- comprehensive CodeFreedom diagnostic check.

Usage:
    codefreedom doctor [--verbose]

Checks the full CodeFreedom environment for issues that could prevent
normal operation, including:

  - Config directory structure (``~/.codefreedom/``)
  - Docker CLI availability and daemon responsiveness
  - Essential config, env, and profile files
  - Proxy compose file and PostgreSQL data directory permissions
  - Tool profiles (chrome, web, github)
  - Docker image availability
  - Environment variable presence
  - Sandbox directory readiness
  - Port availability for tool and proxy services

Designed to catch issues like the PostgreSQL ``initdb`` permission error:
"could not change permissions of directory /var/lib/postgresql/data"
"""

from __future__ import annotations

import os
import sys
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from codefreedom.cli.docker_utils import (
    get_codefreedom_container_ports,
    is_port_available,
)
from codefreedom.core.config import get_codefreedom_dir
from codefreedom.env_loader import load_dotenv

# ═══════════════════════════════════════════════════════════════════════════════
# Check result types
# ═══════════════════════════════════════════════════════════════════════════════


class CheckResult:
    """Result of a single diagnostic check."""

    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"

    def __init__(self, status: str, message: str, detail: str = "") -> None:
        self.status = status
        self.message = message
        self.detail = detail

    def __bool__(self) -> bool:
        return self.status == self.PASS


def _ok(msg: str, detail: str = "") -> CheckResult:
    return CheckResult(CheckResult.PASS, msg, detail)


def _fail(msg: str, detail: str = "") -> CheckResult:
    return CheckResult(CheckResult.FAIL, msg, detail)


def _warn(msg: str, detail: str = "") -> CheckResult:
    return CheckResult(CheckResult.WARN, msg, detail)


def _skip(msg: str, detail: str = "") -> CheckResult:
    return CheckResult(CheckResult.SKIP, msg, detail)


# ═══════════════════════════════════════════════════════════════════════════════
# Check registry
# ═══════════════════════════════════════════════════════════════════════════════

CheckFn = Callable[[], CheckResult]

_SECTIONS: List[Tuple[str, List[CheckFn]]] = []


def _section(name: str) -> Callable[[CheckFn], CheckFn]:
    """Decorator that registers a check function under a named section."""

    def wrapper(fn: CheckFn) -> CheckFn:
        # Find or create section
        for section_name, checks in _SECTIONS:
            if section_name == name:
                checks.append(fn)
                return fn
        _SECTIONS.append((name, [fn]))
        return fn

    return wrapper


def _clear_checks() -> None:
    """Clear all registered checks (for testing)."""
    _SECTIONS.clear()


def _run_checks(verbose: bool = False) -> Tuple[int, int, int]:
    """Run all registered checks and print results.

    Returns (pass_count, fail_count, warn_count).
    """
    passed = 0
    failed = 0
    warned = 0

    for section_name, checks in _SECTIONS:
        print(f"\n  [{section_name}]")
        for check_fn in checks:
            try:
                result = check_fn()
            except Exception as e:
                result = _fail(f"Exception: {e}")

            icon = _status_icon(result.status)
            print(f"    {icon} {result.message}")
            if verbose and result.detail:
                for line in result.detail.split("\n"):
                    print(f"         {line}")
            if result.status == CheckResult.PASS:
                passed += 1
            elif result.status == CheckResult.FAIL:
                failed += 1
            elif result.status == CheckResult.WARN:
                warned += 1

    return passed, failed, warned


def _status_icon(status: str) -> str:
    """Return a colored status icon."""
    if status == CheckResult.PASS:
        return "[OK]"
    elif status == CheckResult.FAIL:
        return "[FAIL]"
    elif status == CheckResult.WARN:
        return "[WARN]"
    else:
        return "[SKIP]"


# ═══════════════════════════════════════════════════════════════════════════════
# Individual checks
# ═══════════════════════════════════════════════════════════════════════════════


# ── Section: CodeFreedom Home ─────────────────────────────────────────────


@_section("CodeFreedom Home")
def _check_cf_dir_exists() -> CheckResult:
    cf_dir = get_codefreedom_dir()
    if cf_dir.exists():
        return _ok(f"{cf_dir} exists")
    return _fail(f"{cf_dir} does not exist -- run 'cf init'")


@_section("CodeFreedom Home")
def _check_recipe_instruction() -> CheckResult:
    cf_dir = get_codefreedom_dir()
    recipe_file = cf_dir / "RECIPE.md"
    if recipe_file.exists():
        content = recipe_file.read_text(encoding="utf-8")
        # Extract recipe name from the first line
        for line in content.splitlines():
            if line.startswith("# CodeFreedom Recipe:"):
                recipe_name = line.split(":", 1)[1].strip()
                return _ok(f"Recipe installed: {recipe_name}")
        return _ok("RECIPE.md found")
    return _skip(
        "No RECIPE.md — run 'cf init' to install a recipe and download one"
    )


@_section("CodeFreedom Home")
def _check_cf_dir_permissions() -> CheckResult:
    cf_dir = get_codefreedom_dir()
    if not cf_dir.exists():
        return _skip("(directory does not exist)")
    if os.access(cf_dir, os.R_OK | os.W_OK | os.X_OK):
        return _ok(f"{cf_dir} is readable, writable, and searchable")
    return _fail(f"{cf_dir} has incorrect permissions")


@_section("CodeFreedom Home")
def _check_cf_dir_structure() -> CheckResult:
    """Check that key subdirectories exist."""
    cf_dir = get_codefreedom_dir()
    expected_dirs = ["profiles", "proxy", "proxy/config"]
    missing = []
    for sub in expected_dirs:
        if not (cf_dir / sub).is_dir():
            missing.append(sub)
    if missing:
        return _warn(
            f"Missing subdirectories: {', '.join(missing)}",
            "Run 'cf init' to create them",
        )
    return _ok("All key subdirectories present")


# ── Section: Docker ────────────────────────────────────────────────────────


@_section("Docker")
def _check_docker_cli() -> CheckResult:
    if shutil.which("docker"):
        return _ok("Docker CLI found in PATH")
    return _fail(
        "Docker CLI not found in PATH",
        "Install Docker: https://docs.docker.com/engine/install/",
    )


@_section("Docker")
def _check_docker_daemon() -> CheckResult:
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            return _ok(f"Docker daemon running (server v{result.stdout.strip()})")
        return _fail("Docker daemon not running", f"  {result.stderr.strip()}")
    except FileNotFoundError:
        return _skip("(Docker CLI not available)")
    except subprocess.TimeoutExpired:
        return _fail("Docker daemon not responding (timeout)")


@_section("Docker")
def _check_docker_compose() -> CheckResult:
    for candidate in ["docker compose", "docker-compose"]:
        try:
            cmd = candidate.split()
            result = subprocess.run(
                [*cmd, "version", "--short"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0:
                return _ok(f"{candidate} available ({result.stdout.strip()})")
        except FileNotFoundError:
            continue
    return _fail(
        "Docker Compose not found",
        "Install Docker Compose: https://docs.docker.com/compose/install/",
    )


# ── Section: Config Files ─────────────────────────────────────────────────


def _resolve_tool_home() -> Path:
    """Return the tool home directory (~/.codefreedom, overridable for tests)."""
    override = os.environ.get("CODEFREEDOM_TOOL_HOME")
    if override:
        return Path(override)
    return Path.home() / ".codefreedom"


ESSENTIAL_ENV_FILES = [
    (".env.claude", "Claude Code config"),
    (".env.claude.secrets", "Claude Code secrets"),
    (".env.proxy", "Proxy config"),
    (".env.proxy.secrets", "Proxy secrets"),
]

ESSENTIAL_PROFILE_FILES = [
    ("profiles/chrome.yaml", "Chrome tool profile"),
    ("profiles/web.yaml", "Web search tool profile"),
    ("profiles/github.yaml", "GitHub MCP tool profile"),
]

ESSENTIAL_PROXY_FILES = [
    ("proxy/docker-compose.yaml", "Docker Compose file"),
    ("proxy/config/config.yaml", "LiteLLM config"),
]


@_section("Config Files")
def _check_env_files() -> CheckResult:
    cf_dir = get_codefreedom_dir()
    missing = []
    for rel_path, label in ESSENTIAL_ENV_FILES:
        if not (cf_dir / rel_path).exists():
            missing.append(f"{label} ({rel_path})")
    if missing:
        return _warn(
            f"Missing env files: {', '.join(missing)}",
            "Run 'cf init' to create defaults",
        )
    return _ok("All essential env files present")


@_section("Config Files")
def _check_profile_files() -> CheckResult:
    # Tool profiles always live in ~/.codefreedom/profiles/ (shared across
    # all projects).  Other profiles (claude-code, etc.) live under
    # CODEFREEDOM_HOME / get_codefreedom_dir().
    tool_home = _resolve_tool_home()
    missing = []
    for rel_path, label in ESSENTIAL_PROFILE_FILES:
        if not (tool_home / rel_path).exists():
            missing.append(f"{label} ({rel_path})")
    if missing:
        return _warn(
            f"Missing profile files: {', '.join(missing)}",
            "Run 'cf init' to create defaults",
        )
    return _ok("All essential profile files present")


@_section("Config Files")
def _check_proxy_config_files() -> CheckResult:
    cf_dir = get_codefreedom_dir()
    missing = []
    for rel_path, label in ESSENTIAL_PROXY_FILES:
        if not (cf_dir / rel_path).exists():
            missing.append(f"{label} ({rel_path})")
    if missing:
        return _fail(
            f"Missing proxy files: {', '.join(missing)}",
            "Run 'cf init' to create them",
        )
    return _ok("All essential proxy config files present")


@_section("Config Files")
def _check_claude_code_profile() -> CheckResult:
    """Check claude-code profile (legacy .json or new .yaml name)."""
    cf_dir = get_codefreedom_dir()
    candidates = [
        cf_dir / "profiles" / "claude-code.json",
        cf_dir / "profiles" / "claude-code.yaml",
        cf_dir / "profiles" / "claude-code-profiles.yaml",
    ]
    found = [p for p in candidates if p.exists()]
    if found:
        return _ok(f"Claude Code profile found: {found[0].name}")
    return _warn(
        "No Claude Code profile file found",
        "Looked for: claude-code.json, claude-code.yaml, claude-code-profiles.yaml",
    )


# ── Section: PostgreSQL / Proxy Data ───────────────────────────────────────


@_section("PostgreSQL / Proxy Data")
def _check_pg_data_dir() -> CheckResult:
    """Check the PostgreSQL data directory that gets mounted into LiteLLM.

    The LiteLLM container runs as the ``codefreedom`` user (uid 1000).
    If the host-mounted directory is owned by root or has restricted
    permissions, ``initdb`` will fail with the classic:

        initdb: error: could not change permissions of directory ...
    """
    cf_dir = get_codefreedom_dir()
    pg_data = cf_dir / "pg" / "data"

    if not pg_data.exists():
        # Directory will be auto-created by Docker; nothing to check yet.
        # But check its parent is writable.
        parent = pg_data.parent
        if not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)
        if os.access(parent, os.W_OK):
            return _ok(f"{pg_data} will be created on first proxy start")
        return _fail(
            f"{pg_data.parent} is not writable",
            "Fix: chmod your home directory or set POSTGRES_HOST_DATA_DIR",
        )
    else:
        # Directory exists — check ownership and permissions
        st = os.stat(pg_data)
        uid = st.st_uid
        mode = st.st_mode

        # The container runs as the 'codefreedom' user which typically
        # has uid 1000 inside the container. If the host uid maps to
        # something else, check if the directory is world-writable or
        # if the uid matches the host user running CodeFreedom.
        if sys.platform != "win32":
            host_uid = os.getuid()
        else:
            host_uid = None

        issues = []
        if host_uid is not None:
            if uid != host_uid and uid != 1000:
                issues.append(
                    f"owned by uid {uid} (container expects uid 1000 or your uid {host_uid})"
                )
            if not (mode & stat.S_IWOTH or mode & stat.S_IWUSR or uid == host_uid):
                issues.append("not writable by the container's user")
        else:
            if not (mode & stat.S_IWOTH or mode & stat.S_IWUSR):
                issues.append("not writable")

        if issues:
            fix = (
                f"Fix: sudo chown -R {host_uid} {pg_data}  OR  sudo chmod -R 777 {pg_data}"
                if host_uid is not None
                else "Fix: adjust directory permissions"
            )
            return _fail(
                f"{pg_data}: {'; '.join(issues)}",
                fix,
            )
        return _ok(f"{pg_data} is ready (uid {uid}, mode {oct(mode & 0o777)})")


@_section("PostgreSQL / Proxy Data")
def _check_pg_backup_dir() -> CheckResult:
    cf_dir = get_codefreedom_dir()
    pg_backup = cf_dir / "pg" / "backup"
    if not pg_backup.exists():
        return _ok(f"{pg_backup} will be created on first proxy start")
    if os.access(pg_backup, os.W_OK):
        return _ok(f"{pg_backup} is writable")
    return _fail(f"{pg_backup} is not writable", "Fix: chmod the directory")


@_section("PostgreSQL / Proxy Data")
def _check_compose_pg_volume() -> CheckResult:
    """Parse the compose file and check POSTGRES_HOST_DATA_DIR consistency."""
    cf_dir = get_codefreedom_dir()
    compose_file = cf_dir / "proxy" / "docker-compose.yaml"

    if not compose_file.exists():
        return _skip("(compose file not found)")

    try:
        import yaml

        with open(compose_file, encoding="utf-8") as f:
            compose = yaml.safe_load(f)
    except Exception:
        return _skip("(could not parse compose file)")

    if not isinstance(compose, dict):
        return _skip("(compose file is not a mapping)")

    services = compose.get("services", {})
    litellm = services.get("litellm", {})
    volumes = litellm.get("volumes", [])

    pg_mount = None
    for vol in volumes:
        if "postgresql/data" in str(vol):
            pg_mount = vol
            break

    if pg_mount is None:
        return _warn("No PostgreSQL data volume mount found in compose file")

    # Parse the host part of the volume spec
    env_override = os.environ.get("POSTGRES_HOST_DATA_DIR", "")

    if env_override:
        resolved = Path(env_override)
        if resolved.exists():
            if os.access(resolved, os.W_OK):
                return _ok(f"POSTGRES_HOST_DATA_DIR={env_override} is writable")
            return _fail(f"POSTGRES_HOST_DATA_DIR={env_override} is not writable")
        else:
            parent = resolved.parent
            if parent.exists() and os.access(parent, os.W_OK):
                return _ok(f"POSTGRES_HOST_DATA_DIR={env_override} (will be created)")
            return _fail(f"POSTGRES_HOST_DATA_DIR parent {parent} is not writable")

    return _ok("POSTGRES_HOST_DATA_DIR not overridden (compose default will be used)")


# ── Section: Docker Images ─────────────────────────────────────────────────


ESSENTIAL_IMAGES: List[Tuple[str, str, str]] = [
    ("proxy", "LiteLLM proxy", "docker.io/nilayparikh/codefreedom:litellm-latest"),
]


@_section("Docker Images")
def _check_litellm_image() -> CheckResult:
    return _check_image_available(
        "docker.io/nilayparikh/codefreedom:litellm-latest", "LiteLLM proxy"
    )


@_section("Docker Images")
def _check_web_bridge_image() -> CheckResult:
    return _check_image_available(
        "docker.io/nilayparikh/codefreedom:web-bridge", "Web search bridge"
    )


def _check_image_available(image: str, label: str) -> CheckResult:
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            return _ok(f"{label} image '{image}' is cached locally")
        return _warn(
            f"{label} image '{image}' not found locally",
            "Will be pulled on first 'cf proxy start'",
        )
    except FileNotFoundError:
        return _skip("(Docker CLI not available)")


# ── Section: Tool Profiles ─────────────────────────────────────────────────


@_section("Tool Profiles")
def _check_chrome_profile() -> CheckResult:
    return _check_tool_profile("chrome", "Chrome browser")


@_section("Tool Profiles")
def _check_web_profile() -> CheckResult:
    return _check_tool_profile("web", "Web search (Camoufox)")


@_section("Tool Profiles")
def _check_github_profile() -> CheckResult:
    return _check_tool_profile("github", "GitHub MCP")


def _check_tool_profile(name: str, label: str) -> CheckResult:
    cf_dir = get_codefreedom_dir()
    profile_file = cf_dir / "profiles" / f"{name}.json"
    if not profile_file.exists():
        profile_file = cf_dir / "profiles" / f"{name}.yaml"

    if not profile_file.exists():
        return _warn(
            f"{label} profile not found",
            f"Run 'cf tools {name} init' or 'cf init' to create it",
        )

    try:
        import json
        import yaml

        if profile_file.suffix == ".json":
            with open(profile_file, encoding="utf-8") as f:
                json.load(f)
        else:
            with open(profile_file, encoding="utf-8") as f:
                yaml.safe_load(f)
        return _ok(f"{label} profile is valid ({profile_file.name})")
    except (json.JSONDecodeError, yaml.YAMLError) as e:
        return _fail(f"{label} profile has parse errors: {e}")


# ── Section: Env Vars (Proxy) ──────────────────────────────────────────────


def _resolve_env_var_value(
    name: str,
    env_files: Optional[List[Path]] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Resolve an env var value across all sources.

    Checks (in priority order):
    1. ``CF_CLI_<NAME>`` in ``os.environ`` (highest priority machine override)
    2. ``NAME`` directly in ``os.environ``
    3. ``NAME=`` in the provided *env_files*

    Returns ``(value, source_description)`` or ``(None, None)`` if not found
    in any source.
    """
    # 1. CF_CLI_* override (highest priority — beats everything)
    cf_cli_name = f"CF_CLI_{name}"
    if cf_cli_name in os.environ and os.environ[cf_cli_name]:
        return os.environ[cf_cli_name], f"CF_CLI_{cf_cli_name} (machine env override)"

    # 2. Direct env var
    if name in os.environ and os.environ[name]:
        return os.environ[name], f"{name} (machine env)"

    # 3. Env files
    if env_files:
        for env_file in env_files:
            if env_file.exists():
                content = env_file.read_text(encoding="utf-8")
                for line in content.splitlines():
                    if line.strip().startswith(f"{name}="):
                        val = line.split("=", 1)[1].strip()
                        if val and val != "CHANGE_ME":
                            return val, f"{name} (in {env_file.name})"

    return None, None


@_section("Environment Variables (Proxy)")
def _check_litellm_master_key() -> CheckResult:
    return _check_env_var(
        "LITELLM_MASTER_KEY", "Proxy master key", ".env.proxy.secrets"
    )


def _check_env_var(name: str, label: str, source_hint: str) -> CheckResult:
    """Check that an env var is set across all sources (env, CF_CLI_*, files).

    Uses :func:`_resolve_env_var_value` for a single code path that considers
    ``CF_CLI_*`` machine overrides, direct ``os.environ``, and env files.
    """
    cf_dir = get_codefreedom_dir()
    env_files = [cf_dir / ".env.proxy", cf_dir / ".env.proxy.secrets"]
    value, source = _resolve_env_var_value(name, env_files=env_files)
    if value is not None:
        return _ok(f"{name} is set ({label})")
    return _fail(
        f"{name} is not set ({label})",
        f"Set it in {source_hint} or export CF_CLI_{name}=... in your shell",
    )


def _check_env_var_optional(name: str, label: str, _source_hint: str) -> CheckResult:
    """Check an optional env var across all sources (env, CF_CLI_*, files).

    Uses :func:`_resolve_env_var_value` for a single code path that considers
    ``CF_CLI_*`` machine overrides, direct ``os.environ``, and env files.
    """
    cf_dir = get_codefreedom_dir()
    env_files = [cf_dir / ".env.proxy", cf_dir / ".env.proxy.secrets"]
    value, source = _resolve_env_var_value(name, env_files=env_files)
    if value is not None:
        return _ok(f"{name} is set ({label})")
    return _skip(f"{name} is not set (optional — {label})")


# ── Section: Env Vars (Claude) ────────────────────────────────────────────


@_section("Environment Variables (Claude)")
def _check_anthropic_base_url() -> CheckResult:
    return _check_env_var_optional(
        "ANTHROPIC_BASE_URL",
        "Anthropic API base URL (optional if using proxy)",
        ".env.claude or .env.claude.secrets",
    )


@_section("Environment Variables (Claude)")
def _check_anthropic_auth_token() -> CheckResult:
    return _check_env_var_optional(
        "ANTHROPIC_AUTH_TOKEN",
        "Anthropic auth token (optional if using proxy)",
        ".env.claude.secrets",
    )


# ── Section: Sandbox ────────────────────────────────────────────────────────


@_section("Sandbox")
def _check_sandbox_dir() -> CheckResult:
    cf_dir = get_codefreedom_dir()
    sandbox_default = cf_dir / "sandbox" / "default"
    if not sandbox_default.exists():
        return _ok(f"{sandbox_default} will be created on first sandbox run")
    return _ok(f"{sandbox_default} exists")


@_section("Sandbox")
def _check_sandbox_profiles() -> CheckResult:
    cf_dir = get_codefreedom_dir()
    profile_file = cf_dir / "profiles" / "claude-code.json"
    if not profile_file.exists():
        return _skip("(no claude-code profile to check sandbox settings)")

    try:
        import json

        with open(profile_file, encoding="utf-8") as f:
            profiles = json.load(f)
        profiles_list = profiles.get("profiles", {})
        for pname, pdata in profiles_list.items():
            if isinstance(pdata, dict) and "sandbox_images" in pdata:
                return _ok(f"Profile '{pname}' has sandbox image configuration")
        return _skip("(no sandbox images configured in profiles)")
    except (json.JSONDecodeError, OSError):
        return _skip("(could not read profile)")


# ── Section: Proxy Status ──────────────────────────────────────────────────


@_section("Proxy Status")
def _check_proxy_running() -> CheckResult:
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=litellm", "--format", "{{.Status}}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        status = result.stdout.strip()
        if status:
            return _ok(f"LiteLLM container is running ({status})")
        return _warn(
            "LiteLLM container is not running", "Start it with: cf proxy start"
        )
    except FileNotFoundError:
        return _skip("(Docker CLI not available)")


@_section("Proxy Status")
def _check_web_bridge_running() -> CheckResult:
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=web-bridge", "--format", "{{.Status}}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        status = result.stdout.strip()
        if status:
            return _ok(f"Web-bridge container is running ({status})")
        return _warn(
            "Web-bridge container is not running", "Start it with: cf proxy start"
        )
    except FileNotFoundError:
        return _skip("(Docker CLI not available)")


# ── Section: Port Availability ──────────────────────────────────────────────


@_section("Port Availability")
def _check_chrome_cdp_port() -> CheckResult:
    return _check_port(
        9222, "Chrome CDP", "~/.codefreedom/profiles/chrome.yaml (chrome.port)"
    )


@_section("Port Availability")
def _check_chrome_mcp_port() -> CheckResult:
    return _check_port(
        9223, "Chrome MCP", "~/.codefreedom/profiles/chrome.yaml (chrome.mcp_port)"
    )


@_section("Port Availability")
def _check_web_port() -> CheckResult:
    return _check_port(
        8420, "Web search (Camoufox)", "~/.codefreedom/profiles/web.yaml (web.port)"
    )


@_section("Port Availability")
def _check_proxy_port() -> CheckResult:
    # Read LITELLM_PORT from the .env.proxy file, fall back to 4000
    codefreedom_dir = get_codefreedom_dir()
    env_proxy = codefreedom_dir / ".env.proxy"
    proxy_env = load_dotenv(env_proxy)
    port_str = proxy_env.get("LITELLM_PORT", "4000")
    try:
        port = int(port_str)
    except (ValueError, TypeError):
        port = 4000
    return _check_port(
        port, "LiteLLM proxy", "~/.codefreedom/.env.proxy (LITELLM_PORT)"
    )


def _check_port(port: int, label: str, config_hint: str) -> CheckResult:
    """Check if a TCP port is available for binding.

    If the port is in use but belongs to a known CodeFreedom container
    (e.g. Chrome, Web, proxy), it is reported as OK rather than a
    warning — our own tools are expected to listen on those ports.
    """
    if is_port_available(port):
        return _ok(f"Port {port} ({label}) is available")

    cf_ports = get_codefreedom_container_ports()
    if port in cf_ports:
        tool_label = _cf_tool_label_for_port(port)
        if tool_label:
            return _ok(
                f"Port {port} ({label}) — in use by {tool_label} (CodeFreedom container)"
            )
        return _ok(f"Port {port} ({label}) — in use by a CodeFreedom container")

    return _warn(
        f"Port {port} ({label}) is already in use",
        f"Change the port in: {config_hint}",
    )


# Map of well-known tool ports to friendly labels for doctor output.
_CF_TOOL_PORT_LABELS: dict[int, str] = {
    9222: "Chrome browser",
    9223: "Chrome MCP",
    8420: "Web search (Camoufox)",
}


def _cf_tool_label_for_port(port: int) -> str | None:
    """Return a friendly label for a well-known CodeFreedom tool port."""
    return _CF_TOOL_PORT_LABELS.get(port)


# ═══════════════════════════════════════════════════════════════════════════════
# Agent Prerequisites
# ═══════════════════════════════════════════════════════════════════════════════


@_section("Agent Prerequisites")
def _check_claude_binary() -> CheckResult:
    claude = shutil.which("claude")
    if claude:
        return _ok(f"Claude CLI found ({claude})")
    return _warn(
        "Claude CLI not found",
        "Install: npm install -g @anthropic-ai/claude-code",
    )


@_section("Agent Prerequisites")
def _check_mimo_binary() -> CheckResult:
    mimo = shutil.which("mimo")
    if mimo:
        return _ok(f"MiMoCode CLI found ({mimo})")
    return _warn("MiMoCode CLI not found", "See MiMoCode documentation")


@_section("Agent Prerequisites")
def _check_opencode_binary() -> CheckResult:
    opencode = shutil.which("opencode")
    if opencode:
        return _ok(f"OpenCode CLI found ({opencode})")
    return _warn("OpenCode CLI not found", "See OpenCode documentation")


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════


def run(verbose: bool = False) -> int:
    """Run the full doctor diagnostic suite.

    Args:
        verbose: Show detail messages for all checks (not just failures).

    Returns:
        Exit code: 0 if all checks pass, 1 if any failures, 2 if any failures
        plus warnings.
    """
    print()
    print(f"  CodeFreedom Doctor — {get_codefreedom_dir()}")
    print("  " + "=" * 55)

    passed, failed, warned = _run_checks(verbose=verbose)

    print()
    if failed == 0 and warned == 0:
        print(f"  [OK] All {passed} checks passed. Your setup looks good!")
    elif failed == 0:
        print(f"  [OK] {passed} passed, {warned} warnings — review items above.")
    else:
        print(f"  [FAIL] {failed} failure(s), {warned} warning(s), {passed} passed.")

    print()
    return 0 if failed == 0 else (2 if warned > 0 else 1)
