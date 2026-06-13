"""Recipe plan generation and preview — list, init, plan, apply."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from codefreedom.cli.docker_utils import _TOOL_PROFILE_PATHS
from codefreedom.core.config import get_codefreedom_dir
from codefreedom.log import eprint, tag
from codefreedom.recipe.store import (
    _GITHUB_API_BASE,
    _fetch_available_recipes,
    _list_recipes_from_store,
    _resolve_recipe as _store_resolve_recipe,
    _resolve_store,
    RECIPE_OWNER,
    RECIPE_REPO,
)

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
        eprint(f"{tag('RECIPE')} No recipes found.")
        eprint(f"   {source}")
        return 1

    eprint(f"{tag('RECIPE')} Available recipes ({len(recipes)}):")
    for name in recipes:
        eprint(f"   {name}")
    eprint("")
    eprint("   Use:  cf s i -p <name>")
    source = store_path or f"https://github.com/{RECIPE_OWNER}/{RECIPE_REPO}"
    eprint(f"   Store: {source}")
    return 0


def init_recipe(name: str, store: Optional[str] = None, staging: bool = False) -> int:
    """Fetch and apply a recipe to ``~/.codefreedom/``.

    This is the main entry point for ``cf s i -p <name>``.

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
    from codefreedom.recipe.apply import (
        _install_recipe_files,
        _print_summary,
        _remove_orphans,
    )

    cf_dir = get_codefreedom_dir()

    # ── 1. Recipe source ────────────────────────────────────────────────
    branch = "staging" if staging else "main"
    store_path = _resolve_store(store, branch=branch)
    manifest, files = _store_resolve_recipe(name, store_path=store_path)
    if manifest is None:
        # Silently skip _default when not found in the store
        if name == "_default":
            source = store_path or f"https://github.com/{RECIPE_OWNER}/{RECIPE_REPO}"
            eprint(f"{tag('RECIPE')} No '_default' recipe in store — skipping.")
            eprint(f"   Store: {source}")
            return 0
        eprint(f"{tag('RECIPE')} Recipe '{name}' not found.")
        eprint("   Run 'cf s i -l' to see available recipes.")
        source = store_path or f"https://github.com/{RECIPE_OWNER}/{RECIPE_REPO}"
        eprint(f"   Store: {source}")
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
        eprint(f"{tag('RECIPE')} Installing base recipe '{extends}' first...")
        base_manifest, base_files = _store_resolve_recipe(
            extends, store_path=store_path
        )
        if base_manifest is None:
            eprint(
                f"[RECIPE] Warning: base recipe '{extends}' not found — continuing without it."
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
    from codefreedom.recipe.merge import _make_diff

    cf_dir = get_codefreedom_dir()

    # ── 1. Resolve recipe ──────────────────────────────────────────────
    branch = "staging" if staging else "main"
    store_path = _resolve_store(store, branch=branch)
    manifest, files = _store_resolve_recipe(name, store_path=store_path)
    if manifest is None:
        print(f"{tag('PLAN')} Recipe '{name}' not found.")
        print("       Run 'cf s i -l' to see available recipes.")
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
        base_man, base_files = _store_resolve_recipe(extends, store_path=store_path)
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
    print(f"{tag('PLAN')} Recipe: {name}" + (f" (extends {extends})" if extends else ""))
    print(f"{tag('PLAN')} Plan ID: {plan_id}")
    print(f"{tag('PLAN')} Files:   {plans_dir}/")
    print(f"{tag('PLAN')}")
    print(f"{tag('PLAN')}   {summary['create']} new files")
    print(f"{tag('PLAN')}   {summary['replace']} files to replace")
    print(f"{tag('PLAN')}   {summary['same']} unchanged (skipped)")
    if delete_count:
        print(f"{tag('PLAN')}   {delete_count} files to delete")
    dir_count = len(plan_dirs)
    if dir_count:
        print(f"{tag('PLAN')}   {dir_count} directories to create")
    print(f"{tag('PLAN')}")
    print(f"{tag('PLAN')}   {'':>8} {'SOURCE':12} DESTINATION")
    print(f"{tag('PLAN')}   {'-'*8} {'-'*12} {'-'*75}")
    for pf in patch_files:
        action = pf["action"].upper().ljust(8)
        src_label = pf["source"][:12].ljust(12)
        target = pf["target"]
        if target in _TOOL_PROFILE_PATHS:
            dest = tool_home / target
        else:
            dest = cf_dir / target
        print(f"{tag('PLAN')}   {action} {src_label} {dest}")
    for d in plan_dirs:
        dest = cf_dir / d
        print(f"{tag('PLAN')}   {'MKDIR'.ljust(8)} {'recipe'.ljust(12)} {dest}/")
    print(f"{tag('PLAN')}")
    print(f"{tag('PLAN')} To apply:  cf s i -a {plan_id}")
    print(f"{tag('PLAN')} Quick:     cf s i -pa {name}")
    print(f"{tag('PLAN')} To review: cat {plans_dir}/<patch-file>.diff")
    return 0


def plan_and_apply_recipe(
    name: str, store: Optional[str] = None, staging: bool = False
) -> int:
    """Plan a recipe, show the preview, then apply after user confirmation.

    This is the ``cf setup init --plan-and-apply <name>`` (or ``-pa <name>``)
    workflow — a single command that replaces the two-step plan + apply.
    """
    rc = plan_recipe(name, store=store, staging=staging)
    if rc != 0:
        return rc

    try:
        answer = input(f"\n{tag('RECIPE')} Apply this plan? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        eprint(f"\n{tag('RECIPE')} Cancelled.")
        return 1

    if answer not in ("y", "yes"):
        eprint(f"{tag('RECIPE')} Aborted.")
        return 1

    return init_recipe(name, store=store, staging=staging)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _generate_plan_id() -> str:
    """Generate a random 10-character alphanumeric plan ID."""
    import string

    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(10))


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
        "# This file is created once by `cf s i` and is NEVER touched by\n"
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
  -------------------------------------------------------------
  Linux/WSL permission tip
  -------------------------------------------------------------
  Docker on Linux shares the host kernel directly -- file ownership
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
  transparently -- no chown needed.
  -------------------------------------------------------------""")
    else:
        print("  (Ownership mapping is handled automatically on this platform.)")


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
