"""Bridge from codefreedom's tool registry to the per-workspace cbmem package.

The host-side Python that manages codebase-memory's container lifecycle
lives in :mod:`codebase_memory` at ``docker/codebase-memory/src/`` — a
self-contained package that the user can read, modify, or extract
without touching the rest of codefreedom. This module is the glue:

- Adds that directory to ``sys.path`` so ``import codebase_memory``
  resolves to it.
- Re-exports the symbols that codefreedom's tool registry and MCP
  endpoint resolver expect (``_load_profile``, ``start``, ``stop``,
  ``CodebaseMemoryTool``).
- Delegates ``start`` and ``stop`` to the new package, which resolves
  the project from ``Path.cwd()`` via ``git rev-parse``. The
  ``settings`` argument is accepted for back-compat with the tool
  registry's signature but is otherwise ignored — the manifest is the
  source of truth.

There is no fallback to a static container name or a workspace_dir
profile key. If the CWD is not inside a git repository, the commands
fail with a clear message.
"""
from __future__ import annotations

import sys
from pathlib import Path


# ── Path setup (must come before any import of `codebase_memory`) ─────────

_REPO_ROOT = Path(__file__).resolve().parents[3]  # src/codefreedom/tools/_cbmem_loader.py -> repo root
_CBMEM_SRC = _REPO_ROOT / "docker" / "codebase-memory" / "src"
if str(_CBMEM_SRC) not in sys.path:
    sys.path.insert(0, str(_CBMEM_SRC))


# ── Re-exports from the self-contained package ────────────────────────────

from codebase_memory import (  # noqa: E402,F401  (re-exported for back-compat)
    browser,
    compact,
    git_root,
    manager,
    manifest,
    reconcile,
    related,
)
from codebase_memory.manager import (  # noqa: E402,F401
    StartStatus,
)


# ── Back-compat surface ──────────────────────────────────────────────────


_DEFAULT_IMAGE = "docker.io/nilayparikh/codefreedom:codebase-memory-v1.0.0"
_DEFAULT_PORT = 8330
_DEFAULT_UI_PORT = 9749


def _resolve_project_root() -> Path:
    """Resolve the current project's git root, raising a clear error.

    Returns the project root. Raises :class:`git_root.NotInGitRepo` so
    callers can decide whether to log-and-skip or print-and-exit. The
    CLI handler prints and exits; the tool-registry integration
    (``start``/``stop``) catches the error and returns a non-zero exit
    code so the tool is simply skipped.
    """
    return git_root.find_project_root(Path.cwd())


def _find_manifest_root(cwd: Path | None = None) -> Path | None:
    """Walk up from ``cwd`` looking for a ``.codefreedom/codebase-memory.yaml``.

    This is a fallback for when :func:`_resolve_project_root` fails (e.g.
    a repo with ``core.bare=true``). It bypasses git entirely and looks
    for the manifest file directly. Returns the directory containing the
    manifest, or None if not found within 3 levels.
    """
    start = (cwd or Path.cwd()).resolve()
    for level in range(4):
        candidate = start
        for _ in range(level):
            parent = candidate.parent
            if parent == candidate:
                return None
            candidate = parent
        if (candidate / ".codefreedom" / "codebase-memory.yaml").is_file():
            return candidate
    return None


def _load_profile() -> dict:
    """Return the current project's manifest, falling back to defaults.

    Kept for back-compat with codefreedom's tool registry, which calls
    this function with no arguments. The returned dict has the same
    shape as a manifest — keys like ``port``, ``ui_port``,
    ``container_name`` are populated from the YAML if a manifest exists.

    When the CWD is not inside a git repo, the function still returns
    a valid default dict so the tool registry has a coherent view of
    the tool (e.g. for the agent's MCP config writer). The actual
    ``start``/``stop`` calls will fail with a clear error.
    """
    project_root: Path | None = None
    try:
        project_root = _resolve_project_root()
    except git_root.NotInGitRepo:
        project_root = _find_manifest_root()

    if project_root is None:
        return {
            "image": _DEFAULT_IMAGE,
            "container_name": "codefreedom-tools-codebase-memory-default",
            "port": _DEFAULT_PORT,
            "ui_port": _DEFAULT_UI_PORT,
            "data_dir": str(Path.home() / ".codefreedom" / "cache" / "codebase-memory" / "default"),
            "workspace_dir": "",
            "bind_host": "127.0.0.1",
            "remote_url": "",
            "enable_ui": True,
            "log_level": "info",
            "auto_index": False,
            "env": {},
        }

    if not manifest.exists(project_root):
        manager.populate_manifest_for_init(project_root)

    data = manifest.load(project_root)
    data.setdefault("image", _DEFAULT_IMAGE)
    data.setdefault("port", _DEFAULT_PORT)
    data.setdefault("ui_port", _DEFAULT_UI_PORT)
    data.setdefault("bind_host", "127.0.0.1")
    data.setdefault("remote_url", "")
    data.setdefault("env", {})
    return data


def start(_settings: dict | None = None) -> int:
    """Auto-start the current project's container.

    The ``settings`` argument is accepted for back-compat with the tool
    registry's signature; it is ignored. The project is resolved from
    ``Path.cwd()`` via ``git rev-parse``. Returns a non-zero exit code
    (and prints to stderr) when the CWD is not a git repo or the
    container cannot be started — callers in the tool registry treat
    that as "skip this tool".
    """
    project_root: Path | None = None
    try:
        project_root = _resolve_project_root()
    except git_root.NotInGitRepo:
        project_root = _find_manifest_root()

    if project_root is None:
        print("[CODEBASE-MEMORY] Not inside a git repository and no manifest found.", file=sys.stderr)
        return 1

    if not manifest.exists(project_root):
        manager.populate_manifest_for_init(project_root)
    try:
        status, data = manager.ensure_running(project_root)
    except RuntimeError as exc:
        print(f"[CODEBASE-MEMORY] {exc}", file=sys.stderr)
        return 1
    if status == StartStatus.FAILED:
        print("[CODEBASE-MEMORY] Failed to start container. Run 'cf r tl cbmem logs'.", file=sys.stderr)
        return 1
    return 0


def stop(_settings: dict | None = None) -> int:
    """Stop the current project's container. Returns 0 even if nothing to stop."""
    project_root: Path | None = None
    try:
        project_root = _resolve_project_root()
    except git_root.NotInGitRepo:
        project_root = _find_manifest_root()

    if project_root is None or not manifest.exists(project_root):
        return 0
    manager.stop(project_root)
    return 0


def status(_settings: dict | None = None) -> int:
    """Show status for the current project (delegates to the CLI handler)."""
    from codebase_memory import cli as _cli
    args = type("A", (), {"cbmem_action": "status", "follow": False, "keep_manifest": False, "keep_cache": False, "artifact": False})()
    return _cli.run(args)


# ── MCP endpoint class used by tool registry / agent config ──────────────


class CodebaseMemoryTool:
    """MCP endpoint descriptor for the codebase-memory tool.

    ``mcp_endpoint`` reads the current project's manifest (or returns
    defaults if no manifest exists yet) and returns
    ``(port, '/mcp')``. ``mcp_server_name`` is the registry key.
    """

    @property
    def mcp_server_name(self) -> str:
        return "codebase-memory"

    @property
    def mcp_endpoint(self) -> tuple[int, str]:
        project_root: Path | None = None
        try:
            project_root = _resolve_project_root()
        except git_root.NotInGitRepo:
            project_root = _find_manifest_root()

        if project_root is None or not manifest.exists(project_root):
            return _DEFAULT_PORT, "/mcp"

        data = manifest.load(project_root)
        if str(data.get("remote_url", "") or ""):
            return _DEFAULT_PORT, "/mcp"
        return int(data.get("mcp_port") or _DEFAULT_PORT), "/mcp"
