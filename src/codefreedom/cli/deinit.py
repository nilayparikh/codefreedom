"""Deinit subcommand -- fully tear down CodeFreedom configuration and containers.

Usage:
    codefreedom deinit              Interactive teardown (prompts for confirmation)
    codefreedom deinit --force      Skip confirmation prompt
    codefreedom deinit --help       Show this help

Teardown steps:
  1. Stop the proxy (docker compose down)
  2. Stop all tools (chrome, web, github, web-bridge)
  3. Find and remove any remaining CodeFreedom Docker containers (sandbox
     sessions, orphaned containers, etc.)
  4. Prompt the user to confirm removal of the CodeFreedom home directory
     (``~/.codefreedom/`` or ``$CODEFREEDOM_HOME``)
  5. Remove the CodeFreedom home directory

Does NOT remove Docker images. Use ``docker image prune`` or
``docker rmi`` separately if you also want to reclaim image space.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import os
import sys
from pathlib import Path

from codefreedom.config import get_codefreedom_dir
from codefreedom.env_loader import eprint


def _find_codefreedom_containers() -> list[str]:
    """Find all Docker containers (running or stopped) owned by CodeFreedom.

    Uses :func:`codefreedom.cli.docker_utils.find_containers_by_base` for
    strict prefix matching (avoids false positives from containers whose
    name merely contains ``codefreedom-`` as a substring).

    Matches containers whose name starts with known CodeFreedom prefixes:
    - ``codefreedom-`` (sandbox sessions, legacy containers, tools)
    - ``litellm-codefreedom-`` (proxy containers)

    Returns container names sorted newest-first.
    """
    from codefreedom.cli.docker_utils import find_containers_by_base

    found: set[str] = set()
    for prefix in ["codefreedom", "litellm-codefreedom"]:
        found.update(find_containers_by_base(prefix))
    return sorted(found)


def _stop_and_remove_container(name: str) -> None:
    """Force-stop and remove a single Docker container."""
    try:
        subprocess.run(
            ["docker", "rm", "-f", name],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        pass


def _stop_proxy(cf_dir: Path) -> int:
    """Stop the CodeFreedom proxy via docker compose down, if compose file exists."""
    compose_file = cf_dir / "proxy" / "docker-compose.yaml"
    if not compose_file.exists():
        return 0

    eprint("[deinit] Stopping proxy...")
    # Load proxy env files to get SUFFIX_ID for COMPOSE_PROJECT_NAME
    # Start with os.environ so HOME and other system vars are available
    # to Docker Compose, preventing "${HOME} not set" warnings in the
    # compose file's Postgres volume fallback paths.
    compose_env: dict[str, str] = {}
    for env_path in [
        cf_dir / ".env.proxy",
        cf_dir / ".env.proxy.secrets",
        cf_dir / ".env.user",
    ]:
        if env_path.exists():
            try:
                from codefreedom.env_loader import load_dotenv

                compose_env.update(load_dotenv(env_path))
            except Exception:
                pass

    compose_env = {**os.environ, **compose_env}
    suffix = compose_env.get("SUFFIX_ID", "0000")
    compose_env["COMPOSE_PROJECT_NAME"] = f"codefreedom-{suffix}"

    # Inject PostgreSQL dirs from CODEFREEDOM_HOME to avoid ${HOME}
    # fallback in the docker-compose.yaml
    compose_env.setdefault("POSTGRES_HOST_DATA_DIR", str(cf_dir / "pg" / "data"))
    compose_env.setdefault("POSTGRES_HOST_BACKUP_DIR", str(cf_dir / "pg" / "backup"))

    try:
        result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "--profile",
                "litellm",
                "down",
            ],
            env=compose_env,
            capture_output=False,
            timeout=60,
            check=False,
        )
        if result.returncode == 0:
            eprint("   [OK] Proxy stopped.")
        else:
            eprint("   [WARN] Proxy may not have stopped cleanly.")
        return result.returncode
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        eprint(f"   [WARN] Could not stop proxy: {exc}")
        return 1


def _stop_tools() -> int:
    """Stop all CodeFreedom tool containers using the existing tools machinery."""
    try:
        from codefreedom.cli.tools import stop_all as tools_stop_all

        eprint("[deinit] Stopping all tools...")
        return tools_stop_all()
    except ImportError as exc:
        eprint(f"   [WARN] Could not import tools module: {exc}")
        return 1
    except Exception as exc:
        eprint(f"   [WARN] Failed to stop tools: {exc}")
        return 1


def _remove_codefreedom_dir(cf_dir: Path) -> None:
    """Remove the CodeFreedom home directory and all its contents.

    Preserves ``.env.user`` — it's a user-managed override file that should
    survive a full teardown. Prints a message telling the user where it is.
    """
    if not cf_dir.exists():
        eprint(f"[deinit] Directory '{cf_dir}' does not exist — nothing to remove.")
        return

    # Preserve .env.user — user-managed override, never auto-created by recipes
    user_env = cf_dir / ".env.user"
    preserved = None
    if user_env.exists():
        try:
            preserved = user_env.read_text()
        except OSError:
            pass

    eprint(f"[deinit] Removing '{cf_dir}' (preserving .env.user)...")
    try:
        shutil.rmtree(cf_dir)
        eprint("   [OK] Directory removed.")
    except OSError as exc:
        eprint(f"   [ERROR] Failed to remove directory: {exc}")
        sys.exit(1)

    # Restore .env.user
    if preserved is not None:
        try:
            cf_dir.mkdir(parents=True, exist_ok=True)
            user_env.write_text(preserved)
            eprint(f"   [OK] Preserved '{user_env}' (user overrides).")
        except OSError as exc:
            eprint(f"   [WARN] Could not restore .env.user: {exc}")


def run(args: argparse.Namespace) -> int:
    """Execute the deinit subcommand. Returns exit code."""
    force = getattr(args, "force", False)
    cf_dir = get_codefreedom_dir()

    eprint("[deinit] Starting CodeFreedom teardown...")
    print()

    # ── Step 1: Stop the proxy ───────────────────────────────────────────
    _stop_proxy(cf_dir)
    print()

    # ── Step 2: Stop all tools ───────────────────────────────────────────
    _stop_tools()
    print()

    # ── Step 3: Remove any remaining CodeFreedom containers ──────────────
    containers = _find_codefreedom_containers()
    if containers:
        eprint(
            f"[deinit] Removing {len(containers)} remaining CodeFreedom container(s)..."
        )
        for name in containers:
            eprint(f"   Removing '{name}'...")
            _stop_and_remove_container(name)
        eprint("   [OK] All remaining containers removed.")
    else:
        eprint("[deinit] No remaining CodeFreedom containers found.")
    print()

    # ── Step 4: Remove the shared codefreedom Docker network ────────────
    try:
        net_inspect = subprocess.run(
            ["docker", "network", "inspect", "codefreedom"],
            capture_output=True,
            timeout=10,
            check=False,
        )
        if net_inspect.returncode == 0:
            eprint("[deinit] Removing shared 'codefreedom' Docker network...")
            subprocess.run(
                ["docker", "network", "rm", "codefreedom"],
                capture_output=True,
                timeout=15,
                check=False,
            )
            eprint("   [OK] Network removed.")
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    print()

    # ── Step 5: Confirm and remove CodeFreedom home directory ────────────
    if not cf_dir.exists():
        eprint(f"[deinit] Directory '{cf_dir}' does not exist — nothing more to do.")
        eprint("[deinit] Teardown complete.")
        return 0

    if not force:
        eprint(
            f"[deinit] This will permanently DELETE the entire '{cf_dir}' directory."
        )
        eprint("   This includes all profiles, configs, credentials, and tool data.")
        eprint()
        try:
            response = input("   Are you sure? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            eprint()
            eprint("[deinit] Aborted.")
            return 1
        if response not in ("y", "yes"):
            eprint("[deinit] Aborted.")
            return 1

    _remove_codefreedom_dir(cf_dir)
    print()
    eprint("[deinit] Teardown complete. CodeFreedom has been fully removed.")
    return 0
