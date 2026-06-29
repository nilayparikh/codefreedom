"""Config command — generate VS Code settings fragments and edit runtime config.

Usage:
    codefreedom setup config vscode [options]
    codefreedom setup config proxy [options]
    codefreedom setup config tools [options]
    codefreedom setup config bind --address <HOST>
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from codefreedom.core.agent_runtime import resolve_proxy_api_key as _resolve_proxy_api_key
from codefreedom.core.config import get_config_dir
from codefreedom.core.remote_validation import (
    PROXY_AUTH_REQUIRED as _PROXY_AUTH_REQUIRED,
    PROXY_OK as _PROXY_OK,
    probe_remote_proxy as _probe_remote_proxy,
    validate_remote_tool_url as _validate_remote_tool_url,
)
from codefreedom.log import eprint, tag

_PROXY_API_KEY_ENV = "CF_CLI_PROXY_API_KEY"
_PROXY_API_KEY_REF = "${PROXY_API_KEY}"


def _override_path() -> Path:
    return get_config_dir() / "override.yaml"


def _load_override() -> dict:
    path = _override_path()
    if not path.exists():
        return {"comment": "User overrides — values here override profiles.yaml"}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _write_override(data: dict) -> None:
    path = _override_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def _set_nested(data: dict, path: list[str], value) -> None:
    cur = data
    for key in path[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    if value is None:
        cur.pop(path[-1], None)
    else:
        cur[path[-1]] = value


def _remove_proxy_master_key_marker(data: dict) -> None:
    """Remove the ``${PROXY_API_KEY}`` interpolation marker we added.

    Only drops the entry when it still equals our marker, so a user-set
    literal value is never clobbered. Clears an empty ``env`` dict afterwards
    to keep ``override.yaml`` tidy.
    """
    proxy = data.get("common", {}).get("proxy", {})
    env = proxy.get("env")
    if isinstance(env, dict) and env.get("PROXY_API_KEY") == _PROXY_API_KEY_REF:
        env.pop("PROXY_API_KEY", None)
        if not env:
            proxy.pop("env", None)


def _resolve_proxy_api_key_interactive() -> str | None:
    """Resolve a proxy API key for an authenticated remote proxy.

    Checks the canonical ``CF_CLI_PROXY_API_KEY`` (and legacy fallback) via
    :func:`resolve_proxy_api_key` first. Falls back to an interactive prompt.
    Returns the key, or ``None`` if none was provided / input was cancelled.
    """
    key = _resolve_proxy_api_key().strip()
    if key:
        return key
    eprint(f"{tag('CONFIG')} Remote proxy requires an API key (401).")
    eprint(f"   Export {_PROXY_API_KEY_ENV} in your shell and re-run, or paste it now.")
    try:
        key = input("   API key: ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    return key or None


def _configure_remote_proxy(data: dict, url: str) -> str | None:
    """Probe a remote proxy URL and persist it, resolving auth on 401.

    On success, mutates *data* to set ``common.proxy.remote_url`` and, when a
    master key was needed, ``common.proxy.env.PROXY_API_KEY`` as the
    ``${PROXY_API_KEY}`` interpolation reference (the actual secret stays
    in the ``CF_CLI_PROXY_API_KEY`` machine env). Returns a truthy status
    string on success, or ``None`` on failure (after printing the reason).
    """
    status = _probe_remote_proxy(url)
    if status == _PROXY_OK:
        _set_nested(data, ["common", "proxy", "remote_url"], url)
        return status
    if status != _PROXY_AUTH_REQUIRED:
        eprint(f"{tag('CONFIG')} Remote proxy validation failed: {url}.")
        eprint("   Expected a working /v1/models endpoint. Settings were not saved.")
        return None

    key = _resolve_proxy_api_key_interactive()
    if not key:
        eprint(f"{tag('CONFIG')} No API key provided. Settings were not saved.")
        eprint(f"   Export {_PROXY_API_KEY_ENV} and re-run.")
        return None
    status = _probe_remote_proxy(url, api_key=key)
    if status != _PROXY_OK:
        eprint(f"{tag('CONFIG')} Remote proxy validation failed: {url}.")
        if status == _PROXY_AUTH_REQUIRED:
            eprint("   The provided API key was rejected (401/403).")
        else:
            eprint("   Expected a working /v1/models endpoint. Settings were not saved.")
        return None

    _set_nested(data, ["common", "proxy", "remote_url"], url)
    _set_nested(data, ["common", "proxy", "env", "PROXY_API_KEY"], _PROXY_API_KEY_REF)
    eprint(f"{tag('SECRETS')} Saved API key reference as {_PROXY_API_KEY_REF}.")
    eprint(
        f"   Keep {_PROXY_API_KEY_ENV} exported; the value is read at runtime."
    )
    return status


def build_parser(parent: argparse.ArgumentParser) -> None:
    """Build the config subcommand parser.

    Called from main.py to register the 'config' subcommand.
    """
    subparsers = parent.add_subparsers(dest="config_target", title="targets")

    # ── vscode config target ─────────────────────────────────────────────
    vscode_parser = subparsers.add_parser(
        "vscode",
        help="Generate chatLanguageModels.json for VS Code Copilot Chat",
        description=(
            "Generate entry for VS Code's built-in "
            "Copilot Chat custom-provider system."
        ),
    )
    vscode_parser.add_argument(
        "--host",
        type=str,
        required=True,
        metavar="HOST",
        help="Proxy host that VS Code should use to reach the proxy",
    )
    vscode_parser.add_argument(
        "--port",
        type=int,
        default=None,
        metavar="PORT",
        help="Proxy port (default: from profile)",
    )
    vscode_parser.add_argument(
        "--name",
        type=str,
        default=None,
        metavar="NAME",
        help="Custom provider name (default: CodeFreedom)",
    )
    vscode_parser.add_argument(
        "--out",
        type=str,
        default=None,
        metavar="FILE",
        help="Write to FILE instead of stdout",
    )

    proxy_parser = subparsers.add_parser(
        "proxy",
        help="Configure local or remote proxy settings",
    )
    proxy_parser.add_argument("--remote-url", type=str, default=None, help="Remote proxy base URL")
    proxy_parser.add_argument("--local", action="store_true", help="Remove remote proxy URL")
    proxy_parser.add_argument("--bind", type=str, default=None, metavar="HOST", help="Proxy bind host")

    tools_parser = subparsers.add_parser(
        "tools",
        help="Configure local or remote tool settings",
    )
    tools_parser.add_argument("tool", choices=["chrome", "web", "github", "web-bridge"])
    tools_parser.add_argument("--remote-url", type=str, default=None, help="Remote tool URL")
    tools_parser.add_argument("--local", action="store_true", help="Remove remote tool URL")
    tools_parser.add_argument("--bind", type=str, default=None, metavar="HOST", help="Tool bind host")

    bind_parser = subparsers.add_parser(
        "bind",
        help="Set the default bind address for proxy and tools",
    )
    bind_parser.add_argument("--address", required=True, metavar="HOST", help="Default bind address")


def handle_args(args: argparse.Namespace) -> int:
    """Handle parsed args and dispatch to the correct config target.

    Called from main.py after argument parsing.
    """
    target = getattr(args, "config_target", None)

    if target is None:
        eprint(f"{tag('CONFIG')} No target specified. Run 'cf setup config -h' for available targets.")
        return 1

    if target == "vscode":
        from codefreedom.cli.vscode import cmd_vscode_proxy_config

        return cmd_vscode_proxy_config(args)

    data = _load_override()

    if target == "proxy":
        if getattr(args, "local", False):
            _set_nested(data, ["common", "proxy", "remote_url"], None)
            _remove_proxy_master_key_marker(data)
        remote_url = getattr(args, "remote_url", None)
        if remote_url:
            if not _configure_remote_proxy(data, remote_url):
                return 1
        if getattr(args, "bind", None):
            _set_nested(data, ["common", "proxy", "bind_host"], args.bind)
        _write_override(data)
        eprint(f"{tag('CONFIG')} Proxy settings updated.")
        if remote_url:
            eprint(f"{tag('CONFIG')} Remote proxy validated at {remote_url}.")
        return 0

    if target == "tools":
        tool = getattr(args, "tool")
        if getattr(args, "local", False):
            _set_nested(data, ["tools", tool, "remote_url"], None)
        if getattr(args, "remote_url", None):
            if not _validate_remote_tool_url(tool, args.remote_url):
                eprint(f"{tag('CONFIG')} Remote tool validation failed for {tool}: {args.remote_url}.")
                eprint("   Expected a working MCP endpoint responding to tools/list. Settings were not saved.")
                return 1
            _set_nested(data, ["tools", tool, "remote_url"], args.remote_url)
        if getattr(args, "bind", None):
            _set_nested(data, ["tools", tool, "bind_host"], args.bind)
        _write_override(data)
        eprint(f"{tag('CONFIG')} Tool settings updated for {tool}.")
        if getattr(args, "remote_url", None):
            eprint(f"{tag('CONFIG')} Remote tool validated for {tool} at {args.remote_url}.")
        return 0

    if target == "bind":
        _set_nested(data, ["common", "bind_address"], args.address)
        _write_override(data)
        eprint(f"{tag('CONFIG')} Default bind address updated.")
        return 0

    eprint(f"{tag('ERROR')} Unknown config target: {target}")
    return 1
