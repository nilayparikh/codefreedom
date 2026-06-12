"""VS Code subcommand — arg parser and dispatch.

Imports implementations from ``agents.vscode.claude_settings`` and
``agents.vscode.proxy_models``.
"""

from __future__ import annotations

import argparse

from codefreedom.agents.vscode.claude_settings import (
    _VSCODE_PREFERRED_LOCATION,
    _VSCODE_SANDBOX_ONLY_KEYS,
    _VSCODE_SECRET_SUBSTRINGS,
    _build_vscode_environment_variables,
    _build_vscode_settings,
    _is_secret_env_var,
    cmd_vscode_claude_config,
)
from codefreedom.agents.vscode.proxy_models import (
    _STANDARD_REASONING_EFFORT_LEVELS,
    _VSCODE_APIKEY_PLACEHOLDER,
    _build_vscode_entry,
    _check_proxy_live,
    _deduplicate_models,
    _fetch_model_info,
    _model_to_vscode_entry,
    _proxy_health_url,
    _proxy_model_info_url,
    _resolve_master_key,
    _resolve_model_id,
    _resolve_reasoning_effort,
    cmd_vscode_proxy_config,
)

__all__ = [
    "_STANDARD_REASONING_EFFORT_LEVELS",
    "_VSCODE_APIKEY_PLACEHOLDER",
    "_VSCODE_PREFERRED_LOCATION",
    "_VSCODE_SANDBOX_ONLY_KEYS",
    "_VSCODE_SECRET_SUBSTRINGS",
    "_build_vscode_entry",
    "_build_vscode_environment_variables",
    "_build_vscode_settings",
    "_check_proxy_live",
    "_deduplicate_models",
    "_fetch_model_info",
    "_is_secret_env_var",
    "_model_to_vscode_entry",
    "_proxy_health_url",
    "_proxy_model_info_url",
    "_resolve_master_key",
    "_resolve_model_id",
    "_resolve_reasoning_effort",
    "build_parser",
    "cmd_vscode_claude_config",
    "cmd_vscode_proxy_config",
]


def build_parser(parser: argparse.ArgumentParser) -> None:
    """Build the ``vscode`` subcommand parser for ``codefreedom config``."""
    sub = parser.add_subparsers(dest="vscode_action", title="vscode targets")
    sub.required = True

    # vscode claude config
    vscode_claude = sub.add_parser(
        "claude",
        help="Generate VS Code settings for the Claude Code extension",
        description="Generate a VS Code settings.json fragment (claudeCode.* keys).",
    )
    vscode_claude.add_argument(
        "--profile",
        type=str,
        default="default",
        metavar="NAME",
        help="Profile to generate settings for (default: 'default')",
    )
    vscode_claude.add_argument(
        "--host",
        type=str,
        default=None,
        metavar="HOST",
        help="Override ANTHROPIC_BASE_URL host",
    )
    vscode_claude.add_argument(
        "--port",
        type=int,
        default=None,
        metavar="PORT",
        help="Override ANTHROPIC_BASE_URL port",
    )
    vscode_claude.add_argument(
        "--out",
        type=str,
        default=None,
        metavar="PATH",
        help="Write output to a file instead of stdout",
    )

    # vscode proxy config
    vscode_proxy = sub.add_parser(
        "proxy",
        help="Generate VS Code config from the running proxy",
        description="Probe the running proxy and emit a chatLanguageModels.json entry.",
    )
    vscode_proxy.add_argument(
        "--host",
        type=str,
        required=True,
        metavar="HOST",
        help="Proxy hostname or IP (required)",
    )
    vscode_proxy.add_argument(
        "--port",
        type=int,
        default=4000,
        metavar="PORT",
        help="Proxy port (default: 4000)",
    )
    vscode_proxy.add_argument(
        "--name",
        type=str,
        default="CodeFreedom Proxy",
        metavar="NAME",
        help="Provider display name (default: 'CodeFreedom Proxy')",
    )
    vscode_proxy.add_argument(
        "--out",
        type=str,
        default=None,
        metavar="PATH",
        help="Write output to a file instead of stdout",
    )
