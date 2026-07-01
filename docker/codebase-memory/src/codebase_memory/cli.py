"""``cf r tl cbmem <verb>`` — the eight subcommands.

All commands operate on the *current* project (resolved from CWD via
``git rev-parse``). There is no central registry, no filesystem scan,
no ``list`` command. The user navigates to a project to manage it.

Verb map
--------

- ``init``    — create the manifest if missing
- ``start``   — reconcile + start/restart the container
- ``stop``    — stop the container
- ``restart`` — stop + start
- ``status``  — show container, ports, memory, cache, related
- ``reset``   — stop, optionally drop manifest and/or cache
- ``logs``    — ``docker logs -f <container>``
- ``compact`` — VACUUM the cache, optionally write team-shared artifact

Each command is a small function that takes the resolved ``project_root``
and a parsed-args ``Namespace``. ``run`` is the single entry point
``codefreedom``'s tool dispatcher calls.
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

from codebase_memory import compact as _compact
from codebase_memory import git_root, manager, manifest, reconcile


_log = logging.getLogger(__name__)


_VERBS = ("init", "start", "stop", "restart", "status", "reset", "logs", "compact")


# ── Entry point ───────────────────────────────────────────────────────────


def run(args: argparse.Namespace) -> int:
    """Dispatch a ``cf r tl cbmem <verb>`` invocation."""
    verb = getattr(args, "cbmem_action", None) or "status"
    try:
        project_root = git_root.find_project_root(Path.cwd())
    except git_root.NotInGitRepo as exc:
        print(f"[CODEBASE-MEMORY] {exc}", file=sys.stderr)
        return 1

    handler_name = f"_cmd_{verb}"
    handler = globals().get(handler_name)
    if handler is None:
        print(f"[CODEBASE-MEMORY] Unknown verb: {verb}. Try one of: {', '.join(_VERBS)}", file=sys.stderr)
        return 2

    try:
        return handler(project_root, args)
    except git_root.NotInGitRepo as exc:
        print(f"[CODEBASE-MEMORY] {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — last-resort guard
        _log.debug("cbmem %s failed", verb, exc_info=True)
        print(f"[CODEBASE-MEMORY] {verb} failed: {exc}", file=sys.stderr)
        return 1


# ── Handlers ──────────────────────────────────────────────────────────────


def _cmd_init(project_root: Path, args: argparse.Namespace) -> int:
    if manifest.exists(project_root):
        data = manifest.load(project_root)
        print(f"[CODEBASE-MEMORY] Already initialized at {manifest.manifest_path(project_root)}", file=sys.stderr)
        print(f"[CODEBASE-MEMORY] id={data.get('id')}", file=sys.stderr)
        return 0
    data = manager.populate_manifest_for_init(project_root)
    print(f"[CODEBASE-MEMORY] Initialized {manifest.manifest_path(project_root)}", file=sys.stderr)
    print(f"[CODEBASE-MEMORY] id={data.get('id')}", file=sys.stderr)
    return 0


def _cmd_start(project_root: Path, args: argparse.Namespace) -> int:
    if not manifest.exists(project_root):
        manager.populate_manifest_for_init(project_root)
    status, data = manager.ensure_running(project_root)
    if status == manager.StartStatus.FAILED:
        print("[CODEBASE-MEMORY] Failed to start container. Run 'cf r tl cbmem logs' to inspect.", file=sys.stderr)
        return 1
    if str(data.get("remote_url", "") or ""):
        print(f"[CODEBASE-MEMORY] remote_url set; using {data['remote_url']}", file=sys.stderr)
        return 0
    print(f"[CODEBASE-MEMORY] {status.value}: {data['container_name']}", file=sys.stderr)
    print(f"[CODEBASE-MEMORY] MCP: http://127.0.0.1:{data['mcp_port']}/mcp", file=sys.stderr)
    print(f"[CODEBASE-MEMORY] UI:  http://127.0.0.1:{data['ui_port']}/", file=sys.stderr)
    return 0


def _cmd_stop(project_root: Path, args: argparse.Namespace) -> int:
    if not manifest.exists(project_root):
        print("[CODEBASE-MEMORY] No manifest; nothing to stop.", file=sys.stderr)
        return 0
    if manager.stop(project_root):
        print("[CODEBASE-MEMORY] Stopped.", file=sys.stderr)
    else:
        print("[CODEBASE-MEMORY] Container was not running.", file=sys.stderr)
    return 0


def _cmd_restart(project_root: Path, args: argparse.Namespace) -> int:
    if not manifest.exists(project_root):
        manager.populate_manifest_for_init(project_root)
    _cmd_stop(project_root, args)
    return _cmd_start(project_root, args)


def _cmd_status(project_root: Path, args: argparse.Namespace) -> int:
    if not manifest.exists(project_root):
        print(f"[CODEBASE-MEMORY] No manifest at {manifest.manifest_path(project_root)}.", file=sys.stderr)
        print("[CODEBASE-MEMORY] Run 'cf r tl cbmem init' to initialize.", file=sys.stderr)
        return 0
    data = manifest.load(project_root)
    decision = reconcile.decide(data)
    _print_status(project_root, data, decision)
    return 0


def _cmd_reset(project_root: Path, args: argparse.Namespace) -> int:
    if not manifest.exists(project_root):
        print("[CODEBASE-MEMORY] No manifest; nothing to reset.", file=sys.stderr)
        return 0
    keep_manifest = bool(getattr(args, "keep_manifest", False))
    keep_cache = bool(getattr(args, "keep_cache", False))
    manager.reset(project_root, keep_manifest=keep_manifest, keep_cache=keep_cache)
    print("[CODEBASE-MEMORY] Reset complete.", file=sys.stderr)
    if not keep_manifest:
        print(f"[CODEBASE-MEMORY] Manifest removed: {manifest.manifest_path(project_root)}", file=sys.stderr)
    if not keep_cache:
        print("[CODEBASE-MEMORY] Cache removed.", file=sys.stderr)
    return 0


def _cmd_logs(project_root: Path, args: argparse.Namespace) -> int:
    if not manifest.exists(project_root):
        print("[CODEBASE-MEMORY] No manifest.", file=sys.stderr)
        return 1
    data = manifest.load(project_root)
    name = data.get("container_name")
    if not name or not manager.container_exists(name):
        print(f"[CODEBASE-MEMORY] Container '{name}' does not exist.", file=sys.stderr)
        return 1
    cmd = ["docker", "logs"]
    if bool(getattr(args, "follow", False)):
        cmd.append("-f")
    cmd.append(str(name))
    return subprocess.call(cmd)


def _cmd_compact(project_root: Path, args: argparse.Namespace) -> int:
    if not manifest.exists(project_root):
        print("[CODEBASE-MEMORY] No manifest.", file=sys.stderr)
        return 1
    write_artifact = bool(getattr(args, "artifact", False))
    summary = _compact.compact(project_root, write_artifact=write_artifact)
    print(f"[CODEBASE-MEMORY] Cache: {summary.cache_dir}", file=sys.stderr)
    if summary.container_was_running:
        print("[CODEBASE-MEMORY] Stopped container for VACUUM. Run 'cf r tl cbmem start' to bring it back.", file=sys.stderr)
    for r in summary.results:
        if r.ok:
            delta = r.before_bytes - r.after_bytes
            pct = (100 * delta / r.before_bytes) if r.before_bytes else 0
            print(
                f"[CODEBASE-MEMORY]   {r.db_path.name}: "
                f"{_fmt_bytes(r.before_bytes)} -> {_fmt_bytes(r.after_bytes)} "
                f"(-{_fmt_bytes(delta)}, -{pct:.0f}%)",
                file=sys.stderr,
            )
        else:
            print(f"[CODEBASE-MEMORY]   {r.db_path.name}: FAILED ({r.error})", file=sys.stderr)
    if summary.artifact_path and summary.artifact_path.is_file():
        print(
            f"[CODEBASE-MEMORY] Artifact: {summary.artifact_path} ({_fmt_bytes(summary.artifact_bytes)})",
            file=sys.stderr,
        )
    elif write_artifact:
        print("[CODEBASE-MEMORY] Artifact: not written (no DBs in cache, or zstd/sqlite3 missing).", file=sys.stderr)
    return 0


_HANDLERS_DISPATCH = {
    "init": "_cmd_init",
    "start": "_cmd_start",
    "stop": "_cmd_stop",
    "restart": "_cmd_restart",
    "status": "_cmd_status",
    "reset": "_cmd_reset",
    "logs": "_cmd_logs",
    "compact": "_cmd_compact",
}


# ── Status rendering ─────────────────────────────────────────────────────


def _print_status(project_root: Path, data: dict, decision: reconcile.ReconcileDecision) -> None:
    print(f"[CODEBASE-MEMORY] project:     {data.get('id', '?')}", file=sys.stderr)
    print(f"[CODEBASE-MEMORY] path:        {project_root}", file=sys.stderr)
    if str(data.get("remote_url", "") or ""):
        print(f"[CODEBASE-MEMORY] remote_url:  {data['remote_url']}", file=sys.stderr)
        return
    print(f"[CODEBASE-MEMORY] container:   {data.get('container_name', '?')} ({_state_label(decision.action)})", file=sys.stderr)
    print(f"[CODEBASE-MEMORY] decision:    {decision.action.value}  ({decision.reason})", file=sys.stderr)
    print(f"[CODEBASE-MEMORY] MCP:         http://127.0.0.1:{data.get('mcp_port', '?')}/mcp", file=sys.stderr)
    ui = data.get("ui_port")
    if ui:
        print(f"[CODEBASE-MEMORY] UI:          http://127.0.0.1:{ui}/  (auto-open: {'enabled' if data.get('auto_open_ui', True) else 'disabled'})", file=sys.stderr)
    print(f"[CODEBASE-MEMORY] memory:      {data.get('memory_mb', 1024)} MB limit", file=sys.stderr)
    cache_dir = manager._cache_dir(data)
    if cache_dir.is_dir():
        size = _dir_size(cache_dir)
        print(f"[CODEBASE-MEMORY] cache:       {_fmt_bytes(size)} in {cache_dir}", file=sys.stderr)
    else:
        print("[CODEBASE-MEMORY] cache:       <not yet created>", file=sys.stderr)
    related_paths = data.get("related_paths") or []
    print(f"[CODEBASE-MEMORY] related:     {len(related_paths)} path(s)", file=sys.stderr)
    print("[CODEBASE-MEMORY] hybrid LSP:  on (9 languages, 149 fallback — upstream)", file=sys.stderr)
    print("[CODEBASE-MEMORY] auto-index:  on (upstream CBM_AUTO_INDEX=true)", file=sys.stderr)


def _state_label(action: reconcile.ReconcileAction) -> str:
    return {
        reconcile.ReconcileAction.REMOTE: "remote",
        reconcile.ReconcileAction.NEEDS_CREATE: "not created",
        reconcile.ReconcileAction.NEEDS_START: "stopped",
        reconcile.ReconcileAction.NEEDS_RESTART: "drifted (restart needed)",
        reconcile.ReconcileAction.NOOP: "running",
    }.get(action, "unknown")


def _dir_size(directory: Path) -> int:
    total = 0
    for p in directory.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total


def _fmt_bytes(n: int) -> str:
    sign = "-" if n < 0 else ""
    n = abs(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{sign}{n:.0f} {unit}" if unit == "B" else f"{sign}{n:.1f} {unit}"
        n = int(n / 1024)
    return f"{sign}{n:.1f} PB"


# ── argparse sub-parser (for codefreedom's main CLI) ──────────────────────


def add_subparser(subparsers) -> argparse.ArgumentParser:
    """Register the ``cbmem`` subcommand on the parent parser."""
    p = subparsers.add_parser(
        "codebase-memory",
        aliases=["cbmem"],
        help="Manage the Codebase Memory MCP tool for the current project",
    )
    p.add_argument(
        "cbmem_action",
        nargs="?",
        default="status",
        choices=_VERBS,
        help="Action to perform (default: status)",
    )
    p.add_argument("--keep-manifest", action="store_true", help="Used with 'reset'.")
    p.add_argument("--keep-cache", action="store_true", help="Used with 'reset'.")
    p.add_argument("-f", "--follow", action="store_true", help="Used with 'logs' (docker logs -f).")
    p.add_argument("--artifact", action="store_true", help="Used with 'compact' — also write .codebase-memory/graph.db.zst.")
    p.set_defaults(func=run)
    return p
