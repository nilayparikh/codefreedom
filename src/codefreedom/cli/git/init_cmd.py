"""cf git init — Add/update git block in .cf.yaml project config."""

from __future__ import annotations

from pathlib import Path

from codefreedom.cli.git.git_ops import get_git_root
from codefreedom.cli.project_config import update_cf_yaml
from codefreedom.log import eprint, tag


def _detect_modules(git_root: Path) -> list[str]:
    """Auto-detect modules from src/<package>/*/ directory structure."""
    modules: list[str] = []
    src_dir = git_root / "src"
    if not src_dir.is_dir():
        return modules

    pkg_dirs = [d for d in src_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
    if not pkg_dirs:
        return modules

    for pkg_dir in pkg_dirs:
        for item in sorted(pkg_dir.iterdir()):
            if item.is_dir() and not item.name.startswith("_") and not item.name.startswith("."):
                modules.append(item.name)

    return modules


def _build_git_block(modules: list[str]) -> dict:
    """Build the git config block."""
    block: dict = {}
    if modules:
        block["modules"] = modules
    return block


def run_init(args: object) -> int:
    """Execute cf git init.

    - If .cf.yaml doesn't exist: create it with git block.
    - If .cf.yaml exists but has no git block: add git block.
    - If .cf.yaml exists and has git block: skip (unless --force).
    """
    git_root = get_git_root(Path.cwd())
    if git_root is None:
        eprint(f"{tag('ERROR')} Not a git repository.")
        return 1

    target = git_root / ".cf.yaml"
    force = getattr(args, "force", False)
    modules = _detect_modules(git_root)
    git_block = _build_git_block(modules)

    result = update_cf_yaml(target, "git", git_block, force=force)

    if result == 2:
        eprint(f"{tag('SKIP')} .cf.yaml already has a git block. Use --force to regenerate.")
        return 0

    eprint(f"{tag('SET')} Updated git block in {target}")
    if modules:
        eprint(f"{tag('INFO')} Detected modules: {', '.join(modules)}")
    else:
        eprint(f"{tag('INFO')} No modules auto-detected. Edit .cf.yaml to add them.")

    return 0
