"""Shared utilities for tool initialization — acceptance prompt, notices, metadata.

Each tool (chrome, web) uses these for init and start flows.
"""

from __future__ import annotations

from typing import Dict

from codefreedom.env_loader import eprint

# ── Tool metadata ────────────────────────────────────────────────────────────

TOOL_INFO: Dict[str, dict] = {
    "chrome": {
        "name": "Chrome Browser (Headless)",
        "description": (
            "Headless Google Chrome for browser automation. "
            "Coding agents connect via Chrome DevTools Protocol (CDP) at port 9222."
        ),
        "third_party": [
            ("Google Chrome / Chromium", "Google LLC"),
            ("dumb-init (PID 1 supervisor)", "Yelp, Inc."),
        ],
        "docs_url": "https://nilayparikh.github.io/codefreedom/tools/chrome/",
        "profile_name": "chrome.yaml",
    },
    "web": {
        "name": "Web Search (MCP)",
        "description": (
            "Web search and scraping via a headless browser. "
            "Runs an MCP server on port 8420 with web_search and web_fetch tools. "
            "Search engines are user-configured via the profile."
        ),
        "third_party": [
            ("Camoufox (stealth browser)", "daijro"),
            ("Firefox", "Mozilla Foundation"),
        ],
        "warning": (
            "The web scraping tool is designed for internal websites "
            "or permissible public infrastructure. "
            "DO NOT USE or REPURPOSE the tool beyond permissible use cases."
        ),
        "docs_url": "https://nilayparikh.github.io/codefreedom/tools/web/",
        "profile_name": "web.yaml",
    },
    "github": {
        "name": "GitHub MCP Server",
        "description": (
            "GitHub MCP Server running the official ghcr.io/github/github-mcp-server "
            "image. Provides GitHub API tools for issues, PRs, repos, and more "
            "via the Model Context Protocol. Requires GITHUB_PERSONAL_ACCESS_TOKEN."
        ),
        "third_party": [
            ("GitHub MCP Server", "GitHub, Inc."),
        ],
        "warning": (
            "This tool requires a GITHUB_PERSONAL_ACCESS_TOKEN with appropriate "
            "repository permissions. Store the token securely in the profile's env section."
        ),
        "docs_url": "https://nilayparikh.github.io/codefreedom/tools/github/",
        "profile_name": "github.yaml",
    },
}

# ── Disclaimers ──────────────────────────────────────────────────────────────

_NON_DISCLAIMER = """\
--- Notice ----------------------------------------------------------
CodeFreedom is provided \"as is\", without warranty of any kind.
See the Apache 2.0 License for details.
---------------------------------------------------------------------"""

_THIRD_PARTY_NOTICE = (
    "CodeFreedom is not responsible"
    " for their behavior, security, or privacy practices."
)


_TAG_MAP: Dict[str, str] = {
    "chrome": "CHROME",
    "web": "WEB",
    "github": "GITHUB",
}


def _print_tool_notice(tool_name: str) -> None:
    """Print a third-party component notice for a specific tool."""
    info = TOOL_INFO.get(tool_name)
    if not info:
        return

    tag = _TAG_MAP.get(tool_name, tool_name.upper())
    components = info["third_party"]
    print()
    print(f"[{tag}] --- Third-Party Notice ---")
    print(f"[{tag}] This container includes third-party components:")
    for component, vendor in components:
        print(f"[{tag}]   * {component} ({vendor})")
    print(f"[{tag}]")
    print(f"[{tag}] {_THIRD_PARTY_NOTICE}")
    if "warning" in info:
        print(f"[{tag}]")
        print(f"[{tag}] WARNING: {info['warning']}")
    print(f"[{tag}] ---")


def _print_non_disclaimer() -> None:
    """Print the general non-disclaimer banner."""
    print(_NON_DISCLAIMER)


def prompt_acceptance(tool_name: str) -> bool:
    """Prompt user to accept understanding of tool contents.

    Prints tool description, third-party components, and requires
    the user to confirm with 'y' to proceed. Default is 'n' (decline).

    Returns True if accepted, False otherwise.
    """
    info = TOOL_INFO.get(tool_name)
    if not info:
        eprint(f"[init] Unknown tool: {tool_name}")
        return False

    print()
    print(f"--- {info['name']} " + "-" * 50)
    print(info["description"])
    print()
    print("Third-party components:")
    for component, vendor in info["third_party"]:
        print(f"  * {component} -- {vendor}")
    print()
    print("By continuing, you acknowledge that this tool uses")
    print("third-party components. " + _THIRD_PARTY_NOTICE)
    print()
    print("Documentation: " + info["docs_url"])
    print()
    try:
        response = input("Continue? [y/N]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        eprint("[init] Init aborted.")
        return False

    if response.lower() == "y":
        return True

    eprint("[init] Init aborted.")
    return False


# ── Help/usage formatting ────────────────────────────────────────────────────


def print_help_section(
    title: str,
    usage_lines: list[str],
    docs_url: str = "",
    include_disclaimer: bool = True,
) -> None:
    """Print a standardized help section (ASCII only, no Unicode).

    Parameters
    ----------
    title:
        Tag printed in brackets, e.g. ``"claude init"``.
    usage_lines:
        Lines of usage info. Each is prefixed with two spaces.
    docs_url:
        Optional documentation URL printed after usage lines.
    include_disclaimer:
        Whether to append the standard non-warranty disclaimer.
    """
    print(f"[{title}]")
    print()
    for line in usage_lines:
        print(f"  {line}")
    print()
    if docs_url:
        print(f"  Docs: {docs_url}")
        print()
    if include_disclaimer:
        _print_non_disclaimer()
