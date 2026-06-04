"""Shared utilities for tool initialization — acceptance prompt, notices, metadata.

Each tool (chrome, web/camoufox) uses these for init and start flows.
"""

from __future__ import annotations

from typing import Dict

from codefreedom.env_loader import eprint

# ── Tool metadata ────────────────────────────────────────────────────────────

TOOL_INFO: Dict[str, dict] = {
    "chrome": {
        "name": "Chrome Browser",
        "description": (
            "Chrome browser with Xvfb virtual display for undetectable headed browsing. "
            "Coding agents connect via Chrome DevTools Protocol (CDP) at port 9222."
        ),
        "third_party": [
            ("Google Chrome / Chromium", "Google LLC"),
            ("Xvfb (virtual display)", "X.org Foundation"),
            ("PulseAudio (virtual audio)", "freedesktop.org"),
            ("MS Core Fonts (Arial, Times New Roman, etc.)", "Microsoft Corporation"),
            ("dumb-init (PID 1 supervisor)", "Yelp, Inc."),
        ],
        "docs_url": "https://nilayparikh.github.io/codefreedom/claude-code/tools/",
        "profile_name": "chrome.json",
    },
    "web": {
        "name": "Camoufox Web Search (MCP)",
        "description": (
            "Camoufox stealth browser for web search and scraping. "
            "Runs an MCP server on port 8420 with web_search and web_fetch tools. "
            "Search engines are user-configured via the profile."
        ),
        "third_party": [
            ("Camoufox (stealth browser)", "daijro"),
            ("Firefox", "Mozilla Foundation"),
        ],
        "warning": (
            "The Camoufox scraping tool is designed for internal websites "
            "or permissible public infrastructure. "
            "DO NOT USE or REPURPOSE the tool beyond permissible use cases."
        ),
        "docs_url": "https://nilayparikh.github.io/codefreedom/claude-code/tools/",
        "profile_name": "camoufox.json",
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
    print(
        f"[{tag}] CodeFreedom is not responsible"
        f" for their behavior, security, or privacy practices."
    )
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
    the user to type 'I understand' to proceed.

    Returns True if accepted, False otherwise.
    """
    info = TOOL_INFO.get(tool_name)
    if not info:
        eprint(f"[init] Unknown tool: {tool_name}")
        return False

    print()
    print(f"─── {info['name']} ──────────────────────────────────────────")
    print(info["description"])
    print()
    print("Third-party components:")
    for component, vendor in info["third_party"]:
        print(f"  • {component} — {vendor}")
    print()
    print("By continuing, you acknowledge that this tool uses")
    print("third-party components. " + _THIRD_PARTY_NOTICE)
    print()
    print("Documentation: " + info["docs_url"])
    print()
    try:
        response = input("Type 'I understand' to continue: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        eprint("[init] Init aborted.")
        return False

    if response.lower() == "i understand":
        return True

    eprint("[init] Init aborted — you must type 'I understand' to proceed.")
    return False
