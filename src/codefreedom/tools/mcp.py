from __future__ import annotations

from typing import Any

from codefreedom.config import load_config
from codefreedom.config.errors import ConfigError


def is_mcp_tool(name: str) -> bool:
    try:
        cfg = load_config().tools.get(name, {}) or {}
    except ConfigError:
        return False
    return isinstance(cfg, dict) and cfg.get("kind") == "mcp"


def get_mcp_definition(name: str) -> dict[str, Any] | None:
    try:
        cfg = load_config().tools.get(name, {}) or {}
    except ConfigError:
        return None
    if not isinstance(cfg, dict) or cfg.get("kind") != "mcp":
        return None
    transport = str(cfg.get("transport") or "").strip().lower()
    server_name = str(cfg.get("server_name") or name)
    enabled = bool(cfg.get("enabled", True))
    timeout = cfg.get("timeout")
    if transport == "local":
        command = cfg.get("command")
        if isinstance(command, str):
            command = [command]
        if not isinstance(command, list) or not command:
            return None
        return {
            "name": server_name,
            "transport": "local",
            "command": [str(part) for part in command],
            "cwd": cfg.get("cwd"),
            "environment": dict(cfg.get("environment", {}) or {}),
            "enabled": enabled,
            "timeout": int(timeout) if timeout is not None else None,
        }
    if transport == "remote":
        url = cfg.get("url")
        if not isinstance(url, str) or not url:
            return None
        oauth = cfg.get("oauth")
        return {
            "name": server_name,
            "transport": "remote",
            "url": url,
            "headers": dict(cfg.get("headers", {}) or {}),
            "oauth": oauth,
            "enabled": enabled,
            "timeout": int(timeout) if timeout is not None else None,
        }
    return None


def get_mcp_definitions(names: list[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name in names:
        definition = get_mcp_definition(name)
        if not definition:
            continue
        server_name = str(definition["name"])
        if server_name in seen:
            continue
        seen.add(server_name)
        result.append(definition)
    return result


def build_claude_mcp_servers(names: list[str]) -> dict[str, dict[str, Any]]:
    servers: dict[str, dict[str, Any]] = {}
    for definition in get_mcp_definitions(names):
        if definition["transport"] == "local":
            server: dict[str, Any] = {
                "type": "stdio",
                "command": definition["command"][0],
            }
            if len(definition["command"]) > 1:
                server["args"] = definition["command"][1:]
            if definition.get("environment"):
                server["env"] = definition["environment"]
            if definition.get("cwd"):
                server["cwd"] = definition["cwd"]
            if definition.get("timeout") is not None:
                server["timeout"] = definition["timeout"]
            servers[definition["name"]] = server
            continue
        server = {
            "type": "http",
            "url": definition["url"],
        }
        if definition.get("headers"):
            server["headers"] = definition["headers"]
        if definition.get("oauth") is not None:
            server["oauth"] = definition["oauth"]
        if definition.get("timeout") is not None:
            server["timeout"] = definition["timeout"]
        servers[definition["name"]] = server
    return servers


def build_opencode_mcp_entries(names: list[str]) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for definition in get_mcp_definitions(names):
        if definition["transport"] == "local":
            entry: dict[str, Any] = {
                "type": "local",
                "command": definition["command"],
                "enabled": definition["enabled"],
            }
            if definition.get("environment"):
                entry["environment"] = definition["environment"]
            if definition.get("cwd"):
                entry["cwd"] = definition["cwd"]
            if definition.get("timeout") is not None:
                entry["timeout"] = definition["timeout"]
            entries[definition["name"]] = entry
            continue
        entry = {
            "type": "remote",
            "url": definition["url"],
            "enabled": definition["enabled"],
        }
        if definition.get("headers"):
            entry["headers"] = definition["headers"]
        if definition.get("oauth") is not None:
            entry["oauth"] = definition["oauth"]
        if definition.get("timeout") is not None:
            entry["timeout"] = definition["timeout"]
        entries[definition["name"]] = entry
    return entries


def build_codex_mcp_entries(names: list[str]) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for definition in get_mcp_definitions(names):
        if definition["transport"] == "local":
            entry: dict[str, Any] = {
                "command": definition["command"][0],
            }
            if len(definition["command"]) > 1:
                entry["args"] = definition["command"][1:]
            if definition.get("environment"):
                entry["env"] = definition["environment"]
            if definition.get("cwd"):
                entry["cwd"] = definition["cwd"]
            if definition.get("timeout") is not None:
                entry["startup_timeout_ms"] = definition["timeout"]
            entries[definition["name"]] = entry
            continue
        entry = {"url": definition["url"]}
        if definition.get("headers"):
            entry["headers"] = definition["headers"]
        if definition.get("timeout") is not None:
            entry["startup_timeout_ms"] = definition["timeout"]
        entries[definition["name"]] = entry
    return entries
