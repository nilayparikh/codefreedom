"""Patch ``_handle_anthropic_messages_response_logging`` to handle ``FakeAnthropicMessagesStreamIterator``.

Root cause
----------
When ``litellm.use_chat_completions_url_for_anthropic_messages = True`` and a
streaming request is made, the experimental pass-through handler returns a
``FakeAnthropicMessagesStreamIterator`` (a streaming wrapper that emits
Anthropic SSE chunks).  The success handler
(``_handle_anthropic_messages_response_logging``) only has early-return paths
for ``ModelResponse`` instances.  Since ``FakeAnthropicMessagesStreamIterator``
is NOT a ``ModelResponse``, the code falls through to::

    AnthropicResponse.model_validate(result)

which fails with a ``ValidationError`` because the argument is an iterator
object, not a dict or ``AnthropicResponse``.

The error is non-blocking (caught and logged as "[Non-Blocking]
LiteLLM.Success_Call Error") but spams the logs on every streaming request.

Fix
---
Add an early-return guard that checks for
``FakeAnthropicMessagesStreamIterator`` before the ``model_validate`` call.
Since this is a streaming iterator, the actual response logging is handled by
the stream-chunk processing path; returning it as-is is correct.

Run from Dockerfile.LiteLLM as a build step.  Idempotent.
"""

from __future__ import annotations

import os
import sys

# The else-branch where AnthropicResponse.model_validate is called.
_ORIGINAL_ELSE = """\
        else:
            from litellm.types.llms.anthropic import AnthropicResponse

            pydantic_result = AnthropicResponse.model_validate(result)"""

# Patched version: add a guard for FakeAnthropicMessagesStreamIterator.
_PATCHED_ELSE = """\
        else:
            from litellm.llms.anthropic.experimental_pass_through.messages.fake_stream_iterator import (
                FakeAnthropicMessagesStreamIterator,
            )
            if isinstance(result, FakeAnthropicMessagesStreamIterator):
                return result

            from litellm.types.llms.anthropic import AnthropicResponse

            pydantic_result = AnthropicResponse.model_validate(result)"""


def patch_logging() -> bool:
    """Apply the guard patch to ``_handle_anthropic_messages_response_logging``.

    Returns True on success, False on failure.  Idempotent.
    """
    import litellm

    pkg_dir = os.path.dirname(litellm.__file__)
    logging_path = os.path.join(pkg_dir, "litellm_core_utils", "litellm_logging.py")

    if not os.path.isfile(logging_path):
        print(f"[patch] ERROR: litellm_logging.py not found at {logging_path}")
        return False

    with open(logging_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Already patched — idempotent.
    if "FakeAnthropicMessagesStreamIterator" in content:
        print("[patch] Already applied — nothing to do.")
        return True

    if _ORIGINAL_ELSE not in content:
        print(
            f"[patch] ERROR: anchor block not found in {logging_path}\n"
            f"  LiteLLM may have changed — check the source and update "
            f"the patch."
        )
        return False

    content = content.replace(_ORIGINAL_ELSE, _PATCHED_ELSE, 1)

    with open(logging_path, "w", encoding="utf-8") as f:
        f.write(content)

    # Verify.
    if "FakeAnthropicMessagesStreamIterator" in content:
        print(
            "[patch] Successfully patched _handle_anthropic_messages_response_logging."
        )
        return True

    print("[patch] ERROR: verification failed after write.")
    return False


def main() -> None:
    success = patch_logging()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
