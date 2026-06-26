"""Pi Code subcommand -- native launch with extension-based config.

Auto-detects the running CodeFreedom LiteLLM proxy, generates a TypeScript
extension for dynamic model discovery, and launches Pi (``pi``) with zero
manual configuration.

Usage:
    codefreedom run agent pi-code [--profile NAME] [--list-profiles] [agent-args...]
    codefreedom run agent pi-code [options] [-- <agent-args>]

Extension-based config:
    - Generates extensions/codefreedom.ts in the pi agent home config dir
    - Extension uses pi.registerProvider() for dynamic model discovery
    - Fetches /v1/model/info for rich capabilities (vision, reasoning, costs)
    - pi-mcp-adapter reads .mcp.json for MCP tool support
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Any

from codefreedom.config.runtime import list_profiles, resolve_agent_runtime
from codefreedom.core.config import (
    get_codefreedom_dir,
    resolve_pi_profiles_path,
)
from codefreedom.log import eprint, tag
from codefreedom.sandbox.signals import forward_signal
from codefreedom.tools.registry import generate_session_id


def register_args(parser: argparse.ArgumentParser) -> None:
    """Register Pi-specific arguments on the agent parser."""


# ── Constants ──────────────────────────────────────────────────────────────────

PI_SETTINGS_NAME = "settings.json"

CODEFREEDOM_DIR = get_codefreedom_dir()

# ── Helpers ────────────────────────────────────────────────────────────────────


def find_pi_binary() -> str | None:
    """Locate the ``pi`` CLI binary on PATH."""
    return shutil.which("pi")


def _read_image_router_models(store_dir: Path) -> list[str]:
    """Read image router config to find models with image routing enabled.

    Two sources (matches VSCode ``_load_route_image_models`` logic):
    1. Image-router plugin YAML — lists VLM models used for transcription.
    2. Provider YAMLs — models with
       ``codefreedom.plugins.route-image-request.enabled: true``.

    Returns a deduplicated list of model group names.
    """
    import glob as _glob

    import yaml

    result: set[str] = set()

    # Source 1: image-router plugin config
    plugin_path = (
        store_dir
        / "proxy"
        / "config"
        / "plugins"
        / "image-router"
        / "image-router.yaml"
    )
    if plugin_path.exists():
        try:
            data = yaml.safe_load(plugin_path.read_text(encoding="utf-8"))
        except Exception:
            data = None

        if isinstance(data, dict):
            router_cfg = data.get("image-router-for-text-only", {})
            if isinstance(router_cfg, dict) and router_cfg.get("enabled", False):
                for m in router_cfg.get("models", []) or []:
                    if isinstance(m, str):
                        result.add(m)

    # Source 2: provider YAMLs with route-image-request plugin
    providers_dir = store_dir / "proxy" / "config" / "providers"
    if not providers_dir.is_dir():
        return sorted(result)

    for yp in _glob.glob(str(providers_dir / "*.yaml")):
        try:
            data = yaml.safe_load(Path(yp).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for entry in data.get("model_list", []) or []:
            if not isinstance(entry, dict):
                continue
            name = entry.get("model_name")
            cf = entry.get("codefreedom")
            if not (isinstance(name, str) and isinstance(cf, dict)):
                continue
            plugins = cf.get("plugins") or {}
            route_cfg = plugins.get("route-image-request")
            if isinstance(route_cfg, dict) and route_cfg.get("enabled") is True:
                result.add(name)

    return sorted(result)


def _load_alias_models(store_dir: Path) -> list[str]:
    """Return model names that are ``model_group_alias`` entries.

    Reads ``proxy/config/config.yaml`` and collects the keys of
    ``router_settings.model_group_alias``.  These are shorthand aliases
    (e.g. ``opus``, ``sonnet``) that LiteLLM resolves to real model
    groups at runtime.  By default the extension skips them so users
    only see actual model entries.
    """
    import yaml

    config_path = store_dir / "proxy" / "config" / "config.yaml"
    if not config_path.is_file():
        return []
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, dict):
        return []

    router = data.get("router_settings") or {}
    if not isinstance(router, dict):
        return []

    aliases = router.get("model_group_alias") or {}
    if not isinstance(aliases, dict):
        return []

    return sorted(aliases.keys())


_EXTENSION_TEMPLATE = """\
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

// Standard thinking levels — pi passes these to the proxy,
// which maps them to model-native values via reasoning-efforts plugin.
// Must match pi's --thinking flag values: off, minimal, low, medium, high, xhigh
const THINKING_LEVELS = ["off", "minimal", "low", "medium", "high", "xhigh"];

export default async function (pi: ExtensionAPI) {
  const baseUrl = process.env.PROXY_BASE_URL || "http://localhost:4000";
  const apiKey = process.env.PROXY_API_KEY || "";
  const imageRouterModels = (process.env.IMAGE_ROUTER_MODELS || "")
    .split(",")
    .filter(Boolean);
  const aliasModels = (process.env.ALIAS_MODELS || "")
    .split(",")
    .filter(Boolean);
  const showAliases = ["1", "true", "yes"].includes(
    (process.env.PI_SHOW_ALIAS_MODELS || "").toLowerCase()
  );

  const headers: Record<string, string> = {};
  if (apiKey) headers.Authorization = `Bearer ${apiKey}`;

  // Try /v1/model/info for rich metadata, fall back to /v1/models
  let models: any[] = [];
  try {
    const infoResp = await fetch(`${baseUrl}/v1/model/info`, { headers });
    if (infoResp.ok) {
      const infoData = await infoResp.json();
      const raw = (infoData.data || [])
        .filter((m: any) => {
          const name = m.model_name || "";
          return (
            !name.startsWith("azure/") &&
            !["gpt-3.5-turbo", "custom"].includes(name) &&
            (showAliases || !aliasModels.includes(name))
          );
        });

      // Deduplicate by model_name (group name) — keep richest model_info
      const seen = new Map<string, any>();
      for (const m of raw) {
        const name = m.model_name || "";
        if (!name) continue;
        const existing = seen.get(name);
        const existingInfo = existing?.model_info || {};
        const candidateInfo = m.model_info || {};
        if (!existing || Object.keys(candidateInfo).length > Object.keys(existingInfo).length) {
          seen.set(name, m);
        }
      }

      models = [...seen.values()].map((m: any) => {
        const info = m.model_info || {};
        const name = m.model_name || "unknown";
        const isVision =
          info.supports_vision || info.vision || imageRouterModels.includes(name);
        const isReasoning = info.supports_reasoning || false;

        // thinkingLevelMap maps pi levels to provider values.
        // Proxy's reasoning-efforts plugin handles the actual mapping,
        // so we pass pi levels through directly.
        const thinkingLevelMap: Record<string, string> = {};
        if (isReasoning) {
          for (const level of THINKING_LEVELS) {
            thinkingLevelMap[level] = level;
          }
        }

        return {
          id: name,
          name: name,
          reasoning: isReasoning,
          thinkingLevelMap: isReasoning ? thinkingLevelMap : undefined,
          input: isVision ? ["text", "image"] : ["text"],
          cost: {
            input: (info.input_cost_per_token || 0) * 1_000_000,
            output: (info.output_cost_per_token || 0) * 1_000_000,
            cacheRead: (info.cache_read_input_token_cost || 0) * 1_000_000,
            cacheWrite:
              (info.cache_creation_input_token_cost || 0) * 1_000_000,
          },
          contextWindow: info.context_window || info.max_input_tokens || 128000,
          maxTokens: info.max_output_tokens || 4096,
        };
      });
    }
  } catch {}

  // Fallback to /v1/models if /v1/model/info failed
  if (models.length === 0) {
    try {
      const resp = await fetch(`${baseUrl}/v1/models`, { headers });
      const { data } = await resp.json();
      models = (data || [])
        .filter(
          (m: any) =>
            !m.id.startsWith("azure/") &&
            !["gpt-3.5-turbo", "custom"].includes(m.id) &&
            (showAliases || !aliasModels.includes(m.id))
        )
        .map((m: any) => ({
          id: m.id,
          name: m.id.includes("/") ? m.id.split("/").pop() : m.id,
          reasoning: false,
          thinkingLevelMap: undefined,
          input: imageRouterModels.includes(m.id)
            ? ["text", "image"]
            : ["text"],
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
          contextWindow: 128000,
          maxTokens: 4096,
        }));
    } catch {}
  }

  pi.registerProvider("codefreedom", {
    name: "CodeFreedom",
    baseUrl: `${baseUrl}/v1`,
    apiKey: "$PROXY_API_KEY",
    api: "openai-completions",
    models,
  });
}
"""


def _generate_codefreedom_extension(config_dir: Path) -> Path:
    """Generate the CodeFreedom pi extension for dynamic model discovery.

    Creates extensions/codefreedom.ts in the config directory (global pi agent dir).
    Returns the path to the generated extension file.
    """
    ext_dir = config_dir / "extensions"
    ext_dir.mkdir(parents=True, exist_ok=True)
    ext_path = ext_dir / "codefreedom.ts"
    ext_path.write_text(_EXTENSION_TEMPLATE, encoding="utf-8")
    ext_path.chmod(0o600)
    eprint(f"{tag('PI')} Generated extension at {ext_path}")
    return ext_path


def _write_minimal_settings(
    pi_agent_dir: Path,
    extensions: list[str] | None = None,
) -> Path:
    """Write pi ``settings.json`` with CodeFreedom provider defaults.

    Merges with existing settings so user preferences (theme,
    last changelog version) survive across launches.

    Configuration precedence (highest to lowest):
    1. CLI flags (--model, --thinking, --provider) from profile env
    2. settings.json (pi-mutable, preserved across launches)
    3. Defaults in this function

    Prefixes each extension with ``npm:`` so ``pi`` resolves it as an
    npm source (its native install format). pi will auto-install missing
    packages at startup via its built-in package manager.

    Returns the path to the written settings file.
    """
    pi_agent_dir.mkdir(parents=True, exist_ok=True)
    config_path = pi_agent_dir / PI_SETTINGS_NAME

    # Read existing settings to preserve user preferences
    existing: dict[str, Any] = {}
    if config_path.is_file():
        with contextlib.suppress(Exception):
            existing = json.loads(config_path.read_text(encoding="utf-8"))

    # Force-set provider and trust (required for CodeFreedom to work)
    settings: dict[str, Any] = {**existing}
    settings["defaultProvider"] = "codefreedom"
    settings["defaultProjectTrust"] = "always"

    # Update packages (extensions may change between profiles)
    if extensions:
        settings["packages"] = [f"npm:{ext}" for ext in extensions]

    config_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    config_path.chmod(0o600)
    eprint(f"{tag('PI')} Generated settings at {config_path}")
    return config_path


def _read_profile_field(
    profile_name: str,
    profiles_path: Path,
    field: str,
    default: Any = None,
) -> Any:
    """Read a field from a named profile in the YAML profiles file.

    Handles YAML loading, structure validation, and profile lookup.
    Returns ``default`` if the profile or field is missing.
    """
    if not profiles_path.exists():
        return default

    import yaml

    try:
        data = yaml.safe_load(profiles_path.read_text(encoding="utf-8"))
    except Exception:
        return default

    if not isinstance(data, dict):
        return default

    profiles = data.get("profiles", {})
    if not isinstance(profiles, dict):
        return default

    profile = profiles.get(profile_name, {})
    if not isinstance(profile, dict):
        return default

    return profile.get(field, default)


def _read_profile_extensions(
    profile_name: str,
    profiles_path: Path,
) -> list[str]:
    """Read the ``extensions`` list from the profile YAML."""
    exts = _read_profile_field(profile_name, profiles_path, "extensions", [])
    return exts if isinstance(exts, list) else []


def _read_profile_lsp_servers(
    profile_name: str,
    profiles_path: Path,
) -> dict[str, list[str]]:
    """Read the ``lsp_servers`` map from the profile YAML.

    Returns e.g. ``{"npm": ["typescript-language-server", ...], "pip": [...]}``.
    """
    lsp = _read_profile_field(profile_name, profiles_path, "lsp_servers", {})
    return lsp if isinstance(lsp, dict) else {}


_LSP_BINARY_MAP: dict[str, str] = {
    "python-lsp-server[all]": "pylsp",
    "python-lsp-server": "pylsp",
    "vscode-langservers-extracted": "vscode-langservers-extracted",
}


def _ensure_lsp_servers(lsp_servers: dict[str, list[str]]) -> None:
    """Install missing LSP servers declared in the profile.

    Uses ``_LSP_BINARY_MAP`` for packages whose executable differs from
    the package name, then falls back to deriving the binary name from
    the package string.
    """
    for manager, packages in lsp_servers.items():
        if not isinstance(packages, list):
            continue
        missing = []
        for pkg in packages:
            bin_name = _LSP_BINARY_MAP.get(pkg)
            if bin_name is None:
                bin_name = pkg.split("[")[0].split("@")[0]
                if "/" in bin_name:
                    bin_name = bin_name.rsplit("/", 1)[-1]
            if not shutil.which(bin_name):
                missing.append(pkg)

        if not missing:
            continue

        if manager == "npm":
            npm_bin = shutil.which("npm")
            if not npm_bin:
                eprint(f"{tag('LSP')} npm not found on PATH — cannot install packages")
                continue
            eprint(f"{tag('LSP')} Installing npm packages: {', '.join(missing)}")
            try:
                subprocess.run(
                    [npm_bin, "install", "-g", *missing],
                    check=False,
                    capture_output=True,
                    timeout=120,
                )
            except Exception as exc:
                eprint(f"{tag('LSP')} npm install failed: {exc}")

        elif manager == "pip":
            pip_bin = shutil.which("pip")
            if not pip_bin:
                eprint(f"{tag('LSP')} pip not found on PATH — cannot install packages")
                continue
            eprint(f"{tag('LSP')} Installing pip packages: {', '.join(missing)}")
            try:
                subprocess.run(
                    [pip_bin, "install", "--quiet", *missing],
                    check=False,
                    capture_output=True,
                    timeout=120,
                )
            except Exception as exc:
                eprint(f"{tag('LSP')} pip install failed: {exc}")


def _ensure_lean_ctx() -> None:
    """Install the lean-ctx Rust binary via ``npm install -g lean-ctx-bin``.

    Uses the ``lean-ctx-bin`` npm package which ships pre-built binaries
    for all platforms (no Rust toolchain needed).  Then runs
    ``lean-ctx init --agent pi`` to write the MCP config that
    ``pi-mcp-adapter`` picks up.
    """
    # Already installed?
    if shutil.which("lean-ctx"):
        return

    npm_bin = shutil.which("npm")
    if not npm_bin:
        eprint(f"{tag('LEAN-CTX')} npm not found on PATH — cannot install")
        return

    eprint(f"{tag('LEAN-CTX')} Installing via npm (lean-ctx-bin)...")
    try:
        subprocess.run(
            [npm_bin, "install", "-g", "lean-ctx-bin"],
            check=True,
            capture_output=True,
            timeout=120,
        )
    except Exception as exc:
        eprint(f"{tag('LEAN-CTX')} npm install failed: {exc}")
        return

    lean_ctx_bin = shutil.which("lean-ctx")
    if not lean_ctx_bin:
        eprint(f"{tag('LEAN-CTX')} Installed but not on PATH — check npm global bin")
        return

    eprint(f"{tag('LEAN-CTX')} Configuring for pi...")
    with contextlib.suppress(Exception):
        subprocess.run(
            [lean_ctx_bin, "init", "--agent", "pi"],
            check=False,
            capture_output=True,
            timeout=30,
        )


def _detect_proxy_url(base_env: dict[str, str]) -> str:
    """Detect the proxy URL from environment or use default.

    Thin wrapper over :func:`codefreedom.core.agent_runtime.detect_proxy_url`.
    """
    from codefreedom.core.agent_runtime import detect_proxy_url

    return detect_proxy_url(base_env)


# ── Execution ─────────────────────────────────────────────────────────────────


def _get_pi_agent_dir() -> Path:
    """Return pi's default agent directory (``~/.pi/agent``).

    This is where pi looks for ``settings.json``, ``extensions/``,
    ``npm/``, and ``sessions/``.  We write our generated files here
    so they're picked up without overriding ``PI_CONFIG_DIR``.
    """
    return Path.home() / ".pi" / "agent"


def _prepare_pi_env(
    profile_env: dict[str, str],
    workspace_dir: Path,
    extensions: list[str] | None = None,
    acquired_tools: list[str] | None = None,
    lsp_servers: dict[str, list[str]] | None = None,
) -> dict[str, str]:
    """Build the env dict and set up pi agent directory, MCP, LSP, lean-ctx."""
    extensions = extensions or []

    env = {**os.environ}
    env.update(profile_env)

    pi_agent_dir = _get_pi_agent_dir()
    pi_agent_dir.mkdir(parents=True, exist_ok=True)
    _write_minimal_settings(pi_agent_dir, extensions=extensions)
    _generate_codefreedom_extension(pi_agent_dir)

    if acquired_tools:
        from codefreedom.launcher import _write_mcp_json

        _write_mcp_json(workspace_dir, acquired_tools)

    if "pi-lean-ctx" in extensions:
        _ensure_lean_ctx()

    if lsp_servers:
        _ensure_lsp_servers(lsp_servers)

    image_router_models = _read_image_router_models(CODEFREEDOM_DIR)
    if image_router_models:
        env["IMAGE_ROUTER_MODELS"] = ",".join(image_router_models)

    alias_models = _load_alias_models(CODEFREEDOM_DIR)
    if alias_models:
        env["ALIAS_MODELS"] = ",".join(alias_models)

    return env


def _build_pi_command(
    pi_bin: str, profile_env: dict[str, str], pi_args: list[str]
) -> list[str]:
    """Build the pi command with profile-driven --model/--thinking/--provider flags."""
    cmd = [pi_bin]

    default_model = profile_env.get("PI_DEFAULT_MODEL")
    has_model_flag = any(arg in ("--model", "-m") for arg in pi_args)
    if not has_model_flag and default_model:
        cmd.extend(["--model", default_model])

    default_thinking = profile_env.get("PI_DEFAULT_THINKING_LEVEL")
    has_thinking_flag = any(arg == "--thinking" for arg in pi_args)
    if not has_thinking_flag and default_thinking:
        cmd.extend(["--thinking", default_thinking])

    default_provider = profile_env.get("PI_DEFAULT_PROVIDER", "codefreedom")
    has_provider_flag = any(arg == "--provider" for arg in pi_args)
    if not has_provider_flag and default_provider:
        cmd.extend(["--provider", default_provider])

    cmd.extend(pi_args)
    return cmd


def run_local(
    profile_env: dict[str, str],
    pi_args: list[str],
    workspace_dir: Path,
    extensions: list[str] | None = None,
    acquired_tools: list[str] | None = None,
    lsp_servers: dict[str, list[str]] | None = None,
) -> int:
    """Run ``pi`` natively on the host. Returns exit code."""
    pi_bin = find_pi_binary()
    if not pi_bin:
        eprint(
            f"{tag('ERROR')} Pi (pi) not found on PATH.\n"
            "       Install: npm install -g @earendil-works/pi-coding-agent"
        )
        return 1

    eprint(f"{tag('LOCAL')} Running Pi natively...")

    env = _prepare_pi_env(
        profile_env, workspace_dir, extensions, acquired_tools, lsp_servers
    )
    cmd = _build_pi_command(pi_bin, profile_env, pi_args)

    try:
        proc = subprocess.Popen(cmd, env=env)
        signal.signal(signal.SIGINT, lambda s, f: forward_signal(proc, s, f))
        signal.signal(signal.SIGTERM, lambda s, f: forward_signal(proc, s, f))
        proc.wait()
        return proc.returncode
    except FileNotFoundError:
        eprint(f"{tag('ERROR')} Pi binary not found at {pi_bin}.")
        return 1
    except KeyboardInterrupt:
        return 130


# ── Main entry point ─────────────────────────────────────────────────────────


def run(args: argparse.Namespace) -> int:
    """Execute the ``pi-code`` subcommand. Returns exit code."""

    # Fast-path flags
    if args.list_profiles:
        from codefreedom.cli.common import display_profiles

        profiles_path = resolve_pi_profiles_path()
        profiles = list_profiles(profiles_path, agent="pi-code")
        return display_profiles(
            profiles_path, profiles, show_env_keys=False, show_tools=True
        )

    # ── Load env chain ─────────────────────────────────────────────────────
    workspace_dir = Path.cwd()
    eprint(f"{tag('ENV')} Loading configuration...")
    runtime = resolve_agent_runtime(
        "pi-code",
        workspace_dir=workspace_dir,
        profile_name=args.profile or "default",
        mode="local",
    )

    # ── Load profile ───────────────────────────────────────────────────────
    profile_name = args.profile or "default"
    profiles_path = resolve_pi_profiles_path()

    from codefreedom.cli.common import load_profile_with_tools

    profile_env, _sandbox_images, tools, exit_code = load_profile_with_tools(
        profile_name, profiles_path, runtime.base_env, "local",
        agent="pi-code",
    )
    if exit_code != 0:
        return 1

    # ── Ensure proxy API key is available ──────────────────────────────
    if not profile_env.get("PROXY_API_KEY"):
        master_key = runtime.base_env.get("LITELLM_MASTER_KEY", "")
        if master_key:
            profile_env["PROXY_API_KEY"] = master_key

    # ── Read extensions from profile ─────────────────────────────────
    extensions = _read_profile_extensions(profile_name, profiles_path)
    if extensions:
        eprint(f"{tag('PI')} Profile extensions: {', '.join(extensions)}")

    # ── Read LSP servers from profile ────────────────────────────────
    lsp_servers = _read_profile_lsp_servers(profile_name, profiles_path)
    if lsp_servers:
        total = sum(len(v) for v in lsp_servers.values() if isinstance(v, list))
        eprint(
            f"{tag('PI')} Profile LSP servers: {total} packages ({', '.join(lsp_servers.keys())})"
        )

    # ── Tools: acquire if declared in profile ────────────────────────────
    session_id = generate_session_id("local")

    from codefreedom.cli.common import acquire_and_run

    def _run(acquired_tools: list[str]) -> int:
        return run_local(
            profile_env,
            args.agent_args,
            workspace_dir,
            extensions=extensions,
            acquired_tools=acquired_tools,
            lsp_servers=lsp_servers,
        )

    return acquire_and_run(session_id, tools, profile_name, _run)
