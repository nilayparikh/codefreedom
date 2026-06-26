"""URL helpers — single source of truth for endpoint/proxy URL construction.

Replaces ad-hoc ``f"http://127.0.0.1:{port}{path}"`` strings scattered
across :mod:`codefreedom.cli.mimo` / :mod:`codefreedom.cli.opencode` /
:mod:`codefreedom.cli.codex` / :mod:`codefreedom.tools.registry` and the
``http://localhost:{port}`` form used by :mod:`codefreedom.cli.run.proxy`.

Centralising these removes the ``127.0.0.1`` vs ``localhost`` inconsistency
and lets the MCP bind host become configurable without re-touching every
caller (future: support remote MCP servers / tunnel SSH forwards).
"""

from __future__ import annotations

_MCP_BIND_HOST = "127.0.0.1"


def build_endpoint_url(port: int | str, path: str = "/", host: str = _MCP_BIND_HOST) -> str:
    """Build an HTTP endpoint URL for an MCP/tool server.

    ``path`` is normalised to always start with ``/`` (LAN-style relative
    references are accepted either way). Host defaults to ``127.0.0.1`` —
    the canonical loopback used by all CodeFreedom tool containers when
    started from the host's CLI.
    """
    if not path:
        path = "/"
    elif not path.startswith("/"):
        path = "/" + path
    return f"http://{host}:{port}{path}"


def build_proxy_url(host: str, port: int | str) -> str:
    """Build the LiteLLM proxy base URL.

    Mirrors :meth:`ProxySettings.public_base_url` from
    :mod:`codefreedom.config.runtime` — host and port come from the resolved
    config (so ``override.yaml`` ``proxy.bind_host`` is honoured) rather than
    being re-derived with literal ``localhost`` / ``4000``.
    """
    return f"http://{host}:{port}"