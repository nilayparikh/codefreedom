"""Pure rendering functions for generated recipe artifacts.

Produce bash scripts, PowerShell scripts, env templates, and summary
metadata from structured recipe metadata. All functions are deterministic
and side-effect free.
"""

from __future__ import annotations

from typing import Any


def render_bash_setup_script(
    recipe_name: str,
    secrets: list[dict[str, str]],
    config_vars: list[dict[str, str]],
    service_groups: list[dict[str, Any]],
) -> str:
    lines: list[str] = []
    lines.append("#!/usr/bin/env bash")
    lines.append(f"# {recipe_name} — setup script")
    lines.append("set -euo pipefail")
    lines.append("")

    if service_groups:
        lines.append("# --- Service groups ---")
        for group in service_groups:
            name = group["name"]
            requires = ", ".join(group.get("requires", []))
            lines.append(f"# Group: {name}" + (f" (requires: {requires})" if requires else ""))
        lines.append("")

    if secrets:
        lines.append("# --- Secrets ---")
        for s in secrets:
            var = s["var"]
            prompt = s["prompt"]
            default = s.get("default")
            if default:
                lines.append(f'read -p "{prompt} [{default}]: " {var}')
                lines.append(f'{var}="${{{var}:-{default}}}"')
            else:
                lines.append(f'read -p "{prompt}: " {var}')
        lines.append("")

    if config_vars:
        lines.append("# --- Configuration ---")
        for c in config_vars:
            var = c["var"]
            prompt = c["prompt"]
            default = c.get("default")
            if default:
                lines.append(f'read -p "{prompt} [{default}]: " {var}')
                lines.append(f'{var}="${{{var}:-{default}}}"')
            else:
                lines.append(f'read -p "{prompt}: " {var}')
        lines.append("")

    lines.append('echo "Setup complete for {recipe_name}"')
    return "\n".join(lines) + "\n"


def render_powershell_setup_script(
    recipe_name: str,
    secrets: list[dict[str, str]],
    config_vars: list[dict[str, str]],
    service_groups: list[dict[str, Any]],
) -> str:
    lines: list[str] = []
    lines.append(f"# {recipe_name} — PowerShell setup script")
    lines.append("$ErrorActionPreference = 'Stop'")
    lines.append("")

    if service_groups:
        lines.append("# --- Service groups ---")
        for group in service_groups:
            name = group["name"]
            requires = ", ".join(group.get("requires", []))
            lines.append(f"# Group: {name}" + (f" (requires: {requires})" if requires else ""))
        lines.append("")

    if secrets:
        lines.append("# --- Secrets ---")
        for s in secrets:
            var = s["var"]
            prompt = s["prompt"]
            default = s.get("default")
            if default:
                lines.append(f'${var} = Read-Host "{prompt} [{default}]"')
                lines.append(f'if (-not ${var}) {{ ${var} = "{default}" }}')
            else:
                lines.append(f'${var} = Read-Host "{prompt}"')
        lines.append("")

    if config_vars:
        lines.append("# --- Configuration ---")
        for c in config_vars:
            var = c["var"]
            prompt = c["prompt"]
            default = c.get("default")
            if default:
                lines.append(f'${var} = Read-Host "{prompt} [{default}]"')
                lines.append(f'if (-not ${var}) {{ ${var} = "{default}" }}')
            else:
                lines.append(f'${var} = Read-Host "{prompt}"')
        lines.append("")

    lines.append(f'Write-Host "Setup complete for {recipe_name}"')
    return "\n".join(lines) + "\n"


def render_env_template(secrets: list[dict[str, str]]) -> str:
    if not secrets:
        return ""
    lines: list[str] = []
    for s in secrets:
        var = s["var"]
        default = s.get("default", "CHANGE_ME")
        lines.append(f"{var}={default}")
    return "\n".join(lines) + "\n"


def render_recipe_summary_metadata(manifest: dict[str, Any]) -> dict[str, Any]:
    secrets = manifest.get("required_secrets", [])
    config_vars = manifest.get("config_vars", [])
    service_groups = manifest.get("service_groups", [])
    return {
        "name": manifest.get("name", ""),
        "secret_count": len(secrets),
        "config_count": len(config_vars),
        "service_groups": [
            {"name": g["name"], "requires": g.get("requires", [])}
            for g in service_groups
        ],
    }
