"""Recipe plan application — install, merge, orphan cleanup, summary."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Dict

import yaml

from codefreedom.admin import backup as cf_backup
from codefreedom.cli.docker_utils import _TOOL_PROFILE_PATHS
from codefreedom.config import get_codefreedom_dir
from codefreedom.interpolate import interpolate_all_strings
from codefreedom.log import eprint
from codefreedom.schemas.recipe import RecipeConfig
from pydantic import ValidationError


def apply_plan(plan_id: str) -> int:
    """Apply a previously generated plan by ID.

    Reads ``~/.codefreedom/plans/<plan_id>/plan.yaml`` and applies
    each file change.
    """
    from codefreedom.recipe.merge import _extract_content_from_diff

    cf_dir = get_codefreedom_dir()
    plans_dir = cf_dir / "plans" / plan_id
    plan_path = plans_dir / "plan.yaml"

    if not plan_path.exists():
        eprint(f"[RECIPE] Plan '{plan_id}' not found at {plans_dir}")
        return 1

    try:
        plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        eprint(f"[RECIPE] Invalid plan.yaml: {e}")
        return 1

    if not isinstance(plan, dict):
        print("[RECIPE] Invalid plan format")
        return 1

    # ── 0. Auto-backup before applying ──────────────────────────────────
    # Full backup (no secret redaction) for rollback, tagged with plan ID.
    try:
        backup_path, _ = cf_backup(
            profile=f"pre-apply-{plan_id}",
            redact_secrets=False,
        )
        eprint(f"[RECIPE] Backup: {backup_path}")
    except (FileNotFoundError, OSError, RuntimeError) as e:
        eprint(f"[RECIPE] Warning: Backup failed: {e}")
        print("[RECIPE] Continuing without backup...")

    tool_home = Path.home() / ".codefreedom"
    eprint(f"[RECIPE] Applying plan {plan_id}...")
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
    from codefreedom.recipe.plan import _print_ownership_advice

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
        print(f"\n[RECIPE] Plan applied — {count} file(s) updated.")
    else:
        print("\n[RECIPE] No files were changed.")
    return 0


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
    from codefreedom.recipe.merge import _merge_file

    # Interpolate ${VAR} references in manifest before validation
    interpolate_all_strings(manifest)

    # Validate manifest with Pydantic (non-fatal — warn on failure)
    try:
        RecipeConfig.model_validate(manifest, strict=False)
    except ValidationError as exc:
        eprint(f"[RECIPE] Warning: Recipe validation issue: {exc}")

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
    from codefreedom.recipe.plan import _create_recipe_dirs

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


def _print_summary(manifest: Dict[str, Any], cf_dir: Path) -> None:
    """Print a post-install summary telling the user what to do next."""
    from codefreedom.recipe.plan import _find_env_secrets_targets

    name = manifest.get("name", "unknown")
    description = manifest.get("description", "")

    required = manifest.get("required_secrets", [])
    optional = manifest.get("optional_config", [])

    print()
    print(f"  Recipe: {name}")
    if description:
        print(f"  {description}")
    print("  " + "-" * 55)

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
    print("  " + "-" * 55)
    print()


def _generate_recipe_instruction(manifest: Dict[str, Any], cf_dir: Path) -> None:
    """Generate a persistent ``~/.codefreedom/RECIPE.md`` instruction file.

    This file records what recipe was installed, what files were created,
    and what tools are available. The doctor command (``cf doctor``) uses
    it as a reference for validation. Secret-related information is shown
    only on stdout — never written to disk.
    """
    name = manifest.get("name", "unknown")
    description = manifest.get("description", "")
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

    if tools:
        lines.append("## Available Tools")
        lines.append("")
        for t in tools:
            lines.append(f"- `{t}` — start with: `cf tools {t} start`")
        lines.append("")

    lines.append("## Quick Start")
    lines.append("")
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
        eprint(f"[RECIPE] Warning: Could not write instructions: {e}")
