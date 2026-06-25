"""Doctor subcommand -- comprehensive CodeFreedom diagnostic check.

Usage:
    codefreedom manage doctor [--verbose]

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
import shutil
import subprocess
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from codefreedom.cli.docker_utils import (
    get_codefreedom_container_ports,
    is_port_available,
    load_tool_profile,
)
from codefreedom.core.config import get_codefreedom_dir, get_config_dir
from codefreedom.core.settings import resolve_config_value

# ═══════════════════════════════════════════════════════════════════════════════
# Check result types
# ═══════════════════════════════════════════════════════════════════════════════


class CheckResult:
    """Result of a single diagnostic check."""

    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    INFO = "INFO"
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


def _info(msg: str, detail: str = "") -> CheckResult:
    return CheckResult(CheckResult.INFO, msg, detail)


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
    from codefreedom.log import bold, cyan

    passed = 0
    failed = 0
    warned = 0

    for section_name, checks in _SECTIONS:
        print(f"\n  {cyan(bold(f'[{section_name}]'))}")
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
    from codefreedom.log import bold, cyan, green, red, yellow

    if status == CheckResult.PASS:
        return green("[OK]")
    elif status == CheckResult.FAIL:
        return red(bold("[FAIL]"))
    elif status == CheckResult.WARN:
        return yellow("[WARN]")
    elif status == CheckResult.INFO:
        return cyan("[INFO]")
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
    return _fail(f"{cf_dir} does not exist -- run 'cf s i'")


@_section("CodeFreedom Home")
def _check_recipe_instruction() -> CheckResult:
    from codefreedom.core.config import get_config_dir

    config_dir = get_config_dir()
    recipe_file = config_dir / "RECIPE.md"
    if recipe_file.exists():
        content = recipe_file.read_text(encoding="utf-8")
        # Extract recipe name from the first line
        for line in content.splitlines():
            if line.startswith("# CodeFreedom Recipe:"):
                recipe_name = line.split(":", 1)[1].strip()
                return _ok(f"Recipe installed: {recipe_name}")
        return _ok("RECIPE.md found")
    return _skip("No RECIPE.md — run 'cf s i' to install a recipe and download one")


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
    """Check that key subdirectories exist in config directory."""
    from codefreedom.core.config import get_config_dir

    config_dir = get_config_dir()
    expected_dirs = ["proxy", "proxy/config"]
    missing = []
    for sub in expected_dirs:
        if not (config_dir / sub).is_dir():
            missing.append(sub)
    if missing:
        return _warn(
            f"Missing config subdirectories: {', '.join(missing)}",
            "Run 'cf s i' to create them",
        )
    return _ok("All config subdirectories present")


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


def _load_tool_settings(
    tool_key: str,
    profile_filename: str,
    defaults: dict,
    extra_keys: list[str] | None = None,
) -> dict:
    """Load tool settings from profile, falling back to defaults.

    Uses the same ``load_tool_profile()`` that tool modules use, so
    doctor checks always reflect the actual configured values.
    """
    try:
        return load_tool_profile(
            tool_key,
            defaults,
            profile_filename,
            extra_keys=extra_keys,
        )
    except Exception:
        return defaults


def _get_chrome_settings() -> dict:
    return _load_tool_settings(
        "chrome",
        "chrome.yaml",
        {
            "image": "docker.io/nilayparikh/codefreedom:chrome-latest",
            "container_name": "codefreedom-chrome",
            "port": 9222,
            "mcp_port": 9223,
            "mcp_path": "/mcp",
            "cdp_proxy_port": 9220,
            "data_dir": "",
            "env": {},
        },
        extra_keys=["mcp_port", "mcp_path", "cdp_proxy_port"],
    )


def _get_web_settings() -> dict:
    return _load_tool_settings(
        "web",
        "web.yaml",
        {
            "image": "docker.io/nilayparikh/codefreedom:web-latest",
            "container_name": "codefreedom-web",
            "port": 8420,
            "data_dir": "",
            "env": {},
        },
    )


def _get_github_settings() -> dict:
    return _load_tool_settings(
        "github",
        "github.yaml",
        {
            "image": "docker.io/nilayparikh/codefreedom:github-latest",
            "container_name": "codefreedom-tools-github",
            "port": 8129,
            "data_dir": "",
            "env": {},
        },
    )


def _get_web_bridge_settings() -> dict:
    return _load_tool_settings(
        "web_bridge",
        "web-bridge.yaml",
        {
            "image": "docker.io/nilayparikh/codefreedom:web-bridge-latest",
            "container_name": "codefreedom-web-bridge",
            "port": 8500,
            "data_dir": "",
            "env": {},
        },
    )


ESSENTIAL_PROFILE_FILES = [
    "profiles.yaml",  # Unified profiles file
]

ESSENTIAL_PROXY_FILES = [
    ("proxy/docker-compose.yaml", "Docker Compose file"),
    ("proxy/config/config.yaml", "LiteLLM config"),
]


@_section("Config Files")
def _check_profile_files() -> CheckResult:
    from codefreedom.core.config import get_config_dir

    config_dir = get_config_dir()
    discovered = sorted(p.name for p in config_dir.glob("*.yaml") if p.is_file())
    missing = [f for f in ESSENTIAL_PROFILE_FILES if f not in discovered]
    if missing:
        return _warn(
            f"Missing profile files: {', '.join(missing)}",
            "Run 'cf s i' to create defaults",
        )
    return _ok(
        f"All essential profile files present ({len(discovered)} profile(s) found)"
    )


@_section("Config Files")
def _check_proxy_config_files() -> CheckResult:
    config_dir = get_config_dir()
    missing = []
    for rel_path, label in ESSENTIAL_PROXY_FILES:
        if not (config_dir / rel_path).exists():
            missing.append(f"{label} ({rel_path})")
    if missing:
        return _fail(
            f"Missing proxy files: {', '.join(missing)}",
            "Run 'cf s i' to create them",
        )
    return _ok("All essential proxy config files present")


@_section("Config Files")
def _check_claude_code_profile() -> CheckResult:
    """Check claude-code profile (unified profiles.yaml)."""
    from codefreedom.core.config import get_config_dir

    config_dir = get_config_dir()
    candidates = [
        config_dir / "profiles.yaml",
    ]
    found = [p for p in candidates if p.exists()]
    if found:
        return _ok(f"Claude Code profile found: {found[0].name}")
    return _warn(
        "No Claude Code profile file found",
        "Run 'cf s i' to install a recipe",
    )


# ── Section: PostgreSQL / Proxy Data ───────────────────────────────────────


@_section("PostgreSQL / Proxy Data")
def _check_pg_data_dir() -> CheckResult:
    """Check the PostgreSQL data volume strategy.

    PG data uses a Docker named volume (codefreedom_pg_data) instead of
    a host bind-mount, avoiding permission issues on Windows/macOS/Linux.
    """
    return _ok(
        "PG data uses Docker named volume 'codefreedom_pg_data' (no host dir needed)"
    )


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
    """Check that the PG data named volume exists."""
    result = subprocess.run(
        ["docker", "volume", "inspect", "codefreedom_pg_data"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode == 0:
        return _ok("Named volume 'codefreedom_pg_data' exists")
    return _ok(
        "Named volume 'codefreedom_pg_data' will be created on first proxy start"
    )


# ── Section: Docker Images ─────────────────────────────────────────────────


def _get_litellm_image() -> str:
    """Return the LiteLLM image from env or compose default."""
    return os.environ.get(
        "LITELLM_IMAGE", "docker.io/nilayparikh/codefreedom:litellm-latest"
    )


def _get_litellm_container_name() -> str:
    """Return the LiteLLM container name from env or compose default."""
    return os.environ.get("LITELLM_CONTAINER_NAME", "litellm-codefreedom")


@_section("Docker Images")
def _check_litellm_image() -> CheckResult:
    return _check_image_available(_get_litellm_image(), "LiteLLM proxy")


@_section("Docker Images")
def _check_web_bridge_image() -> CheckResult:
    settings = _get_web_bridge_settings()
    return _check_image_available(settings["image"], "Web search bridge")


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
        return _info(
            f"{label} image '{image}' not found locally",
            "Will be pulled on first 'cf run proxy start'",
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
    from codefreedom.core.config import get_config_dir

    config_dir = get_config_dir()
    profiles_path = config_dir / "profiles.yaml"

    if not profiles_path.exists():
        return _warn(
            f"{label} profile not found (no profiles.yaml)",
            "Run 'cf s i' to install a recipe",
        )

    try:
        import yaml

        with open(profiles_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return _fail("profiles.yaml is not a valid mapping")
        tools = data.get("tools", {})
        if name in tools:
            return _ok(f"{label} profile found in profiles.yaml (tools.{name})")
        return _warn(
            f"{label} profile not found in profiles.yaml",
            f"Run 'cf s i' to install a recipe with {name} config",
        )
    except (yaml.YAMLError, OSError) as e:
        return _fail(f"profiles.yaml has parse errors: {e}")


# ── Section: Env Vars (Proxy) ──────────────────────────────────────────────


def _resolve_env_var_value(
    name: str,
    env_files: list[Path] | None = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Resolve an env var value from machine environment variables only.

    All secrets must come from machine environment variables with CF_CLI_* prefix.
    No .env.* files are read for secrets.

    Checks (in priority order):
    1. ``CF_CLI_<NAME>`` in ``os.environ`` (only source for secrets)
    2. ``NAME`` directly in ``os.environ`` (for non-secret config)

    Returns ``(value, source_description)`` or ``(None, None)`` if not found.
    """
    return resolve_config_value(
        name,
        workspace_dir=Path.cwd(),
    )


@_section("Environment Variables (Proxy)")
def _check_litellm_master_key() -> CheckResult:
    return _check_env_var(
        "LITELLM_MASTER_KEY", "Proxy master key", "CF_CLI_LITELLM_MASTER_KEY"
    )


def _check_env_var(name: str, label: str, source_hint: str) -> CheckResult:
    """Check that an env var is set from machine environment variables only.

    Uses :func:`_resolve_env_var_value` for a single code path that considers
    ``CF_CLI_*`` machine overrides and direct ``os.environ``.
    """
    value, source = _resolve_env_var_value(name)
    if value is not None:
        return _ok(f"{name} is set ({label})")
    return _fail(
        f"{name} is not set ({label})",
        f"Export CF_CLI_{name}=... in your shell",
    )


def _check_env_var_optional(name: str, label: str, _source_hint: str) -> CheckResult:
    """Check an optional env var from machine environment variables only.

    Uses :func:`_resolve_env_var_value` for a single code path that considers
    ``CF_CLI_*`` machine overrides and direct ``os.environ``.
    """
    value, source = _resolve_env_var_value(name)
    if value is not None:
        return _ok(f"{name} is set ({label})")
    return _skip(f"{name} is not set (optional — {label})")


# ── Section: Env Vars (Claude) ────────────────────────────────────────────


def _load_claude_profile_env() -> dict[str, str]:
    """Load env vars from the Claude Code profile's default profile.

    Returns the ``env`` dict from the ``default`` profile in
    ``profiles.yaml``, or an empty dict if not found.
    """
    import yaml

    from codefreedom.core.config import get_config_dir

    config_dir = get_config_dir()
    path = config_dir / "profiles.yaml"
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                profiles = data.get("profiles", {})
                default = profiles.get("default", {})
                env = default.get("env", {})
                if isinstance(env, dict):
                    return {k: str(v) for k, v in env.items()}
        except Exception:
            pass
    return {}


@_section("Environment Variables (Claude)")
def _check_anthropic_base_url() -> CheckResult:
    return _check_claude_env_var("ANTHROPIC_BASE_URL", "Anthropic API base URL")


@_section("Environment Variables (Claude)")
def _check_anthropic_auth_token() -> CheckResult:
    return _check_claude_env_var("ANTHROPIC_AUTH_TOKEN", "Anthropic auth token")


def _check_claude_env_var(name: str, label: str) -> CheckResult:
    """Check a Claude env var from machine environment variables only.

    Resolution order:
    1. ``CF_CLI_<NAME>`` machine override (only source for secrets)
    2. ``NAME`` directly in ``os.environ`` (for non-secret config)
    """
    value, source = _resolve_env_var_value(name)
    if value is not None:
        return _ok(f"{name} is set ({label})")
    return _skip(f"{name} is not set (optional — {label})")


# ── Section: Sandbox ────────────────────────────────────────────────────────


@_section("Sandbox")
def _check_sandbox_dir() -> CheckResult:
    cf_dir = get_codefreedom_dir()
    sandbox_default = cf_dir / "claude-code" / "sandbox" / "default"
    if not sandbox_default.exists():
        return _ok(f"{sandbox_default} will be created on first sandbox run")
    return _ok(f"{sandbox_default} exists")


@_section("Sandbox")
def _check_sandbox_profiles() -> CheckResult:
    from codefreedom.core.config import get_config_dir

    config_dir = get_config_dir()
    profiles_path = config_dir / "profiles.yaml"
    if not profiles_path.exists():
        return _skip("(no profiles.yaml to check sandbox settings)")

    try:
        import yaml

        with open(profiles_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return _skip("(could not read profiles.yaml)")
        profiles_section = data.get("profiles", {})
        if isinstance(profiles_section, dict):
            for aname, agent_data in profiles_section.items():
                if not isinstance(agent_data, dict):
                    continue
                agent_profiles = agent_data.get("profiles", {})
                if isinstance(agent_profiles, dict):
                    for pname, pdata in agent_profiles.items():
                        if isinstance(pdata, dict) and "sandbox_images" in pdata:
                            return _ok(
                                f"Profile '{aname}.{pname}' has sandbox image configuration"
                            )
        return _skip("(no sandbox images configured in profiles)")
    except (yaml.YAMLError, OSError):
        return _skip("(could not read profiles.yaml)")


# ── Section: Proxy Status ──────────────────────────────────────────────────


@_section("Proxy Status")
def _check_proxy_running() -> CheckResult:
    container = _get_litellm_container_name()
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                f"name={container}",
                "--format",
                "{{.Status}}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        status = result.stdout.strip()
        if status:
            return _ok(f"LiteLLM container is running ({status})")
        return _warn(
            "LiteLLM container is not running",
            "Start it with: cf run proxy start",
        )
    except FileNotFoundError:
        return _skip("(Docker CLI not available)")


@_section("Proxy Status")
def _check_web_bridge_running() -> CheckResult:
    settings = _get_web_bridge_settings()
    container = settings["container_name"]
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                f"name={container}",
                "--format",
                "{{.Status}}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        status = result.stdout.strip()
        if status:
            return _ok(f"Web-bridge container is running ({status})")
        return _warn(
            "Web-bridge container is not running", "Start it with: cf run proxy start"
        )
    except FileNotFoundError:
        return _skip("(Docker CLI not available)")


# ── Section: Port Availability ──────────────────────────────────────────────


@_section("Port Availability")
def _check_chrome_cdp_port() -> CheckResult:
    settings = _get_chrome_settings()
    port = settings["port"]
    hint = f"{get_config_dir()}/profiles.yaml (tools.chrome.port)"
    return _check_port(port, "Chrome CDP", hint)


@_section("Port Availability")
def _check_chrome_mcp_port() -> CheckResult:
    settings = _get_chrome_settings()
    port = settings.get("mcp_port", 9223)
    hint = f"{get_config_dir()}/profiles.yaml (tools.chrome.mcp_port)"
    return _check_port(port, "Chrome MCP", hint)


@_section("Port Availability")
def _check_web_port() -> CheckResult:
    settings = _get_web_settings()
    port = settings["port"]
    hint = f"{get_config_dir()}/profiles.yaml (tools.web.port)"
    return _check_port(port, "Web search (Camoufox)", hint)


@_section("Port Availability")
def _check_proxy_port() -> CheckResult:
    port = 4000
    hint = "Default LiteLLM port (LITELLM_PORT)"
    return _check_port(port, "LiteLLM proxy", hint)


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


def _cf_tool_label_for_port(port: int) -> str | None:
    """Return a friendly label for a well-known CodeFreedom tool port.

    Builds the mapping dynamically from tool profiles so custom port
    configurations are recognised.
    """
    chrome = _get_chrome_settings()
    web = _get_web_settings()
    bridge = _get_web_bridge_settings()
    labels: dict[int, str] = {
        chrome["port"]: "Chrome browser",
        chrome.get("mcp_port", 9223): "Chrome MCP",
        web["port"]: "Web search (Camoufox)",
        bridge["port"]: "Web search bridge",
    }
    return labels.get(port)


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

    from codefreedom.log import bold, green, red, yellow

    print()
    if failed == 0 and warned == 0:
        print(f"  {green(f'[OK] All {passed} checks passed. Your setup looks good!')}")
    elif failed == 0:
        print(
            f"  {yellow(f'[OK] {passed} passed, {warned} warnings')} — review items above."
        )
    else:
        print(
            f"  {red(bold(f'[FAIL] {failed} failure(s), {warned} warning(s), {passed} passed.'))}"
        )

    print()
    return 0 if failed == 0 else (2 if warned > 0 else 1)
