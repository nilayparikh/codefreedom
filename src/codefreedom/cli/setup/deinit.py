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

from codefreedom.core.config import get_codefreedom_dir
from codefreedom.log import eprint, tag


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

    eprint(f"{tag('DEINIT')} Stopping proxy...")
    # Use the canonical get_env() chain to resolve all proxy env vars
    # (including SUFFIX_ID, POSTGRES_HOST_* paths, and os.environ).
    try:
        from codefreedom.env_loader import get_env

        compose_env = get_env(
            Path.cwd(),
            component="proxy",
            verbose=False,
            extra_injections={
                "POSTGRES_HOST_DATA_DIR": str(cf_dir / "pg" / "data"),
                "POSTGRES_HOST_BACKUP_DIR": str(cf_dir / "pg" / "backup"),
            },
        )
    except Exception:
        # Fallback: minimal env for docker compose (shouldn't happen)
        compose_env = dict(os.environ)

    suffix = compose_env.get("SUFFIX_ID", "0000")
    compose_env["COMPOSE_PROJECT_NAME"] = f"codefreedom-{suffix}"

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
            eprint(f"{tag('DEINIT')} Proxy stopped.")
        else:
            eprint(f"{tag('DEINIT')} Warning: proxy may not have stopped cleanly.")
        return result.returncode
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        eprint(f"{tag('DEINIT')} Warning: could not stop proxy: {exc}")
        return 1


def _stop_tools() -> int:
    """Stop all CodeFreedom tool containers using the existing tools machinery."""
    try:
        from codefreedom.cli.run.tools import stop_all as tools_stop_all

        eprint(f"{tag('DEINIT')} Stopping all tools...")
        return tools_stop_all()
    except ImportError as exc:
        eprint(f"{tag('DEINIT')} Warning: could not import tools module: {exc}")
        return 1
    except Exception as exc:
        eprint(f"{tag('DEINIT')} Warning: failed to stop tools: {exc}")
        return 1


def _remove_codefreedom_dir(cf_dir: Path) -> None:
    """Remove the CodeFreedom home directory and all its contents.

    Preserves ``.env.user`` — it's a user-managed override file that should
    survive a full teardown. Prints a message telling the user where it is.
    """
    if not cf_dir.exists():
        eprint(f"{tag('DEINIT')} Directory '{cf_dir}' does not exist — nothing to remove.")
        return

    # Preserve .env.user — user-managed override, never auto-created by recipes
    user_env = cf_dir / ".env.user"
    preserved = None
    if user_env.exists():
        try:
            preserved = user_env.read_text()
        except OSError:
            pass

    eprint(f"{tag('DEINIT')} Removing '{cf_dir}' (preserving .env.user)...")
    try:
        shutil.rmtree(cf_dir)
        eprint(f"{tag('DEINIT')} Directory removed.")
    except OSError as exc:
        eprint(f"{tag('DEINIT')} Failed to remove directory: {exc}")
        sys.exit(1)

    # Restore .env.user
    if preserved is not None:
        try:
            cf_dir.mkdir(parents=True, exist_ok=True)
            user_env.write_text(preserved)
            eprint(f"{tag('DEINIT')} Preserved '{user_env}' (user overrides).")
        except OSError as exc:
            eprint(f"   {tag('WARN')} Could not restore .env.user: {exc}")


def run(args: argparse.Namespace) -> int:
    """Execute the deinit subcommand. Returns exit code."""
    force = getattr(args, "force", False)
    cf_dir = get_codefreedom_dir()

    eprint(f"{tag('DEINIT')} Starting CodeFreedom teardown...")
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
            f"[DEINIT] Removing {len(containers)} remaining CodeFreedom container(s)..."
        )
        for name in containers:
            eprint(f"   Removing '{name}'...")
            _stop_and_remove_container(name)
        eprint(f"{tag('DEINIT')} All remaining containers removed.")
    else:
        eprint(f"{tag('DEINIT')} No remaining CodeFreedom containers found.")
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
            eprint(f"{tag('DEINIT')} Removing shared 'codefreedom' Docker network...")
            subprocess.run(
                ["docker", "network", "rm", "codefreedom"],
                capture_output=True,
                timeout=15,
                check=False,
            )
            eprint(f"{tag('DEINIT')} Network removed.")
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    print()

    # ── Step 5: Confirm and remove CodeFreedom home directory ────────────
    if not cf_dir.exists():
        eprint(f"{tag('DEINIT')} Directory '{cf_dir}' does not exist — nothing more to do.")
        eprint(f"{tag('DEINIT')} Teardown complete.")
        return 0

    if not force:
        eprint(
            f"[DEINIT] This will permanently DELETE the entire '{cf_dir}' directory."
        )
        eprint("   This includes all profiles, configs, credentials, and tool data.")
        eprint()
        try:
            response = input("   Are you sure? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            eprint()
            eprint(f"{tag('DEINIT')} Aborted.")
            return 1
        if response not in ("y", "yes"):
            eprint(f"{tag('DEINIT')} Aborted.")
            return 1

    _remove_codefreedom_dir(cf_dir)
    print()
    eprint(f"{tag('DEINIT')} Teardown complete. CodeFreedom has been fully removed.")
    return 0
