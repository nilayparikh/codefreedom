"""Deinit subcommand -- fully tear down CodeFreedom configuration and containers.

Usage:
    codefreedom setup deinit              Interactive teardown (prompts for confirmation)
    codefreedom setup deinit --force      Skip confirmation prompt
    codefreedom setup deinit --clean-images  Also remove Docker images and volumes
    codefreedom setup deinit --help       Show this help

Teardown steps:
  1. Stop the proxy (docker compose down)
  2. Stop all tools (chrome, web, github, web-bridge)
  3. Find and remove any remaining CodeFreedom Docker containers (sandbox
     sessions, orphaned containers, etc.)
  4. Remove the shared ``codefreedom`` Docker network
  5. (Optional) Remove CodeFreedom Docker images, PG volumes, and dangling images
  6. Prompt the user to confirm removal of the CodeFreedom home directory
     (``~/.codefreedom/`` or ``$CODEFREEDOM_HOME``)
  7. Remove the CodeFreedom home directory
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import os
from pathlib import Path

from codefreedom.core.config import get_codefreedom_dir, get_config_dir
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
    config_dir = get_config_dir()
    compose_file = config_dir / "proxy" / "docker-compose.yaml"
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
    """Remove all contents of the CodeFreedom home directory.

    Preserves ``config/override.yaml`` — it's a user-managed override file that should
    survive a full teardown. Prints a message telling the user where it is.
    Removes contents rather than the directory itself to avoid Windows
    ``WinError 32`` (directory held open by another process).
    """
    if not cf_dir.exists():
        eprint(
            f"{tag('DEINIT')} Directory '{cf_dir}' does not exist — nothing to remove."
        )
        return

    config_dir = cf_dir / "config"

    # Preserve override.yaml in config directory — user-managed override
    override_path = config_dir / "override.yaml"
    preserved = None
    if override_path.exists():
        try:
            preserved = override_path.read_text(encoding="utf-8")
        except OSError:
            pass

    eprint(
        f"{tag('DEINIT')} Removing contents of '{cf_dir}' (preserving config/override.yaml)..."
    )

    errors: list[str] = []
    for item in sorted(cf_dir.iterdir(), key=lambda p: p.name):
        # Skip agent home dirs (claude-code/, mimo-code/, etc.) - not managed by CLI
        if item.name in (
            "claude-code",
            "mimo-code",
            "open-code",
            "codex-code",
            "pi-code",
        ):
            continue
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        except OSError as exc:
            errors.append(f"  {tag('WARN')} Could not remove {item}: {exc}")

    if errors:
        for line in errors:
            eprint(line)
        eprint(
            f"{tag('DEINIT')} Some items could not be removed (files may be in use)."
        )
    else:
        eprint(f"{tag('DEINIT')} Contents removed.")

    # Restore override.yaml if it was deleted (shouldn't be, but defensive)
    if preserved is not None and not override_path.exists():
        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            override_path.write_text(preserved, encoding="utf-8")
            eprint(f"{tag('DEINIT')} Restored '{override_path}' (user overrides).")
        except OSError as exc:
            eprint(f"   {tag('WARN')} Could not restore override.yaml: {exc}")
    elif preserved is not None:
        eprint(f"{tag('DEINIT')} Preserved '{override_path}' (user overrides).")

    # If no override.yaml was preserved, remove the now-empty directory itself
    if preserved is None:
        try:
            cf_dir.rmdir()
        except OSError:
            pass


def _list_codefreedom_images() -> list[str]:
    """Return locally-pulled CodeFreedom images (``nilayparikh/codefreedom:*``)."""
    try:
        result = subprocess.run(
            [
                "docker",
                "images",
                "--filter",
                "reference=nilayparikh/codefreedom*",
                "--format",
                "{{.Repository}}:{{.Tag}}",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except (subprocess.SubprocessError, FileNotFoundError):
        return []


def _remove_codefreedom_images() -> None:
    """Remove all local CodeFreedom Docker images."""
    images = _list_codefreedom_images()
    if not images:
        eprint(f"{tag('DEINIT')} No CodeFreedom Docker images found.")
        return

    eprint(f"{tag('DEINIT')} Removing {len(images)} CodeFreedom image(s)...")
    for image in images:
        eprint(f"   Removing '{image}'...")
        try:
            subprocess.run(
                ["docker", "image", "rm", "-f", image],
                capture_output=True,
                timeout=60,
                check=False,
            )
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
    eprint(f"{tag('DEINIT')} CodeFreedom images removed.")


def _remove_codefreedom_volumes() -> None:
    """Remove CodeFreedom PostgreSQL named volumes."""
    volumes = ["codefreedom_pg_data", "codefreedom_pg_backup"]
    removed = 0
    for vol in volumes:
        try:
            inspect = subprocess.run(
                ["docker", "volume", "inspect", vol],
                capture_output=True,
                timeout=10,
                check=False,
            )
            if inspect.returncode == 0:
                eprint(f"{tag('DEINIT')} Removing volume '{vol}'...")
                subprocess.run(
                    ["docker", "volume", "rm", vol],
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
                removed += 1
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
    if removed:
        eprint(f"{tag('DEINIT')} Removed {removed} volume(s).")
    else:
        eprint(f"{tag('DEINIT')} No CodeFreedom volumes found.")


def _prune_dangling_images() -> None:
    """Prune dangling (untagged) Docker images."""
    eprint(f"{tag('DEINIT')} Pruning dangling Docker images...")
    try:
        result = subprocess.run(
            ["docker", "image", "prune", "-f"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode == 0:
            reclaimed = ""
            for line in result.stdout.splitlines():
                if "reclaimed" in line.lower():
                    reclaimed = line.strip()
                    break
            if reclaimed:
                eprint(f"{tag('DEINIT')} {reclaimed}")
            else:
                eprint(f"{tag('DEINIT')} Dangling images pruned.")
        else:
            eprint(f"{tag('DEINIT')} Warning: could not prune dangling images.")
    except (subprocess.SubprocessError, FileNotFoundError):
        eprint(f"{tag('DEINIT')} Warning: could not prune dangling images.")


def _clean_docker_cache() -> None:
    """Remove all CodeFreedom Docker images, volumes, and dangling images."""
    _remove_codefreedom_images()
    _remove_codefreedom_volumes()
    _prune_dangling_images()


def run(args: argparse.Namespace) -> int:
    """Execute the deinit subcommand. Returns exit code."""
    force = getattr(args, "force", False)
    clean_images = getattr(args, "clean_images", False)
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

    # ── Step 5: Remove Docker images, volumes, and dangling images ───────
    if clean_images:
        if not force:
            images = _list_codefreedom_images()
            eprint(
                f"[DEINIT] This will remove {len(images)} CodeFreedom image(s),"
                " PG volumes, and dangling images."
            )
            eprint()
            try:
                response = input("   Continue? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                eprint()
                eprint(f"{tag('DEINIT')} Aborted.")
                return 1
            if response not in ("y", "yes"):
                eprint(f"{tag('DEINIT')} Aborted.")
                return 1
        _clean_docker_cache()
        print()

    # ── Step 6: Confirm and remove CodeFreedom home directory ────────────
    if not cf_dir.exists():
        eprint(
            f"{tag('DEINIT')} Directory '{cf_dir}' does not exist — nothing more to do."
        )
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
