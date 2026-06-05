"""Monkey-patch LiteLLM's websearch_interception handler to report proper search count.

LiteLLM's try_short_circuit_search (handler.py:218) constructs the response with:
    "usage": {"input_tokens": 0, "output_tokens": 0}

This omits the server_tool_use.web_search_requests field that Claude Code's TUI
uses to display "Did N searches". This patch injects the missing field.

Usage:
    python3 patch_websearch_count.py

Runs before LiteLLM starts. Patches the installed site-packages file in-place.
"""

import os
import re

HANDLER_PATH = os.path.join(
    os.path.dirname(__file__) or os.getcwd(),
    "..",  # go up one level from the script location
)

# Actually, find it relative to the litellm package
def patch_handler():
    # Find the handler.py in the litellm package
    import litellm
    
    pkg_dir = os.path.dirname(litellm.__file__)
    handler_path = os.path.join(
        pkg_dir,
        "integrations", "websearch_interception", "handler.py"
    )
    
    with open(handler_path, "r") as f:
        content = f.read()
    
    # Check if already patched
    if "web_search_requests" in content:
        print("[patch] Already patched, skipping.")
        return True
    
    # The exact usage line to replace (trailing comma is part of the dict literal)
    # Try with trailing comma first (current format), fallback to without
    replacements = [
        (
            '"usage": {"input_tokens": 0, "output_tokens": 0},',
            '"usage": {"input_tokens": 0, "output_tokens": 0, "server_tool_use": {"web_search_requests": 1}},',
        ),
        (
            '"usage": {"input_tokens": 0, "output_tokens": 0}',
            '"usage": {"input_tokens": 0, "output_tokens": 0, "server_tool_use": {"web_search_requests": 1}}',
        ),
    ]
    
    patched = False
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            patched = True
            break
    
    if not patched:
        print(f"[patch] ERROR: Could not find usage line in {handler_path}")
        return False
    
    with open(handler_path, "w") as f:
        f.write(content)
    
    print(f"[patch] Patched {handler_path}")
    return True


if __name__ == "__main__":
    success = patch_handler()
    exit(0 if success else 1)
