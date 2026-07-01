"""Container lifecycle for one workspace.

Owns the docker run/stop/restart logic. Reads the manifest, builds the
``-v`` flags and labels, picks free ports, and persists back the ports
and timestamps. Reconcile (compare manifest vs running container) lives
in :mod:`codebase_memory.reconcile`; this module executes the result.

Design notes
------------

- The container runs as **root**. The codebase-memory container
  bind-mounts the user's host source code at ``/workspace/<id>`` (ro) and
  a per-project cache directory at ``/cache`` (rw). Running as root
  avoids permission issues with host UIDs and per-file modes. See the
  comment in ``docker/codebase-memory/Dockerfile.Codebase-memory``.

- Ports are allocated by trying to bind ``127.0.0.1:<port>`` locally.
  First free pair wins. The pair is persisted in the manifest.

- The container's effective state is encoded in labels
  (``com.codefreedom.cbm.*``). Reconcile compares the manifest hash
  label to a fresh hash of the current manifest; mismatch triggers a
  restart.
"""
from __future__ import annotations

import contextlib
import enum
import hashlib
import json
import logging
import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

from codebase_memory import browser as _browser
from codebase_memory import manifest as _manifest
from codebase_memory import project_id, related


_log = logging.getLogger(__name__)


# ── Defaults & labels ─────────────────────────────────────────────────────

IMAGE_DEFAULT = "docker.io/nilayparikh/codefreedom:codebase-memory-v1.0.0"
MCP_PORT_DEFAULT = 8330
UI_PORT_DEFAULT = 9749
MCP_PORT_RANGE = 50
LABEL_PREFIX = "com.codefreedom.cbm"
HASH_FIELDS = (
    "id",
    "image",
    "memory_mb",
    "shm_size_mb",
    "env",
    "related_paths",
    "remote_url",
    "mcp_port",
    "ui_port",
)


class StartStatus(enum.Enum):
    """Result of a ``start`` / ``ensure_running`` call."""

    CREATED = "created"
    RESTARTED = "restarted"
    ALREADY_RUNNING = "already_running"
    FAILED = "failed"


# ── Public API ────────────────────────────────────────────────────────────


def ensure_running(project_root: Path) -> tuple[StartStatus, dict[str, Any]]:
    """Reconcile + start/restart as needed. Returns ``(status, manifest)``.

    The caller (CLI or agent integration) is responsible for surfacing
    the status to the user and for writing the MCP URL into the agent
    config on ``CREATED`` / ``RESTARTED`` / ``ALREADY_RUNNING``.
    """
    data = _manifest.load(project_root)
    if not data.get("auto_start", True):
        return StartStatus.ALREADY_RUNNING, data

    if str(data.get("remote_url", "") or ""):
        # Remote mode: no local container, no ports.
        _manifest.update_last_used(project_root)
        return StartStatus.ALREADY_RUNNING, data

    _ensure_ports(project_root, data)
    if not container_exists(data["container_name"]):
        return _create(project_root, data), _manifest.load(project_root)

    desired_hash = manifest_hash(data)
    actual_hash = container_label(data["container_name"], "manifest-hash")
    if actual_hash != desired_hash:
        return _restart(project_root, data), _manifest.load(project_root)

    if not _is_container_running(data["container_name"]):
        _docker_start(data["container_name"])
        _manifest.update_last_used(project_root)
        return StartStatus.RESTARTED, _manifest.load(project_root)

    _manifest.update_last_used(project_root)
    return StartStatus.ALREADY_RUNNING, data


def stop(project_root: Path) -> bool:
    """Stop the project's container. Returns True if it was running."""
    data = _manifest.load(project_root)
    name = data.get("container_name")
    if not name or not container_exists(name):
        return False
    if not _is_container_running(name):
        return False
    _docker_stop(name)
    return True


def reset(
    project_root: Path,
    *,
    keep_manifest: bool = False,
    keep_cache: bool = False,
) -> None:
    """Stop container, optionally drop manifest, optionally drop cache."""
    data = _manifest.load(project_root)
    name = data.get("container_name")
    if name and container_exists(name):
        if _is_container_running(name):
            _docker_stop(name)
        _docker_rm(name)

    if not keep_cache:
        cache_dir = _cache_dir(data)
        if cache_dir.is_dir():
            _rm_tree(cache_dir)

    if not keep_manifest:
        manifest_path = _manifest.manifest_path(project_root)
        if manifest_path.is_file():
            manifest_path.unlink()


# ── Manifest hash & label encoding ───────────────────────────────────────


def manifest_hash(data: dict[str, Any]) -> str:
    """Stable SHA-256 of the effective fields used for reconcile."""
    payload = {k: data.get(k) for k in HASH_FIELDS}
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def build_labels(data: dict[str, Any]) -> dict[str, str]:
    """Build docker ``--label`` flags for a project container."""
    related_paths = data.get("related_paths", []) or []
    related_hosts = ",".join(str(r.get("path", "")) for r in related_paths)
    return {
        f"{LABEL_PREFIX}.managed-by": "codefreedom",
        f"{LABEL_PREFIX}.id": str(data.get("id", "")),
        f"{LABEL_PREFIX}.manifest-hash": manifest_hash(data),
        f"{LABEL_PREFIX}.related-paths": related_hosts,
        f"{LABEL_PREFIX}.memory-mb": str(data.get("memory_mb", 1024)),
        f"{LABEL_PREFIX}.auto-open-ui": str(bool(data.get("auto_open_ui", True))).lower(),
    }


# ── Internal: port allocation ─────────────────────────────────────────────


def _ensure_ports(project_root: Path, data: dict[str, Any]) -> None:
    """Persist first free pair starting from the YAML values (or defaults)."""
    desired_mcp = int(data.get("mcp_port") or MCP_PORT_DEFAULT)
    desired_ui = int(data.get("ui_port") or _ui_pair_for(desired_mcp))
    if _is_free("127.0.0.1", desired_mcp) and _is_free("127.0.0.1", desired_ui):
        data["mcp_port"] = desired_mcp
        data["ui_port"] = desired_ui
        return

    for offset in range(MCP_PORT_RANGE):
        mcp = MCP_PORT_DEFAULT + offset
        ui = _ui_pair_for(mcp)
        if _is_free("127.0.0.1", mcp) and _is_free("127.0.0.1", ui):
            data["mcp_port"] = mcp
            data["ui_port"] = ui
            _manifest.save(project_root, {"mcp_port": mcp, "ui_port": ui})
            return

    raise RuntimeError(
        f"No free MCP port pair available in range {MCP_PORT_DEFAULT}-{MCP_PORT_DEFAULT + MCP_PORT_RANGE - 1}. "
        "Stop some workspace containers and try again."
    )


def _ui_pair_for(mcp_port: int) -> int:
    """UI port = MCP port + (UI_PORT_DEFAULT - MCP_PORT_DEFAULT)."""
    return mcp_port + (UI_PORT_DEFAULT - MCP_PORT_DEFAULT)


def _is_free(host: str, port: int) -> bool:
    """True if ``host:port`` is not currently bound."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
        return True
    except OSError:
        return False


# ── Internal: create / restart ────────────────────────────────────────────


def _create(project_root: Path, data: dict[str, Any]) -> StartStatus:
    args = _build_run_args(data)
    result = _docker_run(args, data["image"])
    if result.returncode != 0:
        return StartStatus.FAILED
    _after_start(project_root, data)
    return StartStatus.CREATED


def _restart(project_root: Path, data: dict[str, Any]) -> StartStatus:
    name = data["container_name"]
    _docker_stop(name)
    _docker_rm(name)
    args = _build_run_args(data)
    result = _docker_run(args, data["image"])
    if result.returncode != 0:
        return StartStatus.FAILED
    _after_start(project_root, data)
    return StartStatus.RESTARTED


def _after_start(project_root: Path, data: dict[str, Any]) -> None:
    _manifest.update_last_used(project_root)
    _auto_index_workspace(data, _workspace_paths(data))
    if data.get("auto_open_ui", True):
        url = f"http://127.0.0.1:{data['ui_port']}/"
        if _browser.open_ui(url):
            _log.info("UI auto-opened: %s", url)
        else:
            _log.info("UI URL (could not auto-open): %s", url)


def _workspace_paths(data: dict[str, Any]) -> list[str]:
    main_root = Path(data["path"]).resolve()
    paths = [f"/workspace/{data['id']}"]
    related_paths = data.get("related_paths") or []
    if related_paths:
        for _, sub in related.container_subpaths(main_root, related_paths):
            paths.append(sub)
    return paths


def _auto_index_workspace(data: dict[str, Any], repo_paths: list[str]) -> None:
    if not repo_paths:
        return
    mcp_port = int(data.get("mcp_port") or MCP_PORT_DEFAULT)
    _wait_for_health(mcp_port)
    for repo_path in repo_paths:
        _mcp_call(mcp_port, "index_repository", {"repo_path": repo_path})


def _wait_for_health(mcp_port: int, timeout_s: float = 30.0) -> None:
    deadline = time.time() + timeout_s
    url = f"http://127.0.0.1:{mcp_port}/healthz"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"codebase-memory health check timed out on port {mcp_port}")


def _mcp_call(mcp_port: int, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    url = f"http://127.0.0.1:{mcp_port}/mcp"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _build_run_args(data: dict[str, Any]) -> list[str]:
    name = data["container_name"]
    image = data.get("image") or IMAGE_DEFAULT
    mcp_port = int(data["mcp_port"])
    ui_port = int(data["ui_port"])
    memory_mb = int(data.get("memory_mb", 1024))
    shm_mb = int(data.get("shm_size_mb", 512))
    bind_host = data.get("bind_host", "127.0.0.1")

    cache_dir = _cache_dir(data)
    cache_dir.mkdir(parents=True, exist_ok=True)

    args: list[str] = [
        "--name", name,
        "--restart", data.get("restart_policy", "unless-stopped"),
        "--shm-size", f"{shm_mb}m",
        "-m", f"{memory_mb}m",
        "--memory-swap", f"{memory_mb}m",
        "-p", f"{bind_host}:{mcp_port}:8330",
        "-p", f"{bind_host}:{ui_port}:9749",
        "-v", f"{cache_dir}:/cache",
        "-e", "CBM_CACHE_DIR=/cache",
        "-e", "CBM_LOG_LEVEL=info",
        "-e", "ENABLE_UI=1",
        "-e", "CBM_AUTO_INDEX=true",
    ]
    for k, v in (data.get("env") or {}).items():
        args.extend(["-e", f"{k}={v}"])

    # Main project mount
    main_root = Path(data["path"]).resolve()
    main_sub = f"/workspace/{data['id']}"
    args.extend(["-v", f"{main_root}:{main_sub}:ro"])

    # Related paths
    related_paths = data.get("related_paths") or []
    if related_paths:
        subpaths = related.container_subpaths(main_root, related_paths)
        for host, sub in subpaths:
            args.extend(["-v", f"{host}:{sub}:ro"])

    # Labels
    for k, v in build_labels(data).items():
        args.extend(["--label", f"{k}={v}"])

    # Healthcheck
    args.extend(
        [
            "--health-cmd",
            "python3 -c \"import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8330/healthz', timeout=2).status==200 else 1)\"",
            "--health-interval", "30s",
            "--health-timeout", "5s",
            "--health-retries", "3",
            "--health-start-period", "15s",
        ]
    )

    args.extend(["-d", image])
    return args


def _cache_dir(data: dict[str, Any]) -> Path:
    """Resolve the per-project cache directory (host side)."""
    return _home() / ".codefreedom" / "cache" / "codebase-memory" / str(data["id"])


def _home() -> Path:
    return Path(os.environ.get("HOME") or str(Path.home()))


def _rm_tree(directory: Path) -> None:
    """Recursively remove a directory. Python 3.12 has shutil.rmtree(safe_rm)."""
    import shutil
    with contextlib.suppress(FileNotFoundError):
        shutil.rmtree(directory)


# ── Internal: docker wrappers ─────────────────────────────────────────────


def _docker_run(args: list[str], image: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "run", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _docker_stop(name: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "stop", name],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _docker_rm(name: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "rm", name],
        check=False,
        capture_output=True,
        text=True,
    )


def _docker_start(name: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "start", name],
        check=False,
        capture_output=True,
        text=True,
    )


def container_exists(name: str) -> bool:
    result = subprocess.run(
        ["docker", "ps", "-aq", "--filter", f"name=^{name}$"],
        check=False,
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def _is_container_running(name: str) -> bool:
    result = subprocess.run(
        ["docker", "ps", "-q", "--filter", f"name=^{name}$"],
        check=False,
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def container_label(name: str, key: str) -> str:
    """Return the value of docker label ``<LABEL_PREFIX>.<key>`` or empty string."""
    full_key = f"{LABEL_PREFIX}.{key}"
    result = subprocess.run(
        ["docker", "inspect", "--format", f"{{{{ index .Config.Labels \"{full_key}\" }}}}", name],
        check=False,
        capture_output=True,
        text=True,
    )
    return (result.stdout or "").strip()


def populate_manifest_for_init(project_root: Path) -> dict[str, Any]:
    """Initialize the manifest if missing and return its current state.

    Sets ``id`` (from basename), ``container_name``, and ``path``. The
    rest of the fields (ports, timestamps) are filled in lazily.
    """
    data = _manifest.load(project_root)
    data["path"] = str(project_root.resolve())
    data["container_name"] = project_id.container_name_for(data["id"])
    _manifest.save(project_root, data)
    return _manifest.load(project_root)
