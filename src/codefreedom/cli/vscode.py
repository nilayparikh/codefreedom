"""VS Code subcommand -- generate config fragments for VS Code.

Usage:
    codefreedom vscode claude config [--profile NAME] [--host HOST] [--port PORT] [--out PATH]
    codefreedom vscode proxy config --host HOST [--port PORT] [--name NAME] [--out PATH]

Generates two different kinds of VS Code configuration:

* ``vscode claude config`` -- emits a ``claudeCode.*`` settings fragment
  for the Anthropic Claude Code VS Code extension. Reads the named
  profile (default: 'default') in local mode, renders env vars, and
  replaces secret-looking values with ``${env:VARNAME}`` references.

* ``vscode proxy config`` -- probes the running CodeFreedom proxy
  (``/health/liveliness`` + ``/v1/model/info``) and emits a
  ``chatLanguageModels.json`` entry for VS Code's built-in Copilot Chat
  OpenAI-compatible provider system. Each model carries ``toolCalling`` /
  ``vision`` / token-limit / ``supportsReasoningEffort`` fields derived
  from the proxy response.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from codefreedom.env_loader import eprint, load_env_chain
from codefreedom.profiles import ProfileError, load_profile_env, load_profiles

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║ Arg parser                                                               ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


def build_parser(parser: argparse.ArgumentParser) -> None:
    """Add VS Code sub-subcommands (``claude config``, ``proxy config``) to *parser*."""
    sub = parser.add_subparsers(dest="vscode_action", title="actions", required=True)

    # ── claude config ───────────────────────────────────────────────────
    claude_cfg = sub.add_parser(
        "claude",
        help="Generate a VS Code settings.json fragment for the Claude Code extension",
        description=(
            "Generate a VS Code settings.json fragment for the Claude Code"
            " extension. Mirrors the local (no-sandbox) mode of"
            " `codefreedom claude` so you can run Claude Code from inside"
            " VS Code with the same profile, auth, and model routing."
        ),
    )
    claude_sub = claude_cfg.add_subparsers(dest="claude_config_action", required=True)
    claude_config = claude_sub.add_parser(
        "config",
        help="Emit the claudeCode.* settings fragment to stdout (or --out PATH)",
        description=(
            "Emit a `claudeCode.*` settings fragment that mirrors the named"
            " profile (default: 'default') in local mode.  Secret-looking"
            " env var values are replaced with `${env:VARNAME}` references"
            " so they are never written to disk in plaintext."
        ),
    )
    claude_config.add_argument(
        "--profile",
        type=str,
        default="default",
        help="Profile to render (default: 'default').",
    )
    claude_config.add_argument(
        "--host",
        type=str,
        default=None,
        help=(
            "Override ANTHROPIC_BASE_URL host (e.g., 192.168.1.10, proxy.lan)."
            " Useful when VS Code runs on a different machine than the"
            " CodeFreedom proxy."
        ),
    )
    claude_config.add_argument(
        "--port",
        type=int,
        default=None,
        help="Override ANTHROPIC_BASE_URL port (default: 4000).",
    )
    claude_config.add_argument(
        "--out",
        type=str,
        default=None,
        metavar="PATH",
        help="Write the fragment to PATH instead of stdout.",
    )

    # ── proxy config ────────────────────────────────────────────────────
    proxy_cfg = sub.add_parser(
        "proxy",
        help="Generate a VS Code chatLanguageModels.json entry from the running proxy",
        description=(
            "Generate VS Code configuration fragments from the running CodeFreedom"
            " proxy. Currently supports emitting a `chatLanguageModels.json` entry"
            " that points VS Code at the LiteLLM proxy."
        ),
    )
    proxy_sub_actions = proxy_cfg.add_subparsers(
        dest="proxy_config_action", required=True
    )
    proxy_config = proxy_sub_actions.add_parser(
        "config",
        help="Probe the proxy and emit a chatLanguageModels.json entry",
        description=(
            "Generate a single entry for VS Code's `chatLanguageModels.json` file. The entry "
            "lists every model exposed by the running LiteLLM proxy at /v1/model/info.\n\n"
            "Requirements:\n"
            "  * The proxy must be up (use `codefreedom proxy status` to verify).\n"
            "  * LITELLM_MASTER_KEY must be set in the environment, or in\n"
            "    `~/.codefreedom/.env.proxy.secrets`.\n\n"
            "The `--host` flag is required because the bind host (LITELLM_BIND_HOST, often "
            "0.0.0.0) is not always a routable address. Use the host that VS Code should use "
            "to reach the proxy (e.g. `localhost`, a LAN IP, or a DNS name)."
        ),
    )
    proxy_config.add_argument(
        "--host",
        type=str,
        required=True,
        help=(
            "Hostname or IP VS Code should use to reach the proxy (required). "
            "Examples: localhost, 192.168.1.10, proxy.lan."
        ),
    )
    proxy_config.add_argument(
        "--port",
        type=int,
        default=4000,
        help="Proxy port (default: 4000).",
    )
    proxy_config.add_argument(
        "--name",
        type=str,
        default="CodeFreedom",
        help="Provider name to use in the generated entry (default: 'CodeFreedom').",
    )
    proxy_config.add_argument(
        "--out",
        type=str,
        default=None,
        metavar="PATH",
        help="Write the generated entry to PATH instead of stdout.",
    )


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║ Section 1: Claude Code VS Code config (`vscode claude config`)            ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
#
# Generates a settings.json fragment for the Claude Code VS Code extension
# (https://marketplace.visualstudio.com/items?itemName=Anthropic.claude-code).
# Mirrors the local (no-sandbox) mode of `codefreedom claude`: loads the
# named profile with local-mode overrides applied, then renders a fragment
# with `claudeCode.environmentVariables` plus other sensible `claudeCode.*`
# settings.


# Env vars that are sandbox-mode-only and have no meaning in the VS Code
# extension (which always runs natively).  Filtered out of the generated
# `claudeCode.environmentVariables` array regardless of profile.
_VSCODE_SANDBOX_ONLY_KEYS = frozenset({"IS_SANDBOX"})

# Default location for the Claude Code panel in VS Code.
_VSCODE_PREFERRED_LOCATION = "panel"

# Env var name patterns that indicate a secret.  Case-insensitive substring
# match against the uppercased name.
#
# How we handle secrets in the fragment:
#   1. We REPLACE the resolved secret value with a `${env:VARNAME}` reference
#      (using the same env var name).  VS Code substitutes the actual value
#      from the system/user environment at runtime -- the resolved secret
#      never appears in settings.json on disk.
#   2. We still FILTER OUT secrets entirely from the fragment if the user
#      prefers (--no-secret-refs flag, future) -- but the default is the
#      ${env:} reference, which is what the user wants for convenience.
#
# Why ${env:VARNAME} and not ${input:id}?
#   * VS Code's `${input:id}` syntax stores values in OS-keychain-backed
#     SecretStorage.  The Claude Code extension does NOT support this for
#     `claudeCode.environmentVariables` -- the feature request
#     (anthropics/claude-code#44158) was closed as not planned.
#   * VS Code's `${env:VARNAME}` syntax IS supported in settings.json values
#     (the extension reads the setting, VS Code substitutes the env var
#     before the extension sees the value).  This is the standard pattern.
#
# Known limitation: the extension DELETES `claudeCode.environmentVariables`
# from settings.json on activation in trusted workspaces (issues #10217,
# #10224).  Even with ${env:} references, the env-var entries will be
# stripped on the next restart.  Workaround: set the env vars as system/user
# environment variables AND the extension will still pick them up from
# process.env at startup.
_VSCODE_SECRET_SUBSTRINGS: Tuple[str, ...] = (
    "TOKEN",
    "_KEY",  # leading underscore avoids matching things like KEYBOARD_LAYOUT
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
)


def _is_secret_env_var(name: str) -> bool:
    """Return True if the env var name looks like it holds a secret.

    Uses case-insensitive substring matching against `_VSCODE_SECRET_SUBSTRINGS`.
    This is a heuristic -- false positives (non-secret vars containing "KEY")
    are acceptable because the user can edit the fragment; false negatives
    (secret vars not matching any pattern) are a real risk.  When in doubt,
    exclude.
    """
    upper = name.upper()
    return any(pat in upper for pat in _VSCODE_SECRET_SUBSTRINGS)


def _build_vscode_environment_variables(
    profile_env: dict,
    *,
    host: Optional[str] = None,
    port: Optional[int] = None,
) -> Tuple[List[dict], List[str]]:
    """Build the `claudeCode.environmentVariables` array for a profile.

    Takes the profile's resolved env in local mode, optionally overrides
    `ANTHROPIC_BASE_URL` host/port (for users generating configs for a remote
    proxy), and:

    * Filters out sandbox-only markers like `IS_SANDBOX` (the VS Code
      extension has no sandbox concept).
    * REPLACES secret-looking env vars (TOKEN/KEY/SECRET/etc.) with a
      `${env:VARNAME}` reference using the same name.  VS Code substitutes
      the actual value from the system/user environment at runtime -- the
      resolved secret value never appears in the fragment.  See
      `_VSCODE_SECRET_SUBSTRINGS` for the full list of patterns and
      rationale.

    Returns a tuple of `(env_array, referenced_secrets)`:
      * `env_array` -- list of `{"name": ..., "value": ...}` dicts sorted by
        name, ready to drop into `claudeCode.environmentVariables`.
      * `referenced_secrets` -- sorted list of env var names whose values
        were replaced with `${env:VARNAME}`.  The caller should print a
        notice telling the user to set these as system/user env vars.
    """
    env = dict(profile_env)

    # Apply host/port override to ANTHROPIC_BASE_URL.
    if host or port:
        existing = env.get("ANTHROPIC_BASE_URL", "http://localhost:4000")
        parsed = urlparse(existing)
        scheme = parsed.scheme or "http"
        new_host = host or parsed.hostname or "localhost"
        new_port = port or parsed.port or 4000
        env["ANTHROPIC_BASE_URL"] = f"{scheme}://{new_host}:{new_port}"

    # Drop sandbox-only keys entirely.  Replace secret-looking values with
    # `${env:VARNAME}` so VS Code can substitute them at runtime from the
    # user's system environment.  The resolved secret value is never
    # written to disk.
    referenced_secrets: List[str] = []
    for key in list(env.keys()):
        if key in _VSCODE_SANDBOX_ONLY_KEYS:
            env.pop(key, None)
        elif _is_secret_env_var(key):
            referenced_secrets.append(key)
            env[key] = f"${{env:{key}}}"

    env_array = [{"name": k, "value": v} for k, v in sorted(env.items())]
    return env_array, sorted(referenced_secrets)


def _build_vscode_settings(
    env_array: List[dict],
    *,
    selected_model: Optional[str] = None,
) -> dict:
    """Build the full `claudeCode.*` settings fragment.

    Includes the env-var array plus sensible defaults for the local (no-sandbox)
    mode the VS Code extension always runs in.  All keys are sourced from the
    official `claudeCode.*` settings list documented at
    https://code.claude.com/docs/en/vs-code#extension-settings.
    """
    fragment: dict = {
        "claudeCode.environmentVariables": env_array,
        "claudeCode.preferredLocation": _VSCODE_PREFERRED_LOCATION,
        # ANTHROPIC_AUTH_TOKEN is set in the env array, so no login prompt needed.
        "claudeCode.disableLoginPrompt": True,
        "claudeCode.useCtrlEnterToSend": True,
        "claudeCode.useTerminal": True,
        "claudeCode.respectGitIgnore": True,
        "claudeCode.autosave": True,
        # Matches the CLI's --dangerously-skip-permissions behaviour in local mode.
        "claudeCode.allowDangerouslySkipPermissions": True,
    }
    if selected_model:
        fragment["claudeCode.selectedModel"] = selected_model
    return fragment


def _resolve_profiles_path() -> Path:
    """Return the resolved Claude Code profiles path (test-patchable)."""
    from codefreedom.config import resolve_profiles_path as _resolve

    return _resolve()


def cmd_vscode_claude_config(args: argparse.Namespace) -> int:
    """Generate a VS Code settings.json fragment for the Claude Code extension.

    Entry point for ``codefreedom vscode claude config``.  Mirrors the local
    (no-sandbox) mode of `codefreedom claude`: loads the named profile with
    local-mode overrides applied, then renders a fragment with
    ``claudeCode.environmentVariables`` plus other sensible
    ``claudeCode.*`` settings.  Output is a JSON fragment ready to be merged
    into VS Code's User settings.json (or workspace .vscode/settings.json).
    """
    workspace_dir = Path.cwd()
    profile_name = args.profile or "default"

    eprint(f"[vscode] Loading env chain (claude component) from {workspace_dir}...")
    base_env = load_env_chain(workspace_dir, component="claude")

    profiles_path = _resolve_profiles_path()
    if not profiles_path.exists():
        eprint(f"[ERROR] Profiles file not found: {profiles_path}")
        eprint("   Run: codefreedom claude init")
        return 1

    try:
        profiles_dict = load_profiles(profiles_path)
        profile_env = load_profile_env(
            profile_name, profiles_path, base_env, "local", profiles=profiles_dict
        )
    except ProfileError as e:
        eprint(f"[ERROR] {e}")
        return 1

    env_array, referenced_secrets = _build_vscode_environment_variables(
        profile_env, host=args.host, port=args.port
    )
    selected_model = profile_env.get("CLAUDE_MODEL")
    fragment = _build_vscode_settings(env_array, selected_model=selected_model)

    rendered = json.dumps(fragment, indent=2)

    # Tell the user which secrets were replaced with ${env:VARNAME}
    # references -- they need to set these as system/user env vars so VS
    # Code can substitute the actual values at runtime.
    if referenced_secrets:
        eprint(
            f"[vscode] {len(referenced_secrets)} secret env var(s) emitted as"
            " ${env:VARNAME} references (set them as system/user env vars):"
        )
        for name in referenced_secrets:
            eprint(f"         - {name}  ->  ${{env:{name}}}")
        eprint(
            "         VS Code substitutes the actual value at runtime from"
            " your system environment.  Set them with:"
        )
        eprint("           Windows:  System Properties -> Environment Variables")
        eprint(
            "           Linux/macOS:  export VARNAME=value  (in ~/.bashrc, ~/.zshrc, etc.)"
        )
        eprint(
            "         See:  https://nilayparikh.github.io/codefreedom/vscode/#secret-management"
        )

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered + "\n", encoding="utf-8")
        eprint(f"[vscode] Wrote: {out_path}")
    else:
        print(rendered)

    env_count = len(env_array)
    eprint(
        f"[vscode] Done -- profile '{profile_name}' rendered as a VS Code"
        f" settings.json fragment ({env_count} env var(s))."
    )
    eprint(
        "         Paste the JSON into your VS Code User settings.json"
        " (e.g. %APPDATA%\\Code\\User\\settings.json on Windows) to activate."
    )
    return 0


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║ Section 2: Proxy VS Code config (`vscode proxy config`)                  ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
#
# Generates a chatLanguageModels.json entry for VS Code's built-in Copilot
# Chat custom-provider system.  Probes the running LiteLLM proxy at
# /health/liveliness and /v1/model/info.


# Default VS Code input reference inserted into the generated `apiKey` field.
# VS Code replaces this at runtime with a value the user stored via the input
# variable system.  Users should run VS Code's "Add Secret Input" command and
# paste this same key to wire the actual LITELLM_MASTER_KEY.
_VSCODE_APIKEY_PLACEHOLDER = "${input:codefreedom.litellm.master_key}"

# Default field fallbacks when the proxy /v1/model/info response omits a
# specific capability or token-limit.  These are conservative -- the user can
# edit the generated JSON to adjust per-model.
_DEFAULT_MAX_INPUT_TOKENS = 128000
_DEFAULT_MAX_OUTPUT_TOKENS = 16000

# Standard reasoning effort levels advertised to VS Code.
#
# The VS Code config always advertises the full standard set for any model
# that supports reasoning.  The proxy's reasoning-efforts mapping plugin
# translates these standard values to model-native values at runtime
# (see ``plugins/reasoning-efforts/reasoning-efforts-mapping.yaml``).
_STANDARD_REASONING_EFFORT_LEVELS: Tuple[str, ...] = (
    "none",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)

# Note: ``supportsReasoningEffort`` is now unconditionally advertised for
# ALL models.  The proxy's ``reasoning-efforts`` mapping plugin translates
# standard effort levels to model-native values at runtime.  If a model has
# no real reasoning capability, the plugin's rule maps everything to
# ``"none"`` -- the VS Code UI still shows the control but it's effectively
# a no-op.  No per-model rule table needed anymore.
#
# The old ``_REASONING_EFFORT_RULES`` tuple was removed because it required
# manual updates for every new model family and could not keep up with the
# proxy's plugin-based mapping.  The plugin IS the single source of truth.


def _resolve_reasoning_effort(_model_name: str) -> List[str]:
    """Return the supported `reasoning_effort` levels for *model_name*.

    Always returns the full standard set (``["none", "low", "medium",
    "high", "xhigh", "max"]``) for every model.  The proxy's
    reasoning-efforts mapping plugin handles translation to model-native
    values (thinking budgets, native reasoning_effort, pass-through) at
    runtime -- see ``plugins/reasoning-efforts/reasoning-efforts-mapping.yaml``.
    If a model truly has no reasoning capability, the mapping plugin's
    rule simply maps all levels to ``"none"``, and VS Code's UI still
    shows the control but the effect is a no-op.

    The ``_model_name`` parameter is accepted for backward compatibility
    with callers that already pass it, but is no longer consulted.
    Previously this function used a hardcoded rule table
    (``_REASONING_EFFORT_RULES``) to decide per-model, but that was fragile
    and required updates whenever a new model family was added.  Since the
    mapping plugin already covers all configured models, unconditionally
    advertising the field is both simpler and more future-proof.
    """
    return list(_STANDARD_REASONING_EFFORT_LEVELS)


def _resolve_master_key() -> Optional[str]:
    """Return LITELLM_MASTER_KEY from the canonical :func:`get_env` chain.

    Delegates to :func:`get_env` (``component="proxy"``) so the same
    precedence applies as everywhere else — env files, shared configs,
    ``os.environ``, and ``CF_CLI_*`` overrides.

    This is a convenience wrapper; ``cmd_vscode_proxy_config`` accesses
    the key directly from ``get_env()``.
    """
    from codefreedom.env_loader import get_env

    merged = get_env(Path.cwd(), component="proxy", verbose=False)
    key = merged.get("LITELLM_MASTER_KEY", "").strip()
    return key if key else None


def _proxy_health_url(host: str, port: int) -> str:
    """Return the URL used to probe proxy liveness."""
    return f"http://{host}:{port}/health/liveliness"


def _proxy_model_info_url(host: str, port: int) -> str:
    """Return the URL of the proxy's /v1/model/info endpoint."""
    return f"http://{host}:{port}/v1/model/info"


def _check_proxy_live(host: str, port: int, *, timeout: float = 5.0) -> bool:
    """Return True if the proxy is responding at /health/liveliness."""
    try:
        req = urllib.request.Request(_proxy_health_url(host, port), method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, ConnectionError, OSError, TimeoutError):
        return False


def _fetch_model_info(
    host: str,
    port: int,
    master_key: str,
    *,
    timeout: float = 10.0,
) -> List[Dict[str, Any]]:
    """Fetch the proxy's /v1/model/info and return its `data` list.

    Raises urllib.error.HTTPError on non-2xx responses (e.g. 401 for a bad
    master key) and urllib.error.URLError on network failures.
    """
    req = urllib.request.Request(
        _proxy_model_info_url(host, port),
        method="GET",
        headers={"Authorization": f"Bearer {master_key}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("Unexpected /v1/model/info response shape (not an object).")
    data = payload.get("data", [])
    if not isinstance(data, list):
        raise ValueError(
            "Unexpected /v1/model/info response shape (`data` not a list)."
        )
    return data


def _model_to_vscode_entry(model: Dict[str, Any], base_url: str) -> Dict[str, Any]:
    """Convert a single proxy model dict to a VS Code chatLanguageModels entry.

    `toolCalling` is always advertised as `True` so VS Code's chat UI shows
    the tool-calling affordance for every model.  LiteLLM does not have a
    reliable, model-agnostic capability database -- most providers don't
    populate `supports_function_calling` even when their models do support
    it -- so a permissive default is friendlier than a sparse "no" that
    hides tools the user actually has access to.  If a model truly does
    not support tool calling, the upstream API returns an error and the
    chat will surface it.

    `vision`, `maxInputTokens`, and `maxOutputTokens` are read from the
    LiteLLM `model_info` payload (keys: `supports_vision`, `max_input_tokens`,
    `max_output_tokens`, with `max_tokens` as a shared fallback).

    `supportsReasoningEffort` is always advertised with the full standard
    set (``["none", "low", "medium", "high", "xhigh", "max"]``) for
    every model.  The proxy's reasoning-efforts mapping plugin translates
    standard values to model-native values at runtime.
    """
    model_info = model.get("model_info") or {}
    if not isinstance(model_info, dict):
        model_info = {}

    model_name = model.get("model_name") or model_info.get("id") or "unknown"

    # Vision: be permissive -- anything truthy under these keys counts.
    vision = bool(model_info.get("supports_vision") or model_info.get("vision"))

    # Token limits: prefer explicit fields, fall back to defaults.
    max_input = (
        model_info.get("max_input_tokens")
        or model_info.get("max_tokens")
        or _DEFAULT_MAX_INPUT_TOKENS
    )
    max_output = (
        model_info.get("max_output_tokens")
        or model_info.get("max_tokens")
        or _DEFAULT_MAX_OUTPUT_TOKENS
    )

    try:
        max_input_int = int(max_input)
    except (TypeError, ValueError):
        max_input_int = _DEFAULT_MAX_INPUT_TOKENS
    try:
        max_output_int = int(max_output)
    except (TypeError, ValueError):
        max_output_int = _DEFAULT_MAX_OUTPUT_TOKENS

    entry: Dict[str, Any] = {
        "id": str(model_name),
        "name": str(model_name),
        "url": base_url,
        # Always advertise tool support -- see docstring for rationale.
        "toolCalling": True,
        "vision": vision,
        "maxInputTokens": max_input_int,
        "maxOutputTokens": max_output_int,
    }
    # Reasoning effort is always advertised.  The proxy's reasoning-efforts
    # mapping plugin translates standard levels to model-native values at
    # runtime (see ``plugins/reasoning-efforts/reasoning-efforts-mapping.yaml``).
    entry["supportsReasoningEffort"] = _resolve_reasoning_effort(str(model_name))
    return entry


def _build_vscode_entry(
    provider_name: str, base_url: str, models: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Build a single chatLanguageModels.json-compatible entry."""
    return {
        "name": provider_name,
        "vendor": "customendpoint",
        "apiKey": _VSCODE_APIKEY_PLACEHOLDER,
        "apiType": "chat-completions",
        "models": [_model_to_vscode_entry(m, base_url) for m in models],
    }


def cmd_vscode_proxy_config(args: argparse.Namespace) -> int:
    """Generate a chatLanguageModels.json entry from the running proxy.

    Entry point for ``codefreedom vscode proxy config``.  Probes the proxy
    at /health/liveliness, fetches /v1/model/info with LITELLM_MASTER_KEY,
    and emits a JSON object that can be dropped into VS Code's user-level
    ``chatLanguageModels.json`` file (a list of provider entries).
    """
    host = args.host
    port = args.port or 4000
    provider_name = args.name
    out_path = Path(args.out) if args.out else None
    workspace_dir = Path.cwd()

    # Load the full env chain so LITELLM_MASTER_KEY is resolved from ANY
    # supported location: .env.proxy, .env.proxy.secrets, .env.secrets,
    # .env.user, CF_CLI_LITELLM_MASTER_KEY, etc.
    eprint(f"[vscode] Loading env chain (proxy component) from {workspace_dir}...")
    base_env = load_env_chain(workspace_dir, component="proxy")

    eprint(f"[vscode] Probing proxy at {_proxy_health_url(host, port)} ...")
    if not _check_proxy_live(host, port):
        eprint(
            f"[ERROR] Proxy is not responding at http://{host}:{port}."
            " Is `codefreedom proxy start` running?"
        )
        return 1

    master_key = base_env.get("LITELLM_MASTER_KEY", "").strip()
    if not master_key:
        eprint(
            "[ERROR] LITELLM_MASTER_KEY is not set."
            " Export it in your shell, or add it to ~/.codefreedom/.env.proxy.secrets,"
            " or set CF_CLI_LITELLM_MASTER_KEY in your shell,"
            " then re-run this command."
        )
        return 1

    eprint(f"[vscode] Fetching models from {_proxy_model_info_url(host, port)} ...")
    try:
        models = _fetch_model_info(host, port, master_key)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            eprint(
                f"[ERROR] Proxy rejected the master key (HTTP {exc.code})."
                " Check LITELLM_MASTER_KEY."
            )
        else:
            eprint(f"[ERROR] /v1/model/info returned HTTP {exc.code}.")
        return 1
    except (urllib.error.URLError, ConnectionError, OSError, TimeoutError) as exc:
        eprint(f"[ERROR] Could not reach the proxy: {exc}")
        return 1
    except (ValueError, json.JSONDecodeError) as exc:
        eprint(f"[ERROR] Invalid response from /v1/model/info: {exc}")
        return 1

    base_url = f"http://{host}:{port}/v1"
    entry = _build_vscode_entry(provider_name, base_url, models)
    rendered = json.dumps(entry, indent=2)

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered + "\n", encoding="utf-8")
        eprint(f"[vscode] Wrote: {out_path}")
    else:
        print(rendered)

    model_count = len(entry["models"])
    eprint(
        f"[vscode] Done -- {model_count} model(s) included."
        f" apiKey is a VS Code input placeholder ({_VSCODE_APIKEY_PLACEHOLDER});"
        " create the matching secret in VS Code to wire the real master key."
    )
    return 0
