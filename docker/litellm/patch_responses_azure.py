"""Disable responses-API auto-routing for Azure models.

LiteLLM 1.87.x auto-routes GPT-5.x chat completions through the Azure
Responses API when reasoning_effort + tools or reasoning_summary are
present (see litellm/main.py responses_api_bridge_check, line ~1003).

This patch removes "azure" from the condition so only OpenAI gets the
auto-routing.  Azure Foundry (services.ai.azure.com) does not reliably
serve the Responses API yet.

If the patch cannot be applied (condition shape changed), the build
fails loudly.
"""

from __future__ import annotations

import os
import sys


def patch_responses_azure() -> bool:
    import litellm

    pkg_dir = os.path.dirname(litellm.__file__)
    main_path = os.path.join(pkg_dir, "main.py")

    if not os.path.isfile(main_path):
        print(f"[patch:azure-responses] ERROR: main.py not found at {main_path}")
        return False

    with open(main_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Idempotent: already patched
    if 'custom_llm_provider == "openai"' in content:
        print("[patch:azure-responses] Already patched, skipping.")
        return True

    # The exact condition to patch.  LiteLLM 1.87.x uses this:
    #   custom_llm_provider in ("openai", "azure")
    # We replace it with:
    #   custom_llm_provider == "openai"
    old = 'custom_llm_provider in ("openai", "azure")'
    new = 'custom_llm_provider == "openai"'

    if old not in content:
        print(
            f"[patch:azure-responses] ERROR: Could not find target line in {main_path}."
            " LiteLLM may have changed the condition; update the patch."
        )
        return False

    content = content.replace(old, new)
    with open(main_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[patch:azure-responses] Patched {main_path}")
    return True


if __name__ == "__main__":
    ok = patch_responses_azure()
    sys.exit(0 if ok else 1)
