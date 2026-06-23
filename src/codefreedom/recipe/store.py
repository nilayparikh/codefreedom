"""Recipe store resolution — fetch, clone, and list recipes."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import time
import errno
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from codefreedom.core.http_client import HTTPError, HTTPStatusError, get_text
from codefreedom.core.config import get_codefreedom_dir
from codefreedom.log import eprint, tag

# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

RECIPE_OWNER = "nilayparikh"
RECIPE_REPO = "codefreedom-recipes"

_OFFICIAL_REPO_URL = f"https://github.com/{RECIPE_OWNER}/{RECIPE_REPO}.git"


def _resolve_recipe_branch() -> str:
    """Resolve the recipe branch from the CLI version.

    Branch mapping:
      - 0.2.2rc1.dev1  → dev/v0.2.2
      - 0.2.2rc1       → rc/v0.2.2
      - 0.2.2          → v0.2.2
      - 0.0.0 (fallback) → main
    """
    from codefreedom import __version__

    ver = __version__
    if ver == "0.0.0":
        return "main"

    parts = ver.split(".", 2)
    if len(parts) < 3:
        return "main"

    major, minor = parts[0], parts[1]
    patch_prerelease = parts[2]

    m = re.match(r"(\d+)(.*)", patch_prerelease)
    if not m:
        return "main"

    patch = m.group(1)
    suffix = m.group(2)
    base = f"{major}.{minor}.{patch}"

    if ".dev" in suffix:
        return f"dev/v{base}"
    if suffix.startswith("rc"):
        return f"rc/v{base}"

    return f"v{base}"


def _raw_base(branch: str) -> str:
    return (
        f"https://raw.githubusercontent.com/"
        f"{RECIPE_OWNER}/{RECIPE_REPO}/{branch}"
    )


def _github_api_base(branch: str) -> str:
    return f"https://api.github.com/repos/{RECIPE_OWNER}/{RECIPE_REPO}"

# ═══════════════════════════════════════════════════════════════════════════════
# Exceptions
# ═══════════════════════════════════════════════════════════════════════════════


class RecipeError(Exception):
    """Raised when a recipe operation fails."""


# ═══════════════════════════════════════════════════════════════════════════════
# Store resolution (--store flag)
# ═══════════════════════════════════════════════════════════════════════════════


def _resolve_store(
    store: Optional[str] = None,
    branch: str = "main",
) -> Optional[Path]:
    """Resolve a store to a local directory path.

    When *store* is ``None`` (default), uses the official community repo
    at ``github.com/nilayparikh/codefreedom-recipes``, cloned via GitPython.

    Accepts:
      - GitHub URL (e.g. ``https://github.com/owner/repo.git`` or
        ``git@github.com:owner/repo.git``) — clones to
        ``~/.codefreedom/stores/<owner>-<repo>-<branch>/`` via GitPython
        sparse checkout.
      - Local absolute path (e.g. ``/home/user/my-recipes``).

    The *branch* parameter controls which git branch is checked out when
    cloning the official store (ignored for local paths and custom URLs).

    All sources use the same download mechanism (GitPython sparse checkout),
    ensuring consistent behavior whether using the official repo or a custom
    store.  Git metadata is removed after cloning — only the folder contents
    remain.

    Returns the ``Path`` to the store root, or ``None`` if resolution fails.
    """
    # ── Default: official community repo ────────────────────────────────
    if store is None:
        cf_dir = get_codefreedom_dir()
        store_name = f"{RECIPE_OWNER}-{RECIPE_REPO}-{branch}"
        store_dir = cf_dir / "stores" / store_name
        if _ensure_store(_OFFICIAL_REPO_URL, store_dir, branch=branch):
            return store_dir
        return None

    store = store.strip()

    # ── Local path ──────────────────────────────────────────────────────
    if store.startswith("~"):
        home = (
            os.environ.get("HOME") or os.environ.get("USERPROFILE") or str(Path.home())
        )
        expanded = home + store[1:]
    else:
        expanded = os.path.expanduser(store)
    if os.path.isabs(expanded) or store.startswith("."):
        p = Path(expanded)
        if p.is_dir():
            return p.resolve()
        eprint(
            f"[RECIPE] Warning: Local store path does not exist or is not a directory: {p}"
        )
        return None

    # ── GitHub URL ──────────────────────────────────────────────────────
    repo_name = _parse_github_url(store)
    if repo_name is None:
        eprint(f"{tag('RECIPE')} Warning: Could not parse GitHub URL: {store}")
        return None

    cf_dir = get_codefreedom_dir()
    store_dir = cf_dir / "stores" / repo_name

    if _ensure_store(store, store_dir):
        return store_dir

    eprint(f"{tag('RECIPE')} Warning: Failed to clone/pull store from {store}")
    return None


def _rmtree_retry(path: Path, retries: int = 3, delay: float = 0.5) -> None:
    """Remove a directory tree with retries for Windows file-locking.

    On Windows, ``.git`` pack files are frequently locked by antivirus
    scanners or the Windows Search Indexer.  This helper retries the
    removal after clearing read-only flags and sleeping briefly.
    """
    for attempt in range(retries):
        try:
            shutil.rmtree(
                path,
                onerror=_handle_remove_readonly,
            )
            return
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise


def _handle_remove_readonly(func: Any, path: str, exc: Any) -> None:  # noqa: ARG001
    """Error handler for ``shutil.rmtree`` — clear read-only and retry."""
    excvalue = exc[1]
    if func in (os.unlink, os.rmdir) and excvalue.errno == errno.EACCES:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    else:
        raise


def _ensure_store(url: str, dest: Path, branch: str = "main") -> bool:
    """Clone a Git store fresh and remove metadata.

    Always re-clones to guarantee latest content — there is no local
    cache beyond the current invocation.  After a successful clone the
    ``.git/`` directory is removed so only recipe folder contents remain.
    """
    if dest.exists():
        _rmtree_retry(dest)
    dest.mkdir(parents=True, exist_ok=True)
    if _clone_or_pull_store(url, dest, branch=branch):
        _remove_git_metadata(dest)
        return True
    return False


def _parse_github_url(url: str) -> Optional[str]:
    """Parse a GitHub URL and return a sanitized directory name.

    Handles formats:
      - ``https://github.com/owner/repo.git``
      - ``https://github.com/owner/repo``
      - ``git@github.com:owner/repo.git``
    """
    # HTTPS: https://github.com/owner/repo[.git]
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if m:
        return f"{m.group(1)}-{m.group(2).replace('.git', '')}"

    # SSH: git@github.com:owner/repo[.git]
    m = re.match(r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$", url)
    if m:
        return f"{m.group(1)}-{m.group(2).replace('.git', '')}"

    return None


def _clone_or_pull_store(url: str, dest: Path, branch: str = "main") -> bool:
    """Clone or update a Git repository into *dest* using sparse checkout.

    Uses GitPython with sparse checkout to fetch only the directory structure
    and recipe manifests needed to list and resolve recipes.  The user's
    stored GitHub credentials (git credential helper / SSH agent) are used
    automatically.

    The *branch* parameter controls which remote branch is fetched.  After
    cloning from a branch-specific store (e.g. ``staging``) the ``.git/``
    metadata is removed, so subsequent calls always do a fresh clone.

    Returns ``True`` on success.
    """
    from git import Repo, GitCommandError

    try:
        if dest.exists() and (dest / ".git").is_dir():
            # Already cloned — update with fast-forward pull on the branch
            print(f"  {tag('STORE')} Updating existing store at {dest} ({branch})")
            repo = Repo(dest)
            origin = repo.remotes.origin
            origin.pull(branch, ff_only=True)
            return True

        # ── Fresh clone with sparse checkout ──────────────────────────────
        print(f"  {tag('STORE')} Cloning {url} -> {dest} (branch: {branch})")
        dest.mkdir(parents=True, exist_ok=True)
        repo = Repo.init(dest)

        with repo.config_writer() as config:
            config.set_value("core", "sparseCheckout", "true")

        # Sparse checkout pattern: fetch root files + all top-level dirs
        # so we can list recipes and read recipe.yaml manifests.
        sparse_path = Path(repo.git_dir) / "info" / "sparse-checkout"
        sparse_path.parent.mkdir(parents=True, exist_ok=True)
        sparse_path.write_text("/*\n*/\n", encoding="utf-8")

        origin = repo.create_remote("origin", url)
        # Fetch the specific branch and check it out
        origin.fetch(branch)
        repo.git.checkout(branch)
        return True

    except GitCommandError as e:
        eprint(f"{tag('RECIPE')} Warning: Git operation failed: {e}")
        return False
    except Exception as e:
        eprint(f"{tag('RECIPE')} Warning: Git operation failed: {e}")
        return False


def _remove_git_metadata(path: Path) -> None:
    """Remove all Git metadata from a directory tree.

    Deletes ``.git/``, ``.gitattributes``, ``.gitignore``, and
    ``.gitmodules`` recursively so only the recipe folder contents
    remain.
    """
    git_dir = path / ".git"
    if git_dir.is_dir():
        _rmtree_retry(git_dir)

    for name in (".gitattributes", ".gitignore", ".gitmodules"):
        f = path / name
        if f.is_file():
            f.unlink(missing_ok=True)


def _list_recipes_from_store(store_path: Path) -> List[str]:
    """List recipes available in a custom store directory.

    Scans top-level subdirectories for ``recipe.yaml`` files.
    Directories starting with ``_`` are excluded.
    """
    if not store_path.is_dir():
        return []

    recipes: List[str] = []
    for child in sorted(store_path.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("_"):
            continue
        if (child / "recipe.yaml").is_file():
            recipes.append(child.name)
    return recipes


# ═══════════════════════════════════════════════════════════════════════════════
# GitHub fetch helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _raw_url(recipe_name: str, path: str = "", branch: str | None = None) -> str:
    """Build raw.githubusercontent.com URL for a recipe file."""
    if branch is None:
        branch = _resolve_recipe_branch()
    base = _raw_base(branch)
    parts = [base, recipe_name]
    if path:
        parts.append(path)
    return "/".join(parts)


def _fetch_text(url: str, timeout: int = 15) -> str:
    """Fetch text content from a URL with a short timeout."""
    try:
        return get_text(url, timeout=timeout, headers={"User-Agent": "codefreedom/0.1"})
    except HTTPStatusError as e:
        raise RecipeError(f"HTTP {e.status_code} fetching {url}") from e
    except HTTPError as e:
        raise RecipeError(f"URL error for {url}: {e}") from e


def _fetch_recipe_manifest(recipe_name: str) -> Dict[str, Any]:
    """Fetch and parse recipe.yaml from GitHub."""
    url = _raw_url(recipe_name, "recipe.yaml")
    try:
        content = _fetch_text(url)
    except RecipeError as e:
        raise RecipeError(
            f"Recipe '{recipe_name}' not found on GitHub. "
            f"Available recipes: https://github.com/"
            f"{RECIPE_OWNER}/{RECIPE_REPO}"
        ) from e

    try:
        manifest = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise RecipeError(f"Invalid recipe.yaml: {e}") from e

    if not isinstance(manifest, dict):
        raise RecipeError("recipe.yaml must be a mapping (dictionary)")

    # Ensure name is set
    if not manifest.get("name"):
        manifest["name"] = recipe_name

    return manifest


def _fetch_recipe_files(
    recipe_name: str,
    manifest: Dict[str, Any],
) -> Dict[str, str]:
    """Fetch all file contents for a recipe from GitHub.

    Returns ``{target_path: content_string}``.
    Missing / failed files are silently skipped with a warning.
    """
    files: Dict[str, str] = {}
    for entry in manifest.get("files", []):
        src_path = entry.get("path", "")
        target = entry.get("target", src_path)
        url = _raw_url(recipe_name, src_path)
        try:
            content = _fetch_text(url)
            files[target] = content
            print(f"  {tag('FETCH')} {src_path}")
        except RecipeError as e:
            eprint(f"{tag('RECIPE')} Warning: Could not fetch {src_path}: {e}")
    return files


def _fetch_available_recipes(branch: str | None = None) -> List[str]:
    """List available recipes by checking each top-level dir for recipe.yaml."""
    if branch is None:
        branch = _resolve_recipe_branch()
    try:
        url = f"{_github_api_base(branch)}/contents"
        raw = _fetch_text(url)
        items = json.loads(raw)
        candidates: List[str] = []
        for item in items:
            if item.get("type") == "dir":
                name = item["name"]
                if name.startswith("_"):
                    continue  # Skip private/base recipes
                try:
                    _fetch_text(_raw_url(name, "recipe.yaml", branch=branch))
                    candidates.append(name)
                except RecipeError:
                    pass
        return sorted(candidates)
    except (RecipeError, json.JSONDecodeError) as e:
        eprint(f"{tag('RECIPE')} Warning: Could not list recipes: {e}")
        return []


def _parse_yaml_file(path: Path) -> Dict[str, Any]:
    """Parse a local YAML file."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise RecipeError(f"{path.name} must be a mapping")
    return data


# ═══════════════════════════════════════════════════════════════════════════════
# Recipe resolution (local submodule → GitHub raw)
# ═══════════════════════════════════════════════════════════════════════════════


def _resolve_recipe(
    name: str,
    store_path: Optional[Path] = None,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, str]]:
    """Resolve a recipe from the store or local submodule.

    Priority:
      1. Store directory (official repo or ``--store``) — always available
      2. Local submodule at ``recipes/{name}/`` (development convenience)

    Both the official repo and custom ``--store`` paths use the same
    GitPython sparse checkout mechanism to fetch recipe content.

    Returns (manifest, file_contents_dict).
    If the recipe cannot be found, returns (None, {}).
    """
    # 0. Store takes highest priority
    if store_path is not None:
        recipe_dir = store_path / name
        manifest_path = recipe_dir / "recipe.yaml"
        if manifest_path.exists():
            try:
                manifest = _parse_yaml_file(manifest_path)
                manifest["_recipe_dir"] = str(recipe_dir)
                files = _read_local_files(recipe_dir, manifest)
                return manifest, files
            except RecipeError as e:
                eprint(
                    f"{tag('RECIPE')} Warning: Store recipe '{name}' has errors: {e}"
                )
                return None, {}

    # 1. Try local submodule (dev installs with git clone) as fallback
    local_path = _find_local_recipe(name)
    if local_path is not None:
        manifest_path = local_path / "recipe.yaml"
        if manifest_path.exists():
            try:
                manifest = _parse_yaml_file(manifest_path)
                manifest["_recipe_dir"] = str(local_path)
                files = _read_local_files(local_path, manifest)
                return manifest, files
            except RecipeError as e:
                eprint(
                    f"{tag('RECIPE')} Warning: Local recipe '{name}' has errors: {e}"
                )

    return None, {}


def _find_local_recipe(name: str) -> Optional[Path]:
    """Find a recipe folder in the local submodule at ``recipes/{name}/``.

    Works when codefreedom is installed from a git clone with submodules
    initialised.  Returns ``None`` if the submodule is not available.
    """
    try:
        # Walk up from the package source to find the project root
        pkg_dir = Path(__file__).resolve().parent.parent.parent.parent
        recipe_dir = pkg_dir / "recipes" / name
        if recipe_dir.is_dir():
            return recipe_dir
    except (NameError, IndexError):
        pass

    # Also try relative to the current working directory
    cwd_recipe = Path.cwd() / "recipes" / name
    if cwd_recipe.is_dir():
        return cwd_recipe

    return None


def _read_local_files(
    recipe_dir: Path,
    manifest: Dict[str, Any],
) -> Dict[str, str]:
    """Read all recipe files from the local filesystem.

    Missing files are silently skipped — they may be provided by an
    extending base recipe, or simply not exist yet.
    """
    files: Dict[str, str] = {}
    for entry in manifest.get("files", []):
        src_path = entry.get("path", "")
        target = entry.get("target", src_path)
        file_path = recipe_dir / src_path
        if file_path.exists():
            files[target] = file_path.read_text(encoding="utf-8")
    return files
