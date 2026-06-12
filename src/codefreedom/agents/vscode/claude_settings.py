"""Section 1 — Claude Code VS Code settings generator (``vscode claude config``).

Generates a settings.json fragment for the Claude Code VS Code extension.
Mirrors local (no-sandbox) mode of ``codefreedom claude``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from codefreedom.env_loader import load_env_chain
from codefreedom.log import eprint
from codefreedom.core.profiles import ProfileError, load_profile_env, load_profiles
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
    from codefreedom.core.config import resolve_profiles_path as _resolve

    return _resolve()


def cmd_vscode_claude_config(args: argparse.Namespace) -> int:
    """Generate a VS Code settings.json fragment for the Claude Code extension.

    Entry point for ``codefreedom config vscode claude config``.  Mirrors the local
    (no-sandbox) mode of `codefreedom claude`: loads the named profile with
    local-mode overrides applied, then renders a fragment with
    ``claudeCode.environmentVariables`` plus other sensible
    ``claudeCode.*`` settings.  Output is a JSON fragment ready to be merged
    into VS Code's User settings.json (or workspace .vscode/settings.json).
    """
    workspace_dir = Path.cwd()
    profile_name = args.profile or "default"

    eprint(f"[VSCODE] Loading env chain (claude component) from {workspace_dir}...")
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


