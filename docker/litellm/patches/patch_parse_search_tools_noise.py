"""Suppress spurious parse_search_tools print on periodic DB refreshes.

Root cause
----------
``ProxyConfig.parse_search_tools()`` unconditionally prints::

    LiteLLM: Proxy initialized with Search Tools:
        <tool_name> (<provider>)

every time it is called.  This method is invoked not only during initial
startup but also every 30 seconds by the ``add_deployment`` background
scheduler job::

    scheduler.add_job(proxy_config.add_deployment, "interval", seconds=30, ...)

``add_deployment`` --> _update_llm_router --> parse_search_tools``,
so the message prints ad infinitum on every periodic DB poll.

Fix
---
Add a class-level ``_search_tools_printed`` sentinel so the two ``print()``
calls only fire on the first invocation.

Run from Dockerfile.LiteLLM as a build step.  Idempotent.
"""

from __future__ import annotations
import os, sys

HEADING_OLD = (
    "        print(  # noqa\n"
    '            "\\033[32mLiteLLM: Proxy initialized with Search Tools:\\033[0m"\n'
    "        )  # noqa\n"
)

HEADING_NEW = (
    '        if not getattr(self, "_search_tools_printed", False):\n'
    "            self._search_tools_printed = True\n"
    "            print(  # noqa\n"
    '                "\\033[32mLiteLLM: Proxy initialized with Search Tools:\\033[0m"\n'
    "            )  # noqa\n"
)

TOOLNAME_OLD = '            print(f"\\033[32m    {search_tool_name} ({search_provider})\\033[0m")  # noqa\n'

TOOLNAME_NEW = (
    '            if not getattr(self, "_search_tools_printed", False):\n'
    '                print(f"\\033[32m    {search_tool_name} ({search_provider})\\033[0m")  # noqa\n'
)


def patch_proxy_server(path=None):
    if path is None:
        import litellm

        path = os.path.join(
            os.path.dirname(litellm.__file__), "proxy", "proxy_server.py"
        )

    if not os.path.isfile(path):
        print(f"[patch] ERROR: not found at {path}")
        return False

    with open(path) as f:
        content = f.read()

    if "_search_tools_printed" in content:
        print("[patch] Already applied -- nothing to do.")
        return True

    if HEADING_OLD not in content:
        print("[patch] ERROR: heading anchor not found")
        return False
    content = content.replace(HEADING_OLD, HEADING_NEW, 1)

    if TOOLNAME_OLD not in content:
        print("[patch] ERROR: toolname anchor not found")
        return False
    content = content.replace(TOOLNAME_OLD, TOOLNAME_NEW, 1)

    with open(path, "w") as f:
        f.write(content)

    import py_compile

    try:
        py_compile.compile(path, doraise=True)
    except py_compile.PyCompileError as e:
        print(f"[patch] SYNTAX ERROR: {e}")
        return False

    print("[patch] Successfully patched parse_search_tools (suppressed spam).")
    return True


def main():
    sys.exit(0 if patch_proxy_server() else 1)


if __name__ == "__main__":
    main()
