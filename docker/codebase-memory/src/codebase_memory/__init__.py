"""codebase-memory — per-workspace host-side manager.

One container instance per git project, resolved from the user's CWD via
``git rev-parse --show-toplevel``. The manifest is a user-editable YAML
file at ``<project_root>/.codefreedom/codebase-memory.yaml``. There is no
central registry — every workspace is fully self-describing.

Public surface
--------------

The CLI entry point is :func:`codebase_memory.cli.run`, which dispatches
the eight subcommands (``init``, ``start``, ``stop``, ``restart``,
``status``, ``reset``, ``logs``, ``compact``). Programmatic users should
go through :mod:`codebase_memory.manager` directly.
"""
from __future__ import annotations

__all__ = [
    "browser",
    "cli",
    "compact",
    "git_root",
    "manager",
    "manifest",
    "project_id",
    "reconcile",
    "related",
]
