"""Git subprocess wrappers for cf git commands."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run_git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run a git command and return the result."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(cwd) if cwd else None,
    )
    return result


def is_git_repo(path: Path | None = None) -> bool:
    """Check if the given path (or cwd) is inside a git repository."""
    result = _run_git(["rev-parse", "--is-inside-work-tree"], cwd=path)
    return result.returncode == 0 and result.stdout.strip() == "true"


def get_git_root(path: Path | None = None) -> Path | None:
    """Return the git repository root, or None if not in a repo."""
    result = _run_git(["rev-parse", "--show-toplevel"], cwd=path)
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return None


def get_current_branch(cwd: Path | None = None) -> str | None:
    """Return the current branch name, or None."""
    result = _run_git(["branch", "--show-current"], cwd=cwd)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


def get_remote_url(cwd: Path | None = None) -> str | None:
    """Return the origin remote URL, or None."""
    result = _run_git(["remote", "get-url", "origin"], cwd=cwd)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


def get_status(cwd: Path | None = None) -> str:
    """Return git status --porcelain output."""
    result = _run_git(["status", "--porcelain"], cwd=cwd)
    return result.stdout.strip() if result.returncode == 0 else ""


def get_staged_files(cwd: Path | None = None) -> list[str]:
    """Return list of staged file paths."""
    result = _run_git(["diff", "--cached", "--name-only"], cwd=cwd)
    if result.returncode != 0:
        return []
    return [f for f in result.stdout.strip().split("\n") if f]


def get_changed_files(cwd: Path | None = None) -> list[str]:
    """Return list of all changed files (staged + unstaged + untracked)."""
    result = _run_git(["status", "--porcelain"], cwd=cwd)
    if result.returncode != 0:
        return []
    files = []
    for line in result.stdout.strip().split("\n"):
        if line and len(line) > 3:
            files.append(line[3:])
    return files


def stage_files(files: list[str] | None = None, cwd: Path | None = None) -> bool:
    """Stage files. If files is None, stage all changes."""
    if files:
        result = _run_git(["add", *files], cwd=cwd)
    else:
        result = _run_git(["add", "-A"], cwd=cwd)
    return result.returncode == 0


def get_staged_diff(cwd: Path | None = None) -> str:
    """Return the staged diff."""
    result = _run_git(["diff", "--cached"], cwd=cwd)
    return result.stdout if result.returncode == 0 else ""


def get_diff(target: str, cwd: Path | None = None) -> str:
    """Return diff between target branch and HEAD."""
    result = _run_git(["diff", f"{target}...HEAD"], cwd=cwd)
    return result.stdout if result.returncode == 0 else ""


def get_log(target: str, cwd: Path | None = None) -> str:
    """Return onelog between target branch and HEAD."""
    result = _run_git(["log", "--oneline", f"{target}..HEAD"], cwd=cwd)
    return result.stdout if result.returncode == 0 else ""


def commit(message: str, signed: bool = False, cwd: Path | None = None) -> tuple[bool, str]:
    """Create a git commit. Returns (success, output)."""
    args = ["commit"]
    if signed:
        args.append("-S")
    args.extend(["-m", message])
    result = _run_git(args, cwd=cwd)
    return result.returncode == 0, result.stdout + result.stderr


def push(cwd: Path | None = None) -> tuple[bool, str]:
    """Push current branch to origin. Returns (success, output)."""
    branch = get_current_branch(cwd)
    if not branch:
        return False, "Could not determine current branch"
    result = _run_git(["push", "origin", branch], cwd=cwd)
    return result.returncode == 0, result.stdout + result.stderr


def parse_remote_owner_repo(remote_url: str) -> tuple[str, str] | None:
    """Extract owner and repo from a remote URL.

    Supports:
      - https://github.com/owner/repo.git
      - git@github.com:owner/repo.git
    """
    import re

    https_match = re.match(r"https://github\.com/([^/]+)/([^/]+?)(?:\.git)?$", remote_url)
    if https_match:
        return https_match.group(1), https_match.group(2)

    ssh_match = re.match(r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$", remote_url)
    if ssh_match:
        return ssh_match.group(1), ssh_match.group(2)

    return None
