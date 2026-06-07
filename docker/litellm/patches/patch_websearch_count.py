"""Bake the WebSearch count patch into the LiteLLM image at build time.

LiteLLM's `try_short_circuit_search` (handler.py) constructs the response with:

    "usage": {"input_tokens": 0, "output_tokens": 0}

This omits the `server_tool_use.web_search_requests` field that Claude Code's
TUI uses to display "Did N searches". This patch injects the missing field.

The patch has three parts:

1. Short-circuit path (handler.py: ~218): hardcoded count of 1, since the
   short-circuit only fires for single-search requests (all tools are web
   search tools, simple prompt, no prior conversation history).

2. Agentic loop typed-plan path: `async_build_agentic_loop_plan` records
   `websearch_count = len(tool_calls)` in plan metadata, and
   `async_post_agentic_loop_response_hook` injects it into the response
   usage. This is the path Claude Code hits when it sends a multi-turn
   conversation with a `web_search_20250305` tool alongside other tools
   (Bash, Read, etc.) — the LLM returns a `tool_use` block, the agentic
   loop executes the search, then a follow-up call to the LLM synthesizes
   the final answer.

3. Agentic loop legacy path (`_execute_agentic_loop`): the count is
   injected directly after the follow-up call, using `len(tool_calls)`.

Run from Dockerfile.LiteLLM as a build step (BEFORE the entrypoint wrapper
is stripped). The patch modifies the installed site-packages file in place
— the modified file is then frozen in the image layer.

If the patch cannot be applied (e.g. LiteLLM renamed the field or moved
the methods), the build fails loudly so we notice before shipping a broken
image.
"""

from __future__ import annotations

import os
import sys


# ── Shared helper ────────────────────────────────────────────────────────────
_INJECT_SEARCH_COUNT_METHOD = '''    @staticmethod
    def _inject_search_count(response: Any, count: int) -> Any:
        """Inject ``server_tool_use.web_search_requests`` into the response usage.

        Claude Code's TUI reads this field from the final response to render
        the "Did N searches" counter. The LLM's own usage dict doesn't include
        it (the LLM didn't do the search — we did), so we add it here.

        Handles both dict (short-circuit path) and pydantic object
        (anthropic_messages.acreate) response shapes.
        """
        if count <= 0:
            return response

        search_use = {"web_search_requests": count}

        if isinstance(response, dict):
            usage = response.get("usage") or {}
            if isinstance(usage, dict):
                usage = {**usage, "server_tool_use": search_use}
                response["usage"] = usage
            return response

        # Object case (pydantic model from anthropic_messages.acreate).
        # Try the cheapest path first; fall back to object.__setattr__ for
        # pydantic v2 models with extra="forbid".
        try:
            usage = getattr(response, "usage", None)
            if usage is None:
                return response
            try:
                usage.server_tool_use = search_use
                return response
            except (AttributeError, TypeError, ValueError):
                pass
            try:
                object.__setattr__(usage, "server_tool_use", search_use)
            except Exception:
                verbose_logger.debug(
                    f"WebSearchInterception: could not set server_tool_use on "
                    f"usage of type {type(usage).__name__}"
                )
        except Exception as e:
            verbose_logger.debug(
                f"WebSearchInterception: usage injection failed: {e}"
            )
        return response

'''

# Anchor: the existing `_inject_native_blocks` static method. The new
# `_inject_search_count` is inserted just before it so the two injection
# helpers sit side-by-side in the class.
_INJECT_NATIVE_BLOCKS_ANCHOR = '''    @staticmethod
    def _inject_native_blocks(
        response: Any, native_blocks: List[Dict[str, Any]]
    ) -> Any:'''


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
    if "_inject_search_count" in content:
        print("[patch] Already patched, skipping.")
        return True

    # ── Patch 1: short-circuit path (handler.py: ~218) ─────────────────
    # Hardcoded count of 1 — the short-circuit only fires for single-search
    # requests (all tools are web search tools, simple prompt).
    short_circuit_replacements = [
        (
            '"usage": {"input_tokens": 0, "output_tokens": 0},',
            '"usage": {"input_tokens": 0, "output_tokens": 0, "server_tool_use": {"web_search_requests": 1}},',
        ),
        (
            '"usage": {"input_tokens": 0, "output_tokens": 0}',
            '"usage": {"input_tokens": 0, "output_tokens": 0, "server_tool_use": {"web_search_requests": 1}}',
        ),
    ]
    # If a prior build already patched the short-circuit line, the old
    # patterns above won't match — that's fine, the line is already correct.
    # We only fail loudly if NEITHER the old pattern NOR an already-patched
    # form is found, which would mean LiteLLM changed the response shape.
    short_circuit_already_patched = (
        '"usage": {"input_tokens": 0, "output_tokens": 0, "server_tool_use":'
        in content
    )
    patched_short_circuit = short_circuit_already_patched
    if not short_circuit_already_patched:
        for old, new in short_circuit_replacements:
            if old in content:
                content = content.replace(old, new)
                patched_short_circuit = True
                break
    if not patched_short_circuit:
        print(
            f"[patch] ERROR: Could not find short-circuit usage line in {handler_path}."
            " LiteLLM may have changed the response shape; update the patch."
        )
        return False
    if short_circuit_already_patched:
        print("[patch] Short-circuit path already patched (prior build)")
    else:
        print("[patch] Patched short-circuit path (try_short_circuit_search)")

    # ── Patch 2: record search count in agentic-loop plan metadata ──────
    # The typed-plan path threads the count through `plan.metadata` so the
    # post-hook can read it back and inject it into the final response.
    old2 = '''        metadata: Dict[str, Any] = {
            "tool_type": "websearch",
            "response_format": "anthropic",
        }'''
    new2 = '''        metadata: Dict[str, Any] = {
            "tool_type": "websearch",
            "response_format": "anthropic",
            # codefreedom: search count for the post-hook to inject into
            # the response's usage dict so Claude Code TUI shows
            # "Did N searches". The LLM's own usage doesn't include this
            # because the LLM didn't perform the search — we did.
            "websearch_count": len(tool_calls),
        }'''
    if old2 not in content:
        print(
            "[patch] ERROR: Could not find metadata dict in "
            "async_build_agentic_loop_plan. Update the patch."
        )
        return False
    content = content.replace(old2, new2)
    print("[patch] Patched async_build_agentic_loop_plan (metadata)")

    # ── Patch 3: typed-plan post-hook injects the count ─────────────────
    # The post-hook runs after the agentic loop's follow-up call returns.
    # We add a search-count injection alongside the existing native-block
    # injection. Both run unconditionally when the hook is invoked.
    old3 = '''        native_blocks = plan.metadata.get(WEBSEARCH_NATIVE_BLOCKS_METADATA_KEY)
        if not native_blocks:
            return response
        return self._inject_native_blocks(response, native_blocks)'''
    new3 = '''        native_blocks = plan.metadata.get(WEBSEARCH_NATIVE_BLOCKS_METADATA_KEY)
        if native_blocks:
            response = self._inject_native_blocks(response, native_blocks)
        # codefreedom: inject the search count into usage so Claude Code's
        # TUI renders "Did N searches". The count comes from plan metadata
        # (set in async_build_agentic_loop_plan).
        count = plan.metadata.get("websearch_count", 0)
        if count:
            response = self._inject_search_count(response, count)
        return response'''
    if old3 not in content:
        print(
            "[patch] ERROR: Could not find async_post_agentic_loop_response_hook"
            " body. Update the patch."
        )
        return False
    content = content.replace(old3, new3)
    print("[patch] Patched async_post_agentic_loop_response_hook")

    # ── Patch 4: legacy _execute_agentic_loop injects the count ─────────
    # The legacy path runs the follow-up call directly (bypassing the typed
    # plan dispatcher) and must inject the count itself to keep behavior
    # identical to the typed path.
    old4 = '''        # Legacy path: the new path goes through the typed plan + core
        # dispatcher which runs the post-hook automatically. Mirror the
        # native-block injection here so both paths behave identically.
        if kwargs.get(WEBSEARCH_EMIT_NATIVE_BLOCKS_KEY):
            native_blocks = self._build_native_result_blocks(
                tool_calls=tool_calls,
                structured_results=structured_results,
            )
            response = self._inject_native_blocks(response, native_blocks)

        return response'''
    new4 = '''        # Legacy path: the new path goes through the typed plan + core
        # dispatcher which runs the post-hook automatically. Mirror the
        # native-block injection here so both paths behave identically.
        if kwargs.get(WEBSEARCH_EMIT_NATIVE_BLOCKS_KEY):
            native_blocks = self._build_native_result_blocks(
                tool_calls=tool_calls,
                structured_results=structured_results,
            )
            response = self._inject_native_blocks(response, native_blocks)

        # codefreedom: mirror the search-count injection for the legacy
        # path so Claude Code TUI shows "Did N searches".
        response = self._inject_search_count(response, len(tool_calls))

        return response'''
    if old4 not in content:
        print(
            "[patch] ERROR: Could not find _execute_agentic_loop tail."
            " Update the patch."
        )
        return False
    content = content.replace(old4, new4)
    print("[patch] Patched _execute_agentic_loop (legacy path)")

    # ── Patch 5: add _inject_search_count helper to the class ───────────
    # Insert just before _inject_native_blocks so the two injection helpers
    # sit side-by-side in the source.
    if _INJECT_NATIVE_BLOCKS_ANCHOR not in content:
        print(
            "[patch] ERROR: Could not find _inject_native_blocks anchor."
            " Update the patch."
        )
        return False
    content = content.replace(
        _INJECT_NATIVE_BLOCKS_ANCHOR,
        _INJECT_SEARCH_COUNT_METHOD + _INJECT_NATIVE_BLOCKS_ANCHOR,
    )
    print("[patch] Added _inject_search_count helper method")

    with open(handler_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[patch] Patched {handler_path}")
    return True


if __name__ == "__main__":
    ok = patch_handler()
    sys.exit(0 if ok else 1)
