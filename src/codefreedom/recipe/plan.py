"""Recipe plan generation and preview — list, init, plan, apply."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from codefreedom.core.config import get_codefreedom_dir, get_config_dir
from codefreedom.log import eprint, tag
from codefreedom.recipe.materialize import materialize_recipe
from codefreedom.recipe.store import (
    _fetch_available_recipes,
    _github_api_base,
    _list_recipes_from_store,
    _resolve_recipe as _store_resolve_recipe,
    _resolve_recipe_branch,
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
    branch = _resolve_recipe_branch() if not staging else "staging"
    store_path = _resolve_store(store, branch=branch)

    if store_path:
        recipes = _list_recipes_from_store(store_path)
    else:
        recipes = _fetch_available_recipes(branch)

    if not recipes:
        source = store_path or _github_api_base(branch)
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


def init_recipe(
    name: str,
    store: Optional[str] = None,
    staging: bool = False,
    folder: Optional[str] = None,
) -> int:
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
      5. Print a "What's Next" summary with required secrets and next steps.
      6. If ``folder`` is set, write a copy of ``override.yaml`` to
         ``<folder>/.cf.yaml`` (the per-folder override layer).

    Secrets are sourced exclusively from ``CF_CLI_*`` machine environment
    variables — no ``.env`` files are created or read by the recipe flow.
    """
    from codefreedom.recipe.apply import (
        _install_recipe_files,
        _print_summary,
        _remove_orphans,
    )

    cf_dir = get_codefreedom_dir()
    config_dir = get_config_dir()

    # ── 1. Recipe source ────────────────────────────────────────────────
    branch = _resolve_recipe_branch() if not staging else "staging"
    store_path = _resolve_store(store, branch=branch)
    manifest, files = _store_resolve_recipe(name, store_path=store_path)
    if manifest is None:
        eprint(f"{tag('RECIPE')} Recipe '{name}' not found.")
        eprint("   Run 'cf s i -l' to see available recipes.")
        source = store_path or f"https://github.com/{RECIPE_OWNER}/{RECIPE_REPO}"
        eprint(f"   Store: {source}")
        return 1

    vars_dict = _load_recipe_vars(manifest)

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
            _install_recipe_files(
                base_manifest, base_files, cf_dir, vars_dict=vars_dict
            )

    # ── 2. Install / merge each file ─────────────────────────────────────
    _collect_targets(manifest)

    # ── 2a. Copy recipe manifest to config for reference by scripts ─────
    _copy_recipe_manifest(_manifest_with_inherited_vars(manifest, store_path), config_dir)

    has_generated = bool(manifest.get("generated_artifacts"))
    if has_generated:
        result = materialize_recipe(manifest, files)
        static_entries = [e for e in result["entries"] if e["type"] == "static"]
        generated_entries = [e for e in result["entries"] if e["type"] == "generated"]

        rebuilt_files: list[dict[str, Any]] = []
        for e in static_entries:
            entry: dict[str, Any] = {
                "path": e.get("path", e["target"]),
                "target": e["target"],
                "merge": e["merge"],
            }
            if e.get("split_by_key"):
                entry["split_by_key"] = e["split_by_key"]
            if e.get("copy_dir"):
                entry["copy_dir"] = e["copy_dir"]
            rebuilt_files.append(entry)

        static_manifest = {**manifest, "files": rebuilt_files}
        static_files: dict[str, str] = {}
        for e in static_entries:
            if e.get("copy_dir"):
                # For copy_dir entries, include all individual files from
                # the original files dict that fall under this directory.
                src_dir = (e.get("path") or e["target"]).rstrip("/")
                for fk, fv in files.items():
                    if fk.startswith(src_dir + "/") or fk == src_dir:
                        static_files[fk] = fv
            else:
                static_files[e["target"]] = e["content"]
        _install_recipe_files(
            static_manifest, static_files, cf_dir, vars_dict=vars_dict
        )

        for entry in generated_entries:
            dst = config_dir / entry["target"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(entry["content"], encoding="utf-8")
            if dst.suffix == ".sh":
                import stat

                dst.chmod(
                    dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                )
            print(f"  {tag('CREATE')} {entry['target']} (generated)")
            all_managed.add(entry["target"])
    else:
        _install_recipe_files(manifest, files, cf_dir, vars_dict=vars_dict)

    # ── 2b. Orphan detection — delete files from previous recipe(s) ────
    # Exclude recipe.yaml and override.yaml from orphan scan
    all_managed.add("recipe.yaml")
    all_managed.add("override.yaml")
    _remove_orphans(all_managed, config_dir)

    # ── 2c. Ensure override.yaml exists (user-managed overrides file) ──
    _ensure_override_yaml(config_dir)

    # ── 2d. Optional: write .cf.yaml to a local folder for per-folder overrides
    if folder:
        _write_cf_yaml(config_dir, folder)

    # ── 3. What's Next summary ──────────────────────────────────────────
    _print_summary(manifest, config_dir)
    return 0


def _collect_recipe_files(
    man: dict, fdict: dict, source_label: str, vars_dict: dict[str, str]
) -> list[dict]:
    """Collect plan entries from a single manifest's file list.

    Handles copy_dir, split_by_key, and variable interpolation.
    Returns a list of plan-entry dicts.
    """
    import os
    import re

    entries: list[dict] = []

    for entry in man.get("files", []):
        src = entry.get("path", "")
        target = entry.get("target", src)
        split_key = entry.get("split_by_key")
        copy_dir = entry.get("copy_dir", False)

        if copy_dir:
            src_dir = src.rstrip("/")
            prefix = src_dir + "/"
            for file_key, file_content in fdict.items():
                if not (file_key.startswith(prefix) or file_key == src_dir):
                    continue
                rel_path = (
                    file_key[len(src_dir) + 1 :]
                    if file_key.startswith(prefix)
                    else file_key
                )
                if not rel_path:
                    continue
                if target.endswith("/"):
                    individual_target = f"{target}{rel_path}"
                else:
                    individual_target = f"{target}/{rel_path}"
                entries.append(
                    {
                        "target": individual_target,
                        "content": file_content,
                        "merge": entry.get("merge", "auto"),
                        "source": source_label,
                    }
                )
            continue

        content = fdict.get(target) or fdict.get(src)
        if content is None:
            continue

        if split_key:
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                continue

            common = data.get("common", {})
            section = data.get(split_key, {})

            for name, profile_data in section.items():
                merged = {**common, **profile_data}
                merged_content = yaml.dump(
                    merged, default_flow_style=False, sort_keys=False
                )

                if target.endswith("/"):
                    individual_target = f"{target}{name}.yaml"
                else:
                    individual_target = f"{target}/{name}.yaml"

                entries.append(
                    {
                        "target": individual_target,
                        "content": merged_content,
                        "merge": entry.get("merge", "auto"),
                        "source": source_label,
                    }
                )
            continue

        if vars_dict:
            def _replace_var(match: re.Match) -> str:
                var_name = match.group(1)
                has_default = match.group(2) is not None
                default = str(match.group(2)) if has_default else ""
                if var_name in vars_dict:
                    return vars_dict[var_name]
                if var_name in os.environ:
                    return os.environ[var_name]
                if has_default:
                    return default
                return str(match.group(0))

            content = re.sub(r"\$\{(\w+)(?::-(.*))?\}", _replace_var, content)

        entries.append(
            {
                "target": target,
                "content": content,
                "merge": entry.get("merge", "auto"),
                "source": source_label,
            }
        )

    return entries


def _compute_plan_entries(
    manifest: dict,
    files: dict,
    name: str,
    store_path: Path | None,
    vars_dict: dict[str, str],
) -> list[dict]:
    """Resolve extends chain, collect entries, add generated artifacts, deduplicate."""
    extends = manifest.get("extends")
    plan_entries: list[dict] = []

    if extends:
        base_man, base_files = _store_resolve_recipe(extends, store_path=store_path)
        if base_man is not None:
            plan_entries.extend(
                _collect_recipe_files(base_man, base_files, extends, vars_dict)
            )

    plan_entries.extend(
        _collect_recipe_files(manifest, files, name, vars_dict)
    )

    has_generated = bool(manifest.get("generated_artifacts"))
    if has_generated:
        result = materialize_recipe(manifest, files)
        for entry in result["entries"]:
            if entry["type"] == "generated":
                plan_entries.append(
                    {
                        "target": entry["target"],
                        "content": entry["content"],
                        "merge": "overwrite",
                        "source": f"{name} (generated)",
                    }
                )

    seen: dict[str, dict] = {}
    for entry in plan_entries:
        seen[entry["target"]] = entry
    return list(seen.values())


def _compute_file_changes(
    plan_entries: list[dict], config_dir: Path, plans_dir: Path
) -> tuple[dict[str, int], list[dict]]:
    """Compute create/replace/same for each entry and write patch files."""
    from codefreedom.recipe.merge import _make_diff

    summary: dict[str, int] = {"create": 0, "replace": 0, "same": 0}
    patch_files: list[dict] = []

    for entry in plan_entries:
        dst = config_dir / entry["target"]
        dst.parent.mkdir(parents=True, exist_ok=True)

        if not dst.exists():
            diff = _make_diff("", entry["content"], entry["target"], from_devnull=True)
            safe_name = entry["target"].replace("/", "-").replace("\\", "-")
            patch_name = f"create-{safe_name}.diff"
            (plans_dir / patch_name).write_text(diff, encoding="utf-8")
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

        diff = _make_diff(existing, entry["content"], entry["target"])
        safe_name = entry["target"].replace("/", "-").replace("\\", "-")
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

    return summary, patch_files


def _detect_orphan_files(
    plan_entries: list[dict],
    patch_files: list[dict],
    summary: dict[str, int],
    config_dir: Path,
) -> tuple[dict[str, int], list[dict]]:
    """Detect files from previous recipe that aren't in the new recipe."""
    managed_targets = {e["target"] for e in plan_entries}
    orphan_dirs: set[Path] = set()
    for e in plan_entries:
        parent = (config_dir / e["target"]).parent
        if parent != config_dir:
            orphan_dirs.add(parent)

    for parent_dir in sorted(orphan_dirs):
        if not parent_dir.is_dir():
            continue
        for child in sorted(parent_dir.iterdir()):
            if not child.is_file():
                continue
            rel = child.relative_to(config_dir).as_posix()
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

    return summary, patch_files


def _write_plan_and_print(
    plan_id: str,
    name: str,
    extends: str | None,
    summary: dict[str, int],
    plan_dirs: list[str],
    patch_files: list[dict],
    plans_dir: Path,
    config_dir: Path,
) -> int:
    """Write plan.yaml and print the human-readable summary."""
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

    delete_count = summary.get("delete", 0)
    print(
        f"{tag('PLAN')} Recipe: {name}" + (f" (extends {extends})" if extends else "")
    )
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
        dest = config_dir / target
        print(f"{tag('PLAN')}   {action} {src_label} {dest}")
    for d in plan_dirs:
        dest = config_dir / d
        print(f"{tag('PLAN')}   {'MKDIR'.ljust(8)} {'recipe'.ljust(12)} {dest}/")
    print(f"{tag('PLAN')}")
    print(f"{tag('PLAN')} To apply:  cf s i -a {plan_id}")
    print(f"{tag('PLAN')} Quick:     cf s i -pa {name}")
    print(f"{tag('PLAN')} To review: cat {plans_dir}/<patch-file>.diff")
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
    branch = _resolve_recipe_branch() if not staging else "staging"
    store_path = _resolve_store(store, branch=branch)
    manifest, files = _store_resolve_recipe(name, store_path=store_path)
    if manifest is None:
        print(f"{tag('PLAN')} Recipe '{name}' not found.")
        print("       Run 'cf s i -l' to see available recipes.")
        return 1

    vars_dict = _load_recipe_vars(manifest)

    # ── 2. Collect plan entries from extends chain ─────────────────────
    plan_entries = _compute_plan_entries(manifest, files, name, store_path, vars_dict)

    # ── 3. Compute file changes ────────────────────────────────────────
    plan_id = _generate_plan_id()
    config_dir = get_config_dir()
    plans_dir = cf_dir / "plans" / plan_id
    plans_dir.mkdir(parents=True, exist_ok=True)

    summary, patch_files = _compute_file_changes(plan_entries, config_dir, plans_dir)

    # ── 4. Orphan detection ────────────────────────────────────────────
    summary, patch_files = _detect_orphan_files(
        plan_entries, patch_files, summary, config_dir
    )

    # ── 5. Collect dirs + write plan + print ───────────────────────────
    plan_dirs: list[str] = []
    extends = manifest.get("extends")
    if extends:
        base_man, _ = _store_resolve_recipe(extends, store_path=store_path)
        if base_man is not None:
            for d in base_man.get("dirs") or []:
                if d not in plan_dirs:
                    plan_dirs.append(d)
    for d in manifest.get("dirs") or []:
        if d not in plan_dirs:
            plan_dirs.append(d)

    return _write_plan_and_print(
        plan_id, name, extends, summary, plan_dirs, patch_files, plans_dir, config_dir
    )


def plan_and_apply_recipe(
    name: str,
    store: Optional[str] = None,
    staging: bool = False,
    folder: Optional[str] = None,
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

    return init_recipe(name, store=store, staging=staging, folder=folder)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _generate_plan_id() -> str:
    """Generate a random 10-character alphanumeric plan ID."""
    import string

    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(10))


def _load_recipe_vars(manifest: Dict[str, Any]) -> Dict[str, str]:
    """Load vars from the recipe manifest.

    The ``vars`` field can be either:
    - A **string** — path to a YAML file relative to the recipe directory.
    - A **dict** — inline key/value variables used directly.
    """
    raw = manifest.get("vars")
    if not raw:
        return {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    recipe_dir = manifest.get("_recipe_dir")
    if not recipe_dir:
        return {}
    vars_path = Path(recipe_dir) / raw
    if not vars_path.exists():
        return {}
    with open(vars_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _copy_recipe_manifest(manifest: Dict[str, Any], config_dir: Path) -> None:
    """Copy the recipe manifest to the config directory for reference.

    Saves a clean copy of the recipe manifest (without internal keys like
    ``_recipe_dir``) as ``recipe.yaml`` in the config directory.  Scripts
    and other components can read ``required_secrets``, ``vars``, and other
    metadata from this canonical location.
    """
    clean = {k: v for k, v in manifest.items() if not k.startswith("_")}
    dst = config_dir / "recipe.yaml"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(
        yaml.dump(clean, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def _manifest_with_inherited_vars(
    manifest: Dict[str, Any], store_path: Path | None
) -> Dict[str, Any]:
    """Return manifest with vars merged from its extends chain."""
    merged = dict(manifest)
    vars_dict: dict[str, Any] = {}
    extends = manifest.get("extends")
    if extends:
        base_manifest, _ = _store_resolve_recipe(extends, store_path=store_path)
        if base_manifest is not None:
            inherited = _manifest_with_inherited_vars(base_manifest, store_path)
            raw_vars = inherited.get("vars")
            if isinstance(raw_vars, dict):
                vars_dict.update(raw_vars)
    raw_vars = manifest.get("vars")
    if isinstance(raw_vars, dict):
        vars_dict.update(raw_vars)
    if vars_dict:
        merged["vars"] = vars_dict
    return merged


def _ensure_override_yaml(cf_dir: Path) -> None:
    """Create ``override.yaml`` in config directory if it doesn't exist.

    ``override.yaml`` is a user-managed override file with the highest config
    priority — it is created once by the init flow and never touched by
    recipes again. Users put their personal overrides here to override values
    from ``profiles.yaml``. It is intentionally excluded from recipe
    file lists so recipes never create, merge, or update it.

    The override.yaml mirrors the structure of profiles.yaml, allowing users
    to override specific values. It also contains special variables like
    SUFFIX_ID, POSTGRES_HOST_PORT, etc.
    """
    import yaml

    from codefreedom.core.config import get_config_dir

    config_dir = get_config_dir()
    override_path = config_dir / "override.yaml"
    if override_path.exists():
        return

    # Ensure config directory exists
    config_dir.mkdir(parents=True, exist_ok=True)

    # Sample override.yaml content
    override_content = {
        "comment": "User overrides — values here override profiles.yaml",
        "vars": {
            "SUFFIX_ID": "0000",
            "POSTGRES_HOST_PORT": "5433",
        },
        "profiles": {
            "default": {
                "env": {},
            },
        },
        "tools": {
            "chrome": {},
            "web": {},
            "github": {},
            "web-bridge": {},
            "git": {},
        },
    }

    with open(override_path, "w", encoding="utf-8") as f:
        yaml.dump(override_content, f, default_flow_style=False, sort_keys=False)

    print("  [CREATE] override.yaml (user-managed overrides)")


def _write_cf_yaml(cf_dir: Path, folder: Optional[str]) -> None:
    """Copy ``override.yaml`` to ``<folder>/.cf.yaml`` for per-folder overrides.

    ``.cf.yaml`` is the highest-precedence YAML layer in the config chain
    (above ``override.yaml``, below ``CF_CLI_*`` machine env). It lets users
    pin folder-specific overrides — e.g. a different ``SUFFIX_ID`` for an
    experiment — without editing the global config.

    The path is explicit: no auto-discovery. Callers must opt in via the
    ``CF_CLI_CF_YAML`` env var, the ``cf_yaml_path`` arg to
    :func:`codefreedom.config.load_config`, or by running
    ``cf setup init -f <folder>`` (which writes the file).

    Behavior:
      - ``folder`` is ``None`` or empty → no-op.
      - Relative paths are resolved against :data:`os.getcwd`.
      - The target folder is created if missing.
      - If ``<folder>/.cf.yaml`` already exists → leave it alone, emit a
        warning, return.
      - If ``override.yaml`` is missing in ``cf_dir`` → silent no-op (the
        user has nothing to copy yet).
    """
    if not folder:
        return

    override_path = cf_dir / "override.yaml"
    if not override_path.exists():
        return

    target_dir = Path(folder).expanduser()
    if not target_dir.is_absolute():
        target_dir = Path.cwd() / target_dir
    target_file = target_dir / ".cf.yaml"

    if target_file.exists():
        eprint(
            f"{tag('WARN')} .cf.yaml already exists at {target_file}; "
            "skipping copy to preserve user edits."
        )
        return

    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
        print(f"  {tag('MKDIR')} {target_file.parent}/")

    content = override_path.read_text(encoding="utf-8")
    target_file.write_text(content, encoding="utf-8")
    print(f"  {tag('CREATE')} {target_file} (folder-specific override)")
    print(
        f"   {tag('INFO')} Set CF_CLI_CF_YAML={target_file} or pass it as "
        "cf_yaml_path to load_config() to activate."
    )


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



