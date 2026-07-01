"""Tests for ``codebase_memory.reconcile`` — the decision logic that
tells the manager what to do with a manifest vs running container.
"""
from __future__ import annotations

from unittest.mock import patch

from codebase_memory import manager, reconcile


def _data(**overrides) -> dict:
    base = {
        "id": "proj",
        "container_name": "codefreedom-tools-codebase-memory-proj",
        "image": "x",
        "mcp_port": 8330,
        "ui_port": 9749,
        "memory_mb": 1024,
        "shm_size_mb": 512,
        "env": {},
        "related_paths": [],
    }
    base.update(overrides)
    return base


class TestDecide:

    def test_remote_url_is_remote(self):
        d = _data(remote_url="https://x/mcp")
        decision = reconcile.decide(d)
        assert decision.action == reconcile.ReconcileAction.REMOTE
        assert decision.container_name is None
        assert decision.actual_hash is None

    def test_no_container_name_needs_create(self):
        d = _data(container_name="")
        decision = reconcile.decide(d)
        assert decision.action == reconcile.ReconcileAction.NEEDS_CREATE

    def test_container_missing_needs_create(self):
        d = _data()
        with patch.object(manager, "container_exists", return_value=False):
            decision = reconcile.decide(d)
        assert decision.action == reconcile.ReconcileAction.NEEDS_CREATE
        assert decision.container_name == d["container_name"]
        assert decision.actual_hash is None

    def test_hash_differs_needs_restart(self):
        d = _data()
        with patch.object(manager, "container_exists", return_value=True), \
             patch.object(manager, "container_label", return_value="wronghash"):
            decision = reconcile.decide(d)
        assert decision.action == reconcile.ReconcileAction.NEEDS_RESTART
        assert decision.actual_hash == "wronghash"
        assert decision.desired_hash == manager.manifest_hash(d)

    def test_hash_matches_stopped_needs_start(self):
        d = _data()
        actual = manager.manifest_hash(d)
        with patch.object(manager, "container_exists", return_value=True), \
             patch.object(manager, "container_label", return_value=actual), \
             patch.object(reconcile, "_is_running", return_value=False):
            decision = reconcile.decide(d)
        assert decision.action == reconcile.ReconcileAction.NEEDS_START
        assert decision.actual_hash == actual

    def test_hash_matches_running_is_noop(self):
        d = _data()
        actual = manager.manifest_hash(d)
        with patch.object(manager, "container_exists", return_value=True), \
             patch.object(manager, "container_label", return_value=actual), \
             patch.object(reconcile, "_is_running", return_value=True):
            decision = reconcile.decide(d)
        assert decision.action == reconcile.ReconcileAction.NOOP

    def test_decision_always_has_desired_hash(self):
        d = _data()
        decision = reconcile.decide(d)
        assert decision.desired_hash == manager.manifest_hash(d)
        assert len(decision.desired_hash) == 16  # truncated SHA-256

    def test_decision_preserves_container_name(self):
        d = _data(container_name="codefreedom-tools-codebase-memory-x")
        with patch.object(manager, "container_exists", return_value=False):
            decision = reconcile.decide(d)
        assert decision.container_name == "codefreedom-tools-codebase-memory-x"
