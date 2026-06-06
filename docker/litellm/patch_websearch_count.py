"""Bake the WebSearch count patch into the LiteLLM image at build time.

LiteLLM's `try_short_circuit_search` (handler.py:218) constructs the response with:

    "usage": {"input_tokens": 0, "output_tokens": 0}

This omits the `server_tool_use.web_search_requests` field that Claude Code's
TUI uses to display "Did N searches". This patch injects the missing field.

Run from Dockerfile.LiteLLM as a build step (BEFORE the entrypoint wrapper is
stripped). The patch modifies the installed site-packages file in place —
the modified file is then frozen in the image layer.

If the patch cannot be applied (e.g. LiteLLM renamed the field), the build
fails loudly so we notice before shipping a broken image.
"""

from __future__ import annotations

import os
import sys


def patch_handler() -> bool:
    """Apply the WebSearch count patch to the installed litellm package.

    Returns True on success, False on failure.  Idempotent — re-running on
    an already-patched file is a no-op.
    """
    import litellm

    pkg_dir = os.path.dirname(litellm.__file__)
    handler_path = os.path.join(
        pkg_dir, "integrations", "websearch_interception", "handler.py"
    )

    if not os.path.isfile(handler_path):
        print(f"[patch] ERROR: handler.py not found at {handler_path}")
        return False

    with open(handler_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Idempotent: already patched
    if "web_search_requests" in content:
        print("[patch] Already patched, skipping.")
        return True

    # The exact usage line to replace.  Trailing comma is part of the dict
    # literal in current LiteLLM releases; the comma-less form is kept as
    # a fallback for older versions.
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

    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            break
    else:
        print(
            f"[patch] ERROR: Could not find usage line in {handler_path}."
            " LiteLLM may have changed the response shape; update the patch."
        )
        return False

    with open(handler_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[patch] Patched {handler_path}")
    return True


if __name__ == "__main__":
    ok = patch_handler()
    sys.exit(0 if ok else 1)
