"""Recipe subsystem for ``cf init --recipe <name>``.

Fetches predefined configuration recipes from the codefreedom-recipes
GitHub repository, then applies them to ``~/.codefreedom/`` with
intelligent structural merging via DeepDiff when a target file already
exists (second+ recipe or pre-existing config).

Recipe source priority:
  1. Custom store (``--store`` flag) — GitHub URL or local folder
  2. Local submodule at ``recipes/{name}/`` (development / git-clone installs)
  3. GitHub raw content (pip-installed / fallback)

``_default`` is silently skipped when not found in a custom store — it's
only required when using the upstream codefreedom-recipes repository.

Recipe format
=============
Each recipe is a folder in ``github.com/nilayparikh/codefreedom-recipes``
containing a ``recipe.yaml`` manifest:

.. code-block:: yaml

    name: opencode-free
    description: "OpenCode Zen free-tier models via LiteLLM proxy"
    version: 1

    files:
      - path: .env.claude.example
        target: .env.claude
        merge: env
      - path: profiles/claude-code.yaml
        target: profiles/claude-code.yaml
        merge: deepdiff
      - path: proxy/config/config.yaml
        target: proxy/config/config.yaml
        merge: deepdiff
      # ...

    required_secrets:
      - var: OPENCODE_ZEN_API_KEY
        prompt: "OpenCode Zen API key"

    optional_config:
      - var: LITELLM_MODEL_ALIAS_BEST
        default: "OpenCode/MiMo-V2.5-FREE"

Merge modes (``merge`` field in files):
  - ``deepdiff`` — structural YAML/JSON diff via DeepDiff
  - ``env`` — key=value .env-style merge (keeps existing keys)
  - ``auto`` — infer from file extension / name
  - ``overwrite`` — always write the recipe version

Orphan detection:
  - After a recipe is applied, any file that exists in a managed
    subdirectory (e.g. ``proxy/config/providers/``) but is NOT listed
    in the new recipe's ``files`` list is auto-detected as an orphan
    and deleted.  This handles switching between recipes that have
    different provider configs (e.g. ``opencode.yaml`` → ``local.yaml``).
  - The root ``~/.codefreedom/`` directory is NEVER scanned, so
    top-level user-created files are safe.
  - Detection is per-directory: only sibling files of managed targets
    are considered.
"""

from __future__ import annotations

import datetime
import json
import os
import secrets
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from codefreedom.admin import backup as cf_backup
from codefreedom.config import get_codefreedom_dir
from codefreedom.env_loader import eprint
from codefreedom.interpolate import interpolate_all_strings
from pydantic import ValidationError

from codefreedom.cli.docker_utils import _TOOL_PROFILE_PATHS
from codefreedom.schemas.recipe import RecipeConfig

# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

RECIPE_OWNER = "nilayparikh"
RECIPE_REPO = "codefreedom-recipes"
RECIPE_BRANCH = "main"

_OFFICIAL_REPO_URL = f"https://github.com/{RECIPE_OWNER}/{RECIPE_REPO}.git"
_RAW_BASE = (
    f"https://raw.githubusercontent.com/"
    f"{RECIPE_OWNER}/{RECIPE_REPO}/{RECIPE_BRANCH}"
)
_GITHUB_API_BASE = f"https://api.github.com/repos/{RECIPE_OWNER}/{RECIPE_REPO}"

MERGEABLE_EXTENSIONS = {".yaml", ".yml", ".json"}

# ═══════════════════════════════════════════════════════════════════════════════
# Exceptions
# ═══════════════════════════════════════════════════════════════════════════════


class RecipeError(Exception):
    """Raised when a recipe operation fails."""


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════


def list_recipes(store: Optional[str] = None, staging: bool = False) -> int:
    """List all available recipes from the recipe store.

    Returns exit code 0 on success, 1 on failure.
    """
    branch = "staging" if staging else "main"
    store_path = _resolve_store(store, branch=branch)

    if store_path:
        recipes = _list_recipes_from_store(store_path)
    else:
        recipes = _fetch_available_recipes()

    if not recipes:
        source = store_path or _GITHUB_API_BASE
        print("[recipe] No recipes found.")
        print(f"         {source}")
        return 1

    print(f"[recipe] Available recipes ({len(recipes)}):")
    for name in recipes:
        print(f"           {name}")
    print()
    print("  Use:  cf init recipe --plan <name>")
    source = store_path or f"https://github.com/{RECIPE_OWNER}/{RECIPE_REPO}"
    print(f"  Store: {source}")
    return 0


def init_recipe(name: str, store: Optional[str] = None, staging: bool = False) -> int:
    """Fetch and apply a recipe to ``~/.codefreedom/``.

    This is the main entry point for ``cf init --recipe <name>``.

    Steps:
      1. Resolve custom store (if ``--store`` provided), then try
         local submodule ``recipes/{name}/``, fall back to GitHub raw.
      2. Parse ``recipe.yaml`` manifest.
      3. For each file in the manifest:
         - If target does **not** exist → create fresh.
         - If target **does** exist → merge using DeepDiff (YAML) or
           key-by-key (.env), preserving existing values.
      4. Detect and delete orphaned files (files from a previous recipe
         that aren't in the new recipe's file list).
      5. Ensure ``.env.user`` exists (created once, never touched again).
      6. Print a "What's Next" summary with required secrets and next steps.
    """
    cf_dir = get_codefreedom_dir()

    # ── 1. Recipe source ────────────────────────────────────────────────
    branch = "staging" if staging else "main"
    store_path = _resolve_store(store, branch=branch)
    manifest, files = _resolve_recipe(name, store_path=store_path)
    if manifest is None:
        # Silently skip _default when not found in the store
        if name == "_default":
            source = store_path or f"https://github.com/{RECIPE_OWNER}/{RECIPE_REPO}"
            print("[recipe] No '_default' recipe in store — skipping.")
            print(f"         Store: {source}")
            return 0
        print(f"[recipe] Recipe '{name}' not found.")
        print("         Run 'cf init recipe --list' to see available recipes.")
        source = store_path or f"https://github.com/{RECIPE_OWNER}/{RECIPE_REPO}"
        print(f"         Store: {source}")
        return 1

    # ── 1b. Collect all managed targets for orphan detection ────────────
    all_managed: set[str] = set()

    def _collect_targets(man: dict) -> None:
        for entry in man.get("files", []):
            target = entry.get("target", entry.get("path", ""))
            if target:
                all_managed.add(target)

    # ── 1c. If recipe extends a base, resolve and install it first ──────
    extends = manifest.get("extends")
    if extends:
        print(f"  [EXTENDS] Installing base recipe '{extends}' first...")
        base_manifest, base_files = _resolve_recipe(extends, store_path=store_path)
        if base_manifest is None:
            print(
                f"  [WARN] Base recipe '{extends}' not found — continuing without it."
            )
        else:
            _collect_targets(base_manifest)
            _install_recipe_files(base_manifest, base_files, cf_dir)

    # ── 2. Install / merge each file ─────────────────────────────────────
    _collect_targets(manifest)
    _install_recipe_files(manifest, files, cf_dir)

    # ── 2b. Orphan detection — delete files from previous recipe(s) ────
    _remove_orphans(all_managed, cf_dir)

    # ── 2c. Ensure .env.user exists (user-managed overrides file) ──────
    _ensure_user_env(cf_dir)

    # ── 3. What's Next summary ──────────────────────────────────────────
    _print_summary(manifest, cf_dir)
    return 0


def plan_recipe(name: str, store: Optional[str] = None, staging: bool = False) -> int:
    """Preview recipe changes without applying them.

    Generates .patch files in ``~/.codefreedom/plans/<plan_id>/``
    showing exactly what would be created or replaced.

    All files are replaced (not merged). The plan shows the diff
    between existing content and the new recipe content.
    """
    cf_dir = get_codefreedom_dir()

    # ── 1. Resolve recipe ──────────────────────────────────────────────
    branch = "staging" if staging else "main"
    store_path = _resolve_store(store, branch=branch)
    manifest, files = _resolve_recipe(name, store_path=store_path)
    if manifest is None:
        print(f"[plan] Recipe '{name}' not found.")
        print("       Run 'cf init recipe --list' to see available recipes.")
        return 1

    # ── 2. Resolve extends chain ───────────────────────────────────────
    plan_entries: list[dict] = []

    def _collect(man: dict, fdict: dict, source_label: str) -> None:
        for entry in man.get("files", []):
            src = entry.get("path", "")
            target = entry.get("target", src)
            content = fdict.get(target) or fdict.get(src)
            if content is None:
                continue
            plan_entries.append(
                {
                    "target": target,
                    "content": content,
                    "merge": entry.get("merge", "auto"),
                    "source": source_label,
                }
            )

    extends = manifest.get("extends")
    base_man: dict[str, Any] | None = None
    if extends:
        base_man, base_files = _resolve_recipe(extends, store_path=store_path)
        if base_man is not None:
            _collect(base_man, base_files, extends)

    _collect(manifest, files, name)

    # ── 2b. Deduplicate by target — keep only the last entry (highest  ──
    #        priority from the extending recipe).                         ──
    seen: dict[str, dict] = {}
    for entry in plan_entries:
        seen[entry["target"]] = entry  # later entries override earlier
    plan_entries = list(seen.values())

    # ── 3. Compute what would happen to each file ──────────────────────
    plan_id = _generate_plan_id()
    tool_home = Path.home() / ".codefreedom"
    plans_dir = cf_dir / "plans" / plan_id
    plans_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, int] = {"create": 0, "replace": 0, "same": 0}
    patch_files: list[dict] = []

    for entry in plan_entries:
        # Tool profiles live in ~/.codefreedom/, everything else respects CODEFREEDOM_HOME.
        if entry["target"] in _TOOL_PROFILE_PATHS:
            dst = tool_home / entry["target"]
        else:
            dst = cf_dir / entry["target"]
        dst.parent.mkdir(parents=True, exist_ok=True)

        if not dst.exists():
            diff = _make_diff("", entry["content"], entry["target"], from_devnull=True)
            safe_name = entry["target"].replace("/", "-")
            patch_name = f"create-{safe_name}.diff"
            (plans_dir / patch_name).write_text(diff, encoding="utf-8")
            # Also store full content for reliable apply
            content_name = f"create-{safe_name}.content"
            (plans_dir / content_name).write_text(entry["content"], encoding="utf-8")
            patch_files.append(
                {
                    "target": entry["target"],
                    "action": "create",
                    "patch": patch_name,
                    "content_file": content_name,
                    "source": entry["source"],
                }
            )
            summary["create"] += 1
            continue

        existing = dst.read_text(encoding="utf-8")
        if existing == entry["content"]:
            patch_files.append(
                {
                    "target": entry["target"],
                    "action": "same",
                    "patch": None,
                    "source": entry["source"],
                }
            )
            summary["same"] += 1
            continue

        # REPLACE — write diff for review + full content for reliable apply
        diff = _make_diff(existing, entry["content"], entry["target"])
        safe_name = entry["target"].replace("/", "-")
        diff_name = f"replace-{safe_name}.diff"
        (plans_dir / diff_name).write_text(diff, encoding="utf-8")
        content_name = f"replace-{safe_name}.content"
        (plans_dir / content_name).write_text(entry["content"], encoding="utf-8")
        patch_files.append(
            {
                "target": entry["target"],
                "action": "replace",
                "patch": diff_name,
                "content_file": content_name,
                "source": entry["source"],
            }
        )
        summary["replace"] += 1

    # ── 3b. Orphan detection — delete files that existed from the    ──
    #        previous recipe but aren't in the new recipe's file list.  ──
    #        Scans each directory that contains a managed file and      ──
    #        flags any sibling file not in the managed set.             ──
    managed_targets = {e["target"] for e in plan_entries}
    orphan_dirs: set[Path] = set()
    for e in plan_entries:
        if e["target"] in _TOOL_PROFILE_PATHS:
            parent = tool_home / e["target"]
        else:
            parent = cf_dir / e["target"]
        parent = parent.parent
        if parent != cf_dir and parent != tool_home:  # Skip root dirs
            orphan_dirs.add(parent)

    for parent_dir in sorted(orphan_dirs):
        if not parent_dir.is_dir():
            continue
        for child in sorted(parent_dir.iterdir()):
            if not child.is_file():
                continue
            try:
                rel = child.relative_to(cf_dir).as_posix()
            except ValueError:
                try:
                    rel = child.relative_to(tool_home).as_posix()
                except ValueError:
                    continue
            if rel not in managed_targets:
                patch_files.append(
                    {
                        "target": rel,
                        "action": "delete",
                        "patch": None,
                        "content_file": None,
                        "source": "orphan",
                    }
                )
                summary["delete"] = summary.get("delete", 0) + 1

    # ── 3c. Collect dirs from base + extending manifests ──────────────
    plan_dirs: list[str] = []

    def _collect_dirs(man: dict) -> None:
        for d in man.get("dirs") or []:
            if d not in plan_dirs:
                plan_dirs.append(d)

    if extends and base_man is not None:
        _collect_dirs(base_man)
    _collect_dirs(manifest)

    # ── 4. Write plan.yaml ─────────────────────────────────────────────
    plan_meta = {
        "plan_id": plan_id,
        "recipe": name,
        "extends": extends,
        "summary": summary,
        "dirs": plan_dirs,
        "files": patch_files,
    }
    (plans_dir / "plan.yaml").write_text(
        yaml.dump(plan_meta, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )

    # ── 5. Print summary ──────────────────────────────────────────────
    delete_count = summary.get("delete", 0)
    print(f"[plan] Recipe: {name}" + (f" (extends {extends})" if extends else ""))
    print(f"[plan] Plan ID: {plan_id}")
    print(f"[plan] Files:   {plans_dir}/")
    print("[plan]")
    print(f"[plan]   {summary['create']} new files")
    print(f"[plan]   {summary['replace']} files to replace")
    print(f"[plan]   {summary['same']} unchanged (skipped)")
    if delete_count:
        print(f"[plan]   {delete_count} files to delete")
    dir_count = len(plan_dirs)
    if dir_count:
        print(f"[plan]   {dir_count} directories to create")
    print("[plan]")
    print(f"[plan]   {'':>8} {'SOURCE':12} DESTINATION")
    print(f"[plan]   {'-'*8} {'-'*12} {'-'*75}")
    for pf in patch_files:
        action = pf["action"].upper().ljust(8)
        src_label = pf["source"][:12].ljust(12)
        target = pf["target"]
        if target in _TOOL_PROFILE_PATHS:
            dest = tool_home / target
        else:
            dest = cf_dir / target
        print(f"[plan]   {action} {src_label} {dest}")
    for d in plan_dirs:
        dest = cf_dir / d
        print(f"[plan]   {'MKDIR'.ljust(8)} {'recipe'.ljust(12)} {dest}/")
    print("[plan]")
    print(f"[plan] To apply:  cf init recipe --apply {plan_id}")
    print(f"[plan] To review: cat {plans_dir}/<patch-file>.diff")
    return 0


def apply_plan(plan_id: str, store: Optional[str] = None, staging: bool = False) -> int:
    """Apply a previously generated plan by ID.

    Reads ``~/.codefreedom/plans/<plan_id>/plan.yaml`` and applies
    each file change.
    """
    cf_dir = get_codefreedom_dir()
    plans_dir = cf_dir / "plans" / plan_id
    plan_path = plans_dir / "plan.yaml"

    if not plan_path.exists():
        print(f"[apply] Plan '{plan_id}' not found at {plans_dir}")
        return 1

    try:
        plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        print(f"[apply] Invalid plan.yaml: {e}")
        return 1

    if not isinstance(plan, dict):
        print("[apply] Invalid plan format")
        return 1

    # ── 0. Auto-backup before applying ──────────────────────────────────
    # Full backup (no secret redaction) for rollback, tagged with plan ID.
    try:
        backup_path, _ = cf_backup(
            profile=f"pre-apply-{plan_id}",
            redact_secrets=False,
        )
        print(f"[apply] Backup: {backup_path}")
    except (FileNotFoundError, OSError, RuntimeError) as e:
        print(f"[apply] [WARN] Backup failed: {e}")
        print("[apply] Continuing without backup...")

    tool_home = Path.home() / ".codefreedom"
    print(f"[apply] Applying plan {plan_id}...")
    count = 0

    for pf in plan.get("files", []):
        target = pf.get("target", "")
        action = pf.get("action", "")
        content_name = pf.get("content_file")

        # Tool profiles always land in ~/.codefreedom/, everything else
        # respects CODEFREEDOM_HOME.
        if target in _TOOL_PROFILE_PATHS:
            dst = tool_home / target
        else:
            dst = cf_dir / target
        dst.parent.mkdir(parents=True, exist_ok=True)

        if action == "same":
            print(f"  [SAME]  {target}")
            continue

        if action == "delete":
            if dst.exists():
                dst.unlink()
                print(f"  [DELETE] {target}")
                count += 1
            else:
                print(f"  [SAME]  {target} (already gone)")
            continue

        if not content_name:
            # Fallback: extract from patch file (legacy plans)
            patch_name = pf.get("patch")
            if not patch_name:
                print(f"  [SKIP]  {target} (no content or patch file)")
                continue
            patch_file = plans_dir / patch_name
            if not patch_file.exists():
                print(f"  [SKIP]  {target} (patch file missing)")
                continue
            content = _extract_content_from_diff(patch_file.read_text(encoding="utf-8"))
        else:
            content_file = plans_dir / content_name
            if not content_file.exists():
                print(f"  [SKIP]  {target} (content file missing)")
                continue
            content = content_file.read_text(encoding="utf-8")

        dst.write_text(content, encoding="utf-8")
        label = "CREATE" if action == "create" else "REPLACE"
        print(f"  [{label}] {target}")
        count += 1

    # ── Create mountable directories ────────────────────────────────────
    dir_count = 0
    for rel_path in plan.get("dirs") or []:
        target = cf_dir / rel_path
        if target.is_dir():
            print(f"  [SAME]  {rel_path}/ (already exists)")
            continue
        target.mkdir(parents=True, exist_ok=True)
        print(f"  [MKDIR] {rel_path}/")
        dir_count += 1

    if dir_count:
        print(f"\n  Created {dir_count} mountable director(ies).")
        _print_ownership_advice()

    if count:
        print(f"\n[apply] Plan applied — {count} file(s) updated.")
    else:
        print("\n[apply] No files were changed.")
    return 0


def _generate_plan_id() -> str:
    """Generate a random 10-character alphanumeric plan ID."""
    import string

    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(10))


def _make_diff(
    existing: str, incoming: str, path: str, from_devnull: bool = False
) -> str:
    """Generate a unified diff between existing and incoming content.

    When *from_devnull* is ``True``, the diff shows the incoming content
    as a new file (``/dev/null`` → ``b/path``), matching ``git diff``
    style for new files.
    """
    import difflib

    existing_lines = existing.splitlines(keepends=True)
    incoming_lines = incoming.splitlines(keepends=True)
    timestamp = datetime.datetime.now().isoformat(timespec="seconds")

    fromfile = "/dev/null" if from_devnull else f"a/{path}"
    tofile = f"b/{path}"

    diff = difflib.unified_diff(
        existing_lines,
        incoming_lines,
        fromfile=fromfile,
        tofile=tofile,
        fromfiledate=timestamp,
        tofiledate=timestamp,
    )
    return "".join(diff)


def _extract_content_from_diff(diff: str) -> str:
    """Extract the resulting content from a unified diff.

    For a new-file diff (``/dev/null → b/path``), returns all lines
    that appear in the target. For standard diffs, returns the
    post-patch content.

    Handles unified diff format where:
    - ``+prefix`` → content added (strip ``+``)
    - `` prefix`` → context/unchanged (strip the leading space)
    - ``-prefix`` → content removed (skip)
    """
    lines: list[str] = []
    in_hunk = False
    for line in diff.splitlines(keepends=True):
        if line.startswith("@@"):
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith("-"):
            continue
        if line.startswith("+"):
            lines.append(line[1:])
        elif line.startswith(" "):
            # Context line: strip the leading space that difflib adds
            lines.append(line[1:])
    return "".join(lines)


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
                files = _read_local_files(recipe_dir, manifest)
                return manifest, files
            except RecipeError as e:
                eprint(f"  [WARN] Store recipe '{name}' has errors: {e}")
                return None, {}

    # 1. Try local submodule (dev installs with git clone) as fallback
    local_path = _find_local_recipe(name)
    if local_path is not None:
        manifest_path = local_path / "recipe.yaml"
        if manifest_path.exists():
            try:
                manifest = _parse_yaml_file(manifest_path)
                files = _read_local_files(local_path, manifest)
                return manifest, files
            except RecipeError as e:
                eprint(f"  [WARN] Local recipe '{name}' has errors: {e}")

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
    expanded = os.path.expanduser(store)
    if os.path.isabs(expanded) or store.startswith("."):
        p = Path(expanded)
        if p.is_dir():
            return p.resolve()
        eprint(f"  [WARN] Local store path does not exist or is not a directory: {p}")
        return None

    # ── GitHub URL ──────────────────────────────────────────────────────
    repo_name = _parse_github_url(store)
    if repo_name is None:
        eprint(f"  [WARN] Could not parse GitHub URL: {store}")
        return None

    cf_dir = get_codefreedom_dir()
    store_dir = cf_dir / "stores" / repo_name

    if _ensure_store(store, store_dir):
        return store_dir

    eprint(f"  [WARN] Failed to clone/pull store from {store}")
    return None


def _ensure_store(url: str, dest: Path, branch: str = "main") -> bool:
    """Clone a Git store fresh and remove metadata.

    Always re-clones to guarantee latest content — there is no local
    cache beyond the current invocation.  After a successful clone the
    ``.git/`` directory is removed so only recipe folder contents remain.
    """
    import shutil

    if dest.exists():
        shutil.rmtree(dest)
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
    import re

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
            print(f"  [STORE] Updating existing store at {dest} ({branch})")
            repo = Repo(dest)
            origin = repo.remotes.origin
            origin.pull(branch, ff_only=True)
            return True

        # ── Fresh clone with sparse checkout ──────────────────────────────
        print(f"  [STORE] Cloning {url} -> {dest} (branch: {branch})")
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
        eprint(f"  [WARN] Git operation failed: {e}")
        return False
    except Exception as e:
        eprint(f"  [WARN] Git operation failed: {e}")
        return False


def _remove_git_metadata(path: Path) -> None:
    """Remove all Git metadata from a directory tree.

    Deletes ``.git/``, ``.gitattributes``, ``.gitignore``, and
    ``.gitmodules`` recursively so only the recipe folder contents
    remain.
    """
    import shutil

    git_dir = path / ".git"
    if git_dir.is_dir():
        shutil.rmtree(git_dir, ignore_errors=True)

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


def _raw_url(recipe_name: str, path: str = "") -> str:
    """Build raw.githubusercontent.com URL for a recipe file."""
    parts = [_RAW_BASE, recipe_name]
    if path:
        parts.append(path)
    return "/".join(parts)


def _fetch_text(url: str, timeout: int = 15) -> str:
    """Fetch text content from a URL with a short timeout."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "codefreedom/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RecipeError(f"HTTP {e.code} fetching {url}") from e
    except urllib.error.URLError as e:
        raise RecipeError(f"URL error for {url}: {e.reason}") from e


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
            print(f"  [FETCH] {src_path}")
        except RecipeError as e:
            eprint(f"  [WARN] Could not fetch {src_path}: {e}")
    return files


def _fetch_available_recipes() -> List[str]:
    """List available recipes by checking each top-level dir for recipe.yaml."""
    try:
        url = f"{_GITHUB_API_BASE}/contents"
        raw = _fetch_text(url)
        items = json.loads(raw)
        candidates: List[str] = []
        for item in items:
            if item.get("type") == "dir":
                name = item["name"]
                if name.startswith("_"):
                    continue  # Skip private/base recipes
                try:
                    _fetch_text(_raw_url(name, "recipe.yaml"))
                    candidates.append(name)
                except RecipeError:
                    pass
        return sorted(candidates)
    except (RecipeError, json.JSONDecodeError) as e:
        eprint(f"  [WARN] Could not list recipes: {e}")
        return []


def _parse_yaml_file(path: Path) -> Dict[str, Any]:
    """Parse a local YAML file."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise RecipeError(f"{path.name} must be a mapping")
    return data


# ═══════════════════════════════════════════════════════════════════════════════
# File installation / merging
# ═══════════════════════════════════════════════════════════════════════════════


# Tool profile files always go to ~/.codefreedom/ (shared across projects).
# Uses the canonical set from docker_utils.


def _install_recipe_files(
    manifest: Dict[str, Any],
    files: Dict[str, str],
    cf_dir: Path,
) -> int:
    """Install or merge each recipe file into ``~/.codefreedom/``.

    Decision per file:
      - Target does **not** exist → create from recipe.
      - Target **does** exist → merge (DeepDiff for YAML/JSON,
        key-merge for .env, overwrite for everything else).

    Tool profiles (chrome.yaml, web.yaml, github.yaml) are always
    written to ``~/.codefreedom/`` regardless of ``CODEFREEDOM_HOME``.
    """
    # Interpolate ${VAR} references in manifest before validation
    interpolate_all_strings(manifest)

    # Validate manifest with Pydantic (non-fatal — warn on failure)
    try:
        RecipeConfig.model_validate(manifest, strict=False)
    except ValidationError as exc:
        eprint(f"  [WARN] Recipe validation issue: {exc}")

    tool_home = Path.home() / ".codefreedom"
    file_entries = manifest.get("files", [])
    count = 0

    for entry in file_entries:
        src_path = entry.get("path", "")
        target_path = entry.get("target", src_path)
        merge_mode = entry.get("merge", "auto")

        content = files.get(target_path) or files.get(src_path)
        if content is None:
            continue

        # Tool profiles always land in ~/.codefreedom/, everything else
        # respects CODEFREEDOM_HOME.
        if target_path in _TOOL_PROFILE_PATHS:
            dst = tool_home / target_path
        else:
            dst = cf_dir / target_path

        dst.parent.mkdir(parents=True, exist_ok=True)

        if dst.exists():
            new_count = _merge_file(dst, content, merge_mode, target_path)
        else:
            dst.write_text(content, encoding="utf-8")
            print(f"  [CREATE] {target_path}")
            new_count = 1

        count += new_count

    # ── Create mountable directories ────────────────────────────────────
    _create_recipe_dirs(manifest, cf_dir)

    if count:
        print(f"\n  Recipe applied — {count} file(s) created/updated.")
    else:
        print("\n  No files were changed.")

    return count


def _remove_orphans(
    managed_targets: set[str],
    cf_dir: Path,
) -> None:
    """Delete files that are not managed by the current recipe.

    Scans each directory that contains a managed file and deletes any
    sibling file that isn't in ``managed_targets``. This handles the
    common case of switching from one recipe to another where each
    recipe has its own provider config (e.g. ``opencode.yaml`` vs
    ``local.yaml`` in ``proxy/config/providers/``).

    Skips the root ``~/.codefreedom/`` directory to avoid deleting
    user-created files at the top level.
    """
    orphan_dirs: set[Path] = set()
    for target in managed_targets:
        parent = (cf_dir / target).parent
        if parent != cf_dir:
            orphan_dirs.add(parent)

    deleted = 0
    for parent_dir in sorted(orphan_dirs):
        if not parent_dir.is_dir():
            continue
        for child in sorted(parent_dir.iterdir()):
            if not child.is_file():
                continue
            rel = child.relative_to(cf_dir).as_posix()
            if rel not in managed_targets:
                child.unlink()
                print(f"  [DELETE] {rel}")
                deleted += 1

    if deleted:
        print(f"\n  Removed {deleted} orphaned file(s) from previous recipe.")
    else:
        print("\n  No orphaned files to clean up.")


def _create_recipe_dirs(
    manifest: Dict[str, Any],
    cf_dir: Path,
) -> None:
    """Create mountable directories declared in the recipe's ``dirs`` list.

    Directories are created under ``CODEFREEDOM_HOME`` (e.g.
    ``<cf_dir>/pg/data``, ``<cf_dir>/pg/backup``). These are typically
    host paths referenced by Docker volume mounts in compose files that
    need to exist before ``docker compose up`` runs so that a subsequent
    permission-fix command (e.g. ``chown 1000:1000``) can set the correct
    ownership before the container starts.
    """
    dirs = manifest.get("dirs")
    if not dirs:
        return

    created = 0
    for rel_path in dirs:
        target = cf_dir / rel_path
        if target.is_dir():
            print(f"  [SAME]  {rel_path}/ (already exists)")
            continue
        target.mkdir(parents=True, exist_ok=True)
        print(f"  [MKDIR] {rel_path}/")
        created += 1

    if created:
        print(f"\n  Created {created} mountable director(ies).")
        _print_ownership_advice()


def _print_ownership_advice() -> None:
    """Print cross-platform advice about Docker volume ownership.

    Linux and WSL share the host kernel, so files written by a container
    user with a different UID become owned by that numeric UID on the
    host.  macOS and native Windows (Docker Desktop) virtualise the
    filesystem layer and map ownership automatically.
    """
    import platform

    system = platform.system()
    cf_dir = get_codefreedom_dir()

    if system == "Linux":
        print(f"""
  ───────────────────────────────────────────────────────────────
  Linux/WSL permission tip
  ───────────────────────────────────────────────────────────────
  Docker on Linux shares the host kernel directly — file ownership
  uses numeric UIDs/GIDs.  If the container's internal user has a
  different UID (e.g. 1001) than your host user (e.g. 1000), files
  created by the container will be owned by UID 1001, and you'll
  get "Permission denied" when accessing them on the host.

  To fix, run:

      sudo chown -R $(id -u):$(id -g) {cf_dir}

  This re-assigns ownership of all CodeFreedom files to your
  current host user.  You only need to run it once (or after
  running Docker commands that create new files as root).

  macOS / Windows (Docker Desktop):
  Docker Desktop runs containers inside a lightweight VM with a
  virtualised filesystem layer, so file ownership is mapped
  transparently — no chown needed.
  ───────────────────────────────────────────────────────────────""")
    else:
        print("  (Ownership mapping is handled automatically on this platform.)")


def _merge_file(
    dst: Path,
    incoming_content: str,
    merge_mode: str,
    display_path: str,
) -> int:
    """Merge a single file that already exists in ``~/.codefreedom/``.

    Returns 1 if merged, 0 if skipped.
    """
    existing_content = dst.read_text(encoding="utf-8")

    # ── Decide merge strategy ───────────────────────────────────────────
    strategy = merge_mode
    if strategy == "auto":
        if display_path.endswith(".env") or ".env." in display_path:
            strategy = "env"
        elif _is_yaml_or_json(display_path):
            strategy = "deepdiff"
        else:
            strategy = "overwrite"

    # ── Apply ───────────────────────────────────────────────────────────
    if strategy == "deepdiff":
        merged = _deepdiff_merge(existing_content, incoming_content, display_path)
        if merged is None:
            print(f"  [SKIP]  {display_path} (auto-merge safe)")
            return 0
        dst.write_text(merged, encoding="utf-8")
        print(f"  [MERGE] {display_path}")
        return 1

    elif strategy == "env":
        merged = _merge_env(existing_content, incoming_content)
        if merged == existing_content:
            print(f"  [SAME]  {display_path}")
            return 0
        dst.write_text(merged, encoding="utf-8")
        print(f"  [MERGE] {display_path}")
        return 1

    else:  # overwrite
        dst.write_text(incoming_content, encoding="utf-8")
        print(f"  [UPDATE] {display_path}")
        return 1


def _is_yaml_or_json(path: str) -> bool:
    """Check if a path has a YAML or JSON extension."""
    ext = Path(path).suffix.lower()
    return ext in MERGEABLE_EXTENSIONS


# ═══════════════════════════════════════════════════════════════════════════════
# Merge engines
# ═══════════════════════════════════════════════════════════════════════════════


def _deepdiff_merge(
    existing: str,
    incoming: str,
    display_path: str = "",
) -> Optional[str]:
    """Structural YAML/JSON merge using DeepDiff analysis + safe recursive merge.

    How it works:
      1. Uses DeepDiff to compute the structural differences between
         the **existing** (current ``~/.codefreedom/``) and the **incoming**
         (recipe version).
      2. DeepDiff reveals *what* changed — new keys, updated values,
         deleted keys, type changes, etc.
      3. The actual merge applies incoming additions and updates on top
         of existing using a recursive dict merge — keys in existing
         that are NOT in incoming are **preserved** (no deletions).
      4. If both values are dicts, they're merged recursively.

    This gives you git-like semantics: the recipe is a diff overlay
    that can only add or update, never delete.

    Returns the merged YAML string, or ``None`` if the content is
    already identical (no merge needed).
    """
    try:
        from deepdiff import DeepDiff  # type: ignore
    except ImportError:
        eprint(
            "  [WARN] deepdiff not installed — falling back to overwrite "
            f"for {display_path}"
        )
        return incoming

    try:
        existing_obj = yaml.safe_load(existing)
        incoming_obj = yaml.safe_load(incoming)
    except yaml.YAMLError as e:
        eprint(f"  [WARN] YAML parse error in {display_path}: {e}")
        return incoming

    # Handle edge cases
    if existing_obj is None:
        return incoming
    if incoming_obj is None:
        return None  # Nothing to merge
    if existing_obj == incoming_obj:
        return None  # Already identical — skip

    # Compute diff for diagnostics (informational only)
    try:
        diff = DeepDiff(existing_obj, incoming_obj)
        if not diff:
            return None  # No structural changes
    except (TypeError, ValueError):
        pass  # Diff diagnostic is best-effort

    # Apply safe recursive merge (never deletes existing keys)
    merged = _recursive_merge(existing_obj, incoming_obj)

    # Preserve output format: if input was JSON, output as JSON
    stripped = existing.strip()
    if stripped and (stripped.startswith("{") or stripped.startswith("[")):
        return json.dumps(merged, indent=2) + "\n"

    return yaml.dump(merged, default_flow_style=False, sort_keys=False)


def _recursive_merge(existing: Any, incoming: Any) -> Any:
    """Recursive dict merge: applies incoming updates on top of existing.

    - Keys in existing that are **not** in incoming → preserved as-is.
    - Keys in incoming that are **not** in existing → added.
    - Keys present in BOTH:
        - If both values are dicts → recursively merged.
        - Otherwise → incoming value overwrites existing.
    - If either value is not a dict, the whole value is replaced.
    """
    if not isinstance(existing, dict) or not isinstance(incoming, dict):
        return incoming  # Non-dict values are fully replaced
    result = dict(existing)
    for key, in_val in incoming.items():
        if key in result and isinstance(result[key], dict) and isinstance(in_val, dict):
            result[key] = _recursive_merge(result[key], in_val)
        else:
            result[key] = in_val
    return result


def _merge_env(existing: str, incoming: str) -> str:
    """Key-by-key merge for .env-style files.

    Existing keys keep their values.  New keys from the recipe that
    don't exist in the current config are appended.

    For .secrets files, placeholder values (empty or "CHANGE_ME") are
    also kept — the user needs to fill them in manually.
    """
    existing_keys: Dict[str, str] = {}
    existing_lines = existing.splitlines()

    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, val = stripped.partition("=")
        existing_keys[key.strip()] = val.strip()

    # Parse incoming to find new keys and their order
    incoming_keys: Dict[str, Tuple[str, int]] = {}
    incoming_order: List[str] = []
    seen_keys: set = set()
    for i, line in enumerate(incoming.splitlines()):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, val = stripped.partition("=")
        k = key.strip()
        incoming_keys[k] = (val.strip(), i)
        if k not in seen_keys:
            seen_keys.add(k)
            incoming_order.append(k)

    # Find keys from incoming that don't exist in existing
    existing_key_set = set(existing_keys.keys())
    new_lines: List[str] = []

    # Re-build with incoming order for new keys
    for key in incoming_order:
        if key not in existing_key_set:
            val, _ = incoming_keys[key]
            new_lines.append(f"{key}={val}")

    if not new_lines:
        return existing  # No changes

    # Append new keys at the end
    merged = existing.rstrip("\n") + "\n" + "\n".join(new_lines) + "\n"
    return merged


# ═══════════════════════════════════════════════════════════════════════════════
# What's Next summary
# ═══════════════════════════════════════════════════════════════════════════════


def _ensure_user_env(cf_dir: Path) -> None:
    """Create ``.env.user`` if it doesn't exist.

    ``.env.user`` is a user-managed override file with the highest config
    priority — it is created once by the init flow and never touched by
    recipes again. Users put their personal overrides here (e.g. port
    changes, custom URLs). It is intentionally excluded from recipe
    file lists so recipes never create, merge, or update it.
    """
    user_env = cf_dir / ".env.user"
    if user_env.exists():
        return

    header = (
        "# ═══════════════════════════════════════════════════════════════════════════════\n"
        "# .env.user — User overrides (highest config priority)\n"
        "# ═══════════════════════════════════════════════════════════════════════════════\n"
        "#\n"
        "# This file is created once by `cf init recipe` and is NEVER touched by\n"
        "# recipes again. It has the highest precedence of any config file — values\n"
        "# here override .env.proxy, .env.claude, .env, .env.secrets, and all recipe\n"
        "# defaults. Only the host OS environment (exported vars) can override it.\n"
        "#\n"
        "# Use this file for your personal overrides, such as:\n"
        "#   LITELLM_PORT=4001\n"
        "#   LITELLM_MODEL_ALIAS_BEST=my-custom-model\n"
        "#\n"
        "# Syntax: standard KEY=value (no quotes needed, no spaces around =)\n"
        "# Supports ${VAR} and ${VAR:-default} interpolation.\n"
        "# ═══════════════════════════════════════════════════════════════════════════════\n"
    )
    user_env.write_text(header, encoding="utf-8")
    print("  [CREATE] .env.user (user-managed overrides)")


def _print_summary(manifest: Dict[str, Any], cf_dir: Path) -> None:
    """Print a post-install summary telling the user what to do next."""
    name = manifest.get("name", "unknown")
    description = manifest.get("description", "")

    required = manifest.get("required_secrets", [])
    optional = manifest.get("optional_config", [])

    print()
    print(f"  Recipe: {name}")
    if description:
        print(f"  {description}")
    print("  " + "─" * 55)

    # ── Generate a persistent RECIPE.md instruction file ────────────────
    _generate_recipe_instruction(manifest, cf_dir)

    if required:
        print("  REQUIRED — set these before starting:")
        for i, secret in enumerate(required, 1):
            var = secret.get("var", "?")
            prompt = secret.get("prompt", "")
            hint = secret.get("hint", "")
            line = f"    {i}. {var}"
            if prompt:
                line += f"  —  {prompt}"
            print(line)
            if hint:
                print(f"       {hint}")

    if optional:
        print()
        print("  OPTIONAL — already has defaults, override if needed:")
        for i, cfg in enumerate(optional, 1):
            var = cfg.get("var", "?")
            default = cfg.get("default", "")
            line = f"    {i}. {var}"
            if default:
                line += f"  (default: {default})"
            print(line)

    # Inherited from profile
    tools = manifest.get("tools_optional", [])
    if tools:
        print()
        print("  TOOLS available:")
        for t in tools:
            print(f"    - {t}  (start with: cf tools {t} start)")

    # Collect which .env.secrets files need editing
    env_secrets_files = _find_env_secrets_targets(manifest, cf_dir)

    print()
    print("  NEXT STEPS:")
    for env_file in env_secrets_files:
        print(f"    1. Edit {env_file} and add your API keys")
    if env_secrets_files:
        print("    2. Start the proxy:  cf proxy start")
        print("    3. Launch the agent: cf cc")
    else:
        print("    1. Start the proxy:  cf proxy start")
        print("    2. Launch the agent: cf cc")
    print("    4. Customize:         cf proxy start --port 4000")

    # ── Sandbox permissions ────────────────────────────────────────────
    cf_dir_str = str(cf_dir)
    print()
    print("  PERMISSIONS — Docker sandbox:")
    print("    Sandbox containers run with minimal permissions (no root).")
    print("    Grant ownership of the CodeFreedom data directory so the")
    print("    container can read and write config:")
    print()
    print(f"      sudo chown -R $(id -u):$(id -g) {cf_dir_str}")
    print()
    print("    5. Run the command above if you plan to use --sandbox mode")
    print("  " + "─" * 55)
    print()


def _generate_recipe_instruction(manifest: Dict[str, Any], cf_dir: Path) -> None:
    """Generate a persistent ``~/.codefreedom/RECIPE.md`` instruction file.

    This file records what recipe was installed, what files were created,
    what secrets are required, and what tools are available.  The doctor
    command (``cf doctor``) uses it as a reference for validation.
    """
    name = manifest.get("name", "unknown")
    description = manifest.get("description", "")
    required = manifest.get("required_secrets", [])
    optional = manifest.get("optional_config", [])
    tools = manifest.get("tools_optional", [])
    files = manifest.get("files", [])

    lines: list[str] = []
    lines.append(f"# CodeFreedom Recipe: {name}")
    lines.append("")
    if description:
        lines.append(f"> {description}")
        lines.append("")
    lines.append(f"Installed: {datetime.datetime.now().isoformat(timespec='seconds')}")
    lines.append("")

    if files:
        lines.append("## Files Installed")
        lines.append("")
        for entry in files:
            target = entry.get("target", entry.get("path", ""))
            lines.append(f"- `{target}`")
        lines.append("")

    if required:
        lines.append("## Required Secrets")
        lines.append("")
        for secret in required:
            var = secret.get("var", "?")
            prompt = secret.get("prompt", "")
            hint = secret.get("hint", "")
            default = secret.get("default", "")
            line = f"- `{var}`"
            if prompt:
                line += f" — {prompt}"
            if default:
                line += f" (default: {default})"
            lines.append(line)
            if hint:
                lines.append(f"  - {hint}")
        lines.append("")

    if optional:
        lines.append("## Optional Configuration")
        lines.append("")
        for cfg in optional:
            var = cfg.get("var", "?")
            default = cfg.get("default", "")
            line = f"- `{var}`"
            if default:
                line += f" (default: {default})"
            lines.append(line)
        lines.append("")

    if tools:
        lines.append("## Available Tools")
        lines.append("")
        for t in tools:
            lines.append(f"- `{t}` — start with: `cf tools {t} start`")
        lines.append("")

    lines.append("## Quick Start")
    lines.append("")
    env_secrets = _find_env_secrets_targets(manifest, cf_dir)
    if env_secrets:
        lines.append("1. Edit the `.secrets` files and add your API keys")
    lines.append("1. Start the proxy: `cf proxy start`")
    lines.append("2. Launch the agent: `cf cc`")
    lines.append("3. Run diagnostics: `cf doctor`")
    lines.append("")

    content = "\n".join(lines)
    instruction_path = cf_dir / "RECIPE.md"

    try:
        instruction_path.write_text(content, encoding="utf-8")
        print(f"  [INFO]  Instructions written to {instruction_path.name}")
    except OSError as e:
        print(f"  [WARN]  Could not write instructions: {e}")


def _find_env_secrets_targets(
    manifest: Dict[str, Any],
    cf_dir: Path,
) -> List[str]:
    """Find which .env.secrets files were created and need editing."""
    targets: List[str] = []
    for entry in manifest.get("files", []):
        target = entry.get("target", entry.get("path", ""))
        if ".secrets" in target:
            dst = cf_dir / target
            if dst.exists():
                try:
                    display_target = str(dst.relative_to(cf_dir))
                except ValueError:
                    display_target = dst.name
                targets.append(display_target)
    return targets
