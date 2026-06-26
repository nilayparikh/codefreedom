"""Shared scaffolding for the four tool modules (chrome, web, github, web_bridge).

Each tool module exposes the same surface:

* ``_load_profile() -> dict``         — load settings from profiles.yaml
* ``_DEFAULT_PORT``                    — canonical default port for that tool
* ``start(settings) -> int``           — start the container
* ``stop(settings) -> int``            — stop the container
* ``restart(settings) -> int``        — restart the container
* ``status(settings) -> int``          — show container status
* ``url(settings) -> int`` (optional)  — print the MCP endpoint URL (chrome only)
* ``run(args) -> int``                 — CLI entry point

The ``run`` body was identical boilerplate in every tool module: load the
profile, override ``port`` when ``--port`` differs from the default, and
dispatch to ``run_tool_action``. ``dispatch_tool_run`` here folds that into
a single call so each tool module's ``run`` shrinks to a one-liner.

This module lives in ``core/`` so tool modules can import it without
reaching up into ``cli/`` (layering rule: tools → core, never tools → cli).
"""

from __future__ import annotations

import argparse
from typing import Callable, Optional

from codefreedom.cli.common import run_tool_action
from codefreedom.core.container import init_tool_redirect, load_tool_profile

__all__ = [
    "dispatch_tool_run",
    "init_tool_redirect",
    "load_tool_profile",
    "make_default_settings",
]


def make_default_settings(
    *,
    image: str,
    container_name: str,
    port: int,
    data_dir: str,
    extra: dict | None = None,
) -> dict:
    """Build the canonical default-settings dict for a tool module.

    All four tool modules start from the same shape:

    ``{image, container_name, port, data_dir, env}``

    …and optionally add tool-specific keys (``mcp_port``, ``mcp_path``,
    ``cdp_proxy_port``, ``search_engines``, …). ``extra`` lets a tool layer
    those extra defaults on top without each module re-typing the base.
    """
    settings: dict = {
        "image": image,
        "container_name": container_name,
        "port": port,
        "data_dir": data_dir,
        "env": {},
    }
    if extra:
        settings.update(extra)
    return settings


def dispatch_tool_run(  # pylint: disable=too-many-arguments
    args: argparse.Namespace,
    *,
    load_profile: Callable[[], dict],
    default_port: int,
    start: Callable[[dict], int],
    stop: Callable[[dict], int],
    restart: Callable[[dict], int],
    status: Callable[[dict], int],
    url: Optional[Callable[[dict], int]] = None,
) -> int:
    """Dispatch a tool CLI ``run(args)`` invocation.

    Wraps the load-profile → override-port → run_tool_action flow that
    was duplicated verbatim in chrome/web/github/web_bridge. The ``url``
    callable is optional (only chrome defines one).

    The ``--port`` CLI flag overrides ``settings["port"]`` only when it
    is explicitly provided *and* differs from the tool's canonical
    default — this avoids clobbering a profile-configured port when the
    CLI merely inherits the default.
    """
    settings = load_profile()

    cli_port = getattr(args, "port", None)
    if cli_port and cli_port != default_port:
        settings["port"] = cli_port

    action = args.action or "status"
    return run_tool_action(
        action,
        start_fn=lambda: start(settings),
        stop_fn=lambda: stop(settings),
        restart_fn=lambda: restart(settings),
        status_fn=lambda: status(settings),
        url_fn=(lambda: url(settings)) if url is not None else None,
    )
