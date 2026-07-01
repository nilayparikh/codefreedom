"""Resolve the project root for a given CWD via ``git rev-parse``.

The codebase-memory tool is git-locked: a workspace is a git repo, and
its root is whatever ``git rev-parse --show-toplevel`` returns from the
CWD. This keeps the project boundary unambiguous (no arbitrary ancestor
walks with a depth limit) and aligns with the upstream CBM tool, which
already keys indexes by the git-tracked file set.

Resolution algorithm
--------------------

Starting at ``cwd`` and walking up to the filesystem root, we look for a
directory that contains a ``.git`` entry (file or directory — worktrees
use a ``.git`` file that points at the real git dir). The *first* such
directory we hit is the project root, and we verify it with
``git -C <dir> rev-parse --show-toplevel``.

If ``--show-toplevel`` fails (e.g. the repo has ``core.bare=true`` set
on a non-bare working tree — a known misconfiguration), we fall back to
``git rev-parse --git-dir`` and resolve its parent, or simply return the
directory that contains ``.git``.

The walk is bounded at 3 levels above the original CWD so a stray
``.git`` somewhere far up the tree (e.g. ``$HOME/.git``) can't capture a
deeply nested CWD by accident. The bound is inclusive: levels 0, 1, 2, 3
are checked, so a project at ``~/code/repo`` is reachable from
``~/code/repo/a/b/c`` (cwd → a → b → repo, 3 levels up).

If no ``.git`` is found within the bound, :class:`NotInGitRepo` is
raised. The user can ``cd`` into a git repo or run ``git init`` in their
current directory to fix this.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


_MAX_WALK_LEVELS = 3


class NotInGitRepo(RuntimeError):
    """Raised when ``git rev-parse`` finds no toplevel from a CWD.

    The CWD did not contain a ``.git`` and walking up to
    ``_MAX_WALK_LEVELS`` parents did not find one either.
    """


def is_git_available() -> bool:
    """Return True if the ``git`` executable is on ``$PATH``."""
    return shutil.which("git") is not None


def find_project_root(cwd: str | Path) -> Path:
    """Walk up from ``cwd`` looking for a git toplevel.

    Returns the resolved absolute path of the project root. Raises
    :class:`NotInGitRepo` if no ``.git`` is found within the bound or
    if ``git`` is not installed.
    """
    if not is_git_available():
        raise NotInGitRepo(
            "The 'git' executable was not found on $PATH. "
            "Install git or run this command from a system that has it."
        )

    start = Path(cwd).resolve()
    if not start.is_dir():
        raise NotInGitRepo(f"CWD does not exist or is not a directory: {start}")

    for level in range(_MAX_WALK_LEVELS + 1):
        candidate = _walk_up(start, level)
        if candidate is None:
            break
        if _has_git(candidate):
            resolved = _resolve_root(candidate)
            if resolved is not None:
                return resolved

    raise NotInGitRepo(
        f"No git repository found within {_MAX_WALK_LEVELS} levels of {start}. "
        "Codebase Memory requires a git repo. Run 'git init' or cd into one."
    )


def _walk_up(start: Path, levels: int) -> Path | None:
    """Return ``start`` walked up ``levels`` times, or None at filesystem root."""
    current = start
    for _ in range(levels):
        parent = current.parent
        if parent == current:
            return None
        current = parent
    return current


def _has_git(directory: Path) -> bool:
    """True if ``directory`` contains a ``.git`` entry (file or directory)."""
    git_entry = directory / ".git"
    return git_entry.exists()


def _resolve_root(directory: Path) -> Path | None:
    """Resolve the project root from a directory that has ``.git``.

    Tries ``git rev-parse --show-toplevel`` first. If that fails (e.g.
    ``core.bare=true`` on a non-bare repo), falls back to
    ``git rev-parse --git-dir`` and resolves its parent, or finally
    returns the directory itself.
    """
    toplevel = _git_toplevel(directory)
    if toplevel is not None:
        return toplevel

    git_dir = _git_git_dir(directory)
    if git_dir is not None:
        if git_dir.name == ".git":
            return git_dir.parent.resolve()
        return git_dir.resolve()

    return directory.resolve()


def _git_toplevel(directory: Path) -> Path | None:
    """Return ``git rev-parse --show-toplevel`` of ``directory`` or None."""
    try:
        result = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    toplevel = result.stdout.strip()
    if not toplevel:
        return None
    return Path(toplevel).resolve()


def _git_git_dir(directory: Path) -> Path | None:
    """Return ``git rev-parse --git-dir`` of ``directory`` or None.

    Used as a fallback when ``--show-toplevel`` fails (e.g. bare repos).
    Returns an absolute path.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--absolute-git-dir"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    git_dir = result.stdout.strip()
    if not git_dir:
        return None
    return Path(git_dir).resolve()
