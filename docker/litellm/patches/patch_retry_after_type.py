"""Bake a defensive type cast for ``min_timeout`` into the image at build time.

LiteLLM's YAML config resolver (``get_secret`` in
``litellm/secret_managers/main.py``) always returns **strings** for
``os.environ/``-prefixed config values, because environment variables are
always strings.  When a numeric router setting like ``retry_after`` is
specified via ``os.environ/LITELLM_RETRY_AFTER``, the string ``"0"`` is
passed to ``Router(retry_after="0")`` and stored as ``self.retry_after =
"0"`` (a str).

Later, ``_calculate_retry_after`` does::

    sleep_seconds = max(sleep_seconds, min_timeout)

where ``min_timeout`` (``self.retry_after``) is the string ``"0"`` and
``sleep_seconds`` is a float.  Python 3 raises::

    TypeError: '>' not supported between instances of 'str' and 'float'

This patch wraps the ``min_timeout`` argument in ``float()`` right at the
point of use, so a string value is converted before the comparison.
``float()`` accepts str, int, and float, so the change is backwards
compatible for *all* current datatypes that reach this line.

Run from Dockerfile.LiteLLM as a build step (before the entrypoint
wrapper is stripped).  The patch modifies the installed site-packages
file in place — the modified file is then frozen in the image layer.
"""

from __future__ import annotations

import os
import sys

# The original line inside ``_calculate_retry_after`` in ``litellm/utils.py``.
_ORIGINAL_LINE = "    sleep_seconds = max(sleep_seconds, min_timeout)"

# The patched version wraps min_timeout in float().
_PATCHED_LINE = "    sleep_seconds = max(sleep_seconds, float(min_timeout))"


def patch_utils() -> bool:
    """Apply the type-cast patch to ``_calculate_retry_after``.

    Returns True on success, False on failure.  Idempotent — re-running
    on an already-patched file is a no-op (the line is already changed).
    """
    import litellm

    pkg_dir = os.path.dirname(litellm.__file__)
    utils_path = os.path.join(pkg_dir, "utils.py")

    if not os.path.isfile(utils_path):
        print(f"[patch] ERROR: utils.py not found at {utils_path}")
        return False

    with open(utils_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Already patched — idempotent.
    if _PATCHED_LINE in content:
        print("[patch] Already applied — nothing to do.")
        return True

    if _ORIGINAL_LINE not in content:
        # Also check with single-quote formatting as an alternative
        # (unlikely but defensive).
        alt_orig = "    sleep_seconds = max(sleep_seconds, min_timeout)"
        if alt_orig in content:
            print(
                "[patch] ERROR: found single-quote variant but expected "
                f"double: {_ORIGINAL_LINE!r}"
            )
            return False
        print(
            f"[patch] ERROR: anchor line not found in {utils_path}\n"
            f"  Expected: {_ORIGINAL_LINE!r}\n"
            f"  LiteLLM may have changed — check the source and update "
            f"the patch."
        )
        return False

    content = content.replace(_ORIGINAL_LINE, _PATCHED_LINE, 1)

    with open(utils_path, "w", encoding="utf-8") as f:
        f.write(content)

    # Verify.
    if _PATCHED_LINE in content:
        print("[patch] Successfully patched _calculate_retry_after.")
        return True

    print("[patch] ERROR: verification failed after write.")
    return False


def main() -> None:
    success = patch_utils()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
