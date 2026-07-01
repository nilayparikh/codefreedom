"""Reconcile: compare current manifest vs running container.

Decides whether a ``start`` call needs to create a new container, restart
the existing one, or do nothing. Logic is split out of
:mod:`codebase_memory.manager` so it can be unit-tested without invoking
``docker``.

The decision tree:

1. ``remote_url`` set → no local container, no work to do
   (``REMOTE``).
2. Container missing → needs creation (``NEEDS_CREATE``).
3. Container present, manifest hash matches, running → no-op
   (``NOOP``).
4. Container present, manifest hash matches, stopped → start it
   (``NEEDS_START``).
5. Container present, manifest hash differs → restart
   (``NEEDS_RESTART``).

Used by ``manager.ensure_running`` and by ``cli.status`` to render a
clear summary.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

from codebase_memory import manager


class ReconcileAction(enum.Enum):
    REMOTE = "remote"
    NEEDS_CREATE = "needs_create"
    NEEDS_START = "needs_start"
    NEEDS_RESTART = "needs_restart"
    NOOP = "noop"


@dataclass
class ReconcileDecision:
    action: ReconcileAction
    reason: str
    container_name: str | None
    desired_hash: str
    actual_hash: str | None


def decide(data: dict[str, Any]) -> ReconcileDecision:
    """Return a structured reconcile decision for ``data`` (the manifest)."""
    name = str(data.get("container_name", "") or "")
    if str(data.get("remote_url", "") or ""):
        return ReconcileDecision(
            action=ReconcileAction.REMOTE,
            reason="remote_url is set; using remote MCP endpoint",
            container_name=None,
            desired_hash=manager.manifest_hash(data),
            actual_hash=None,
        )

    if not name:
        return ReconcileDecision(
            action=ReconcileAction.NEEDS_CREATE,
            reason="no container_name in manifest",
            container_name=None,
            desired_hash=manager.manifest_hash(data),
            actual_hash=None,
        )

    desired_hash = manager.manifest_hash(data)
    if not manager.container_exists(name):
        return ReconcileDecision(
            action=ReconcileAction.NEEDS_CREATE,
            reason=f"container '{name}' does not exist",
            container_name=name,
            desired_hash=desired_hash,
            actual_hash=None,
        )

    actual_hash = manager.container_label(name, "manifest-hash")
    if actual_hash and actual_hash != desired_hash:
        return ReconcileDecision(
            action=ReconcileAction.NEEDS_RESTART,
            reason=f"manifest changed (hash {actual_hash[:8]} -> {desired_hash[:8]})",
            container_name=name,
            desired_hash=desired_hash,
            actual_hash=actual_hash,
        )

    if not _is_running(name):
        return ReconcileDecision(
            action=ReconcileAction.NEEDS_START,
            reason=f"container '{name}' exists but is stopped",
            container_name=name,
            desired_hash=desired_hash,
            actual_hash=actual_hash,
        )

    return ReconcileDecision(
        action=ReconcileAction.NOOP,
        reason="container running and manifest unchanged",
        container_name=name,
        desired_hash=desired_hash,
        actual_hash=actual_hash,
    )


def _is_running(name: str) -> bool:
    """Thin wrapper over ``manager._is_container_running`` for testability."""
    return manager._is_container_running(name)
