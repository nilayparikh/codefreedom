"""Recipe plan application — install, merge, orphan cleanup, summary."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from codefreedom.admin import backup as cf_backup
from codefreedom.cli.docker_utils import _TOOL_PROFILE_PATHS
from codefreedom.core.config import get_codefreedom_dir
from codefreedom.core.interpolate import interpolate_all_strings
from codefreedom.core.settings import resolve_config_value
from codefreedom.log import dim, eprint, green, red, tag, yellow
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
        eprint(f"{tag('RECIPE')} Plan '{plan_id}' not found at {plans_dir}")
        return 1

    try:
        plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        eprint(f"{tag('RECIPE')} Invalid plan.yaml: {e}")
        return 1

    if not isinstance(plan, dict):
        print(f"{tag('RECIPE')} Invalid plan format")
        return 1

    # ── 0. Auto-backup before applying ──────────────────────────────────
    # Full backup (no secret redaction) for rollback, tagged with plan ID.
    try:
        backup_path, _ = cf_backup(
            profile=f"pre-apply-{plan_id}",
            redact_secrets=False,
        )
        eprint(f"{tag('RECIPE')} Backup: {backup_path}")
    except (FileNotFoundError, OSError, RuntimeError) as e:
        eprint(f"{tag('RECIPE')} Warning: Backup failed: {e}")
        print(f"{tag('RECIPE')} Continuing without backup...")

    tool_home = Path.home() / ".codefreedom"
    eprint(f"{tag('RECIPE')} Applying plan {plan_id}...")
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
            print(f"  {tag('SAME')}  {target}")
            continue

        if action == "delete":
            if dst.exists():
                dst.unlink()
                print(f"  {tag('DELETE')} {target}")
                count += 1
            else:
                print(f"  {tag('SAME')}  {target} (already gone)")
            continue

        if not content_name:
            # Fallback: extract from patch file (legacy plans)
            patch_name = pf.get("patch")
            if not patch_name:
                print(f"  {tag('SKIP')}  {target} (no content or patch file)")
                continue
            patch_file = plans_dir / patch_name
            if not patch_file.exists():
                print(f"  {tag('SKIP')}  {target} (patch file missing)")
                continue
            content = _extract_content_from_diff(patch_file.read_text(encoding="utf-8"))
        else:
            content_file = plans_dir / content_name
            if not content_file.exists():
                print(f"  {tag('SKIP')}  {target} (content file missing)")
                continue
            content = content_file.read_text(encoding="utf-8")

        if dst.suffix == ".ps1":
            dst.write_text(content, encoding="utf-8")
        else:
            dst.write_text(content, encoding="utf-8")
        if dst.suffix == ".sh":
            import stat

            dst.chmod(dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        label = "CREATE" if action == "create" else "REPLACE"
        print(f"  [{label}] {target}")
        count += 1

    # ── Create mountable directories ────────────────────────────────────
    from codefreedom.recipe.plan import _print_ownership_advice

    dir_count = 0
    for rel_path in plan.get("dirs") or []:
        target = cf_dir / rel_path
        if target.is_dir():
            print(f"  {tag('SAME')}  {rel_path}/ (already exists)")
            continue
        target.mkdir(parents=True, exist_ok=True)
        print(f"  {tag('MKDIR')} {rel_path}/")
        dir_count += 1

    if dir_count:
        print(f"\n  Created {dir_count} mountable director(ies).")
        _print_ownership_advice()

    if count:
        print(f"\n{tag('RECIPE')} Plan applied — {count} file(s) updated.")
    else:
        print(f"\n{tag('RECIPE')} No files were changed.")
    return 0


def _install_recipe_files(
    manifest: Dict[str, Any],
    files: Dict[str, str],
    cf_dir: Path,
    vars_dict: Optional[Dict[str, str]] = None,
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
        validation_data = {k: v for k, v in manifest.items() if k != "_recipe_dir"}
        RecipeConfig.model_validate(validation_data, strict=False)
    except ValidationError as exc:
        eprint(f"{tag('RECIPE')} Warning: Recipe validation issue: {exc}")

    tool_home = Path.home() / ".codefreedom"
    file_entries = manifest.get("files", [])
    count = 0

    for entry in file_entries:
        src_path = entry.get("path", "")
        target_path = entry.get("target", src_path)
        merge_mode = entry.get("merge", "auto")
        split_key = entry.get("split_by_key")
        copy_dir = entry.get("copy_dir", False)

        if copy_dir:
            # Copy entire directory recursively

            # Find the source directory
            src_dir = None
            for key in files:
                if key.startswith(src_path) or key == src_path.rstrip("/"):
                    # This is a directory entry - files dict has all files under this path
                    src_dir = src_path.rstrip("/")
                    break

            if src_dir is None:
                continue

            # Get all files under this directory from the files dict
            dir_files = {k: v for k, v in files.items() if k.startswith(src_dir + "/") or k.startswith(src_dir)}

            for file_key, file_content in dir_files.items():
                # Calculate relative path
                if file_key.startswith(src_dir + "/"):
                    rel_path = file_key[len(src_dir) + 1 :]
                else:
                    rel_path = file_key

                if not rel_path:
                    continue

                if target_path.endswith("/"):
                    dst = cf_dir / target_path / rel_path
                else:
                    dst = cf_dir / target_path / rel_path

                dst.parent.mkdir(parents=True, exist_ok=True)

                if vars_dict:
                    import os
                    import re

                    def _replace_var(match: re.Match) -> str:
                        var_name = match.group(1)
                        default = match.group(2) if match.group(2) is not None else ""
                        return vars_dict.get(var_name, os.environ.get(var_name, default))

                    file_content = re.sub(r"\$\{(\w+)(?::-(.*))?\}", _replace_var, file_content)

                if dst.exists():
                    new_count = _merge_file(dst, file_content, merge_mode, str(dst.relative_to(cf_dir)))
                else:
                    dst.write_text(file_content, encoding="utf-8")
                    if dst.suffix == ".sh":
                        import stat
                        dst.chmod(dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                    print(f"  {tag('CREATE')} {dst.relative_to(cf_dir)}")
                    new_count = 1

                count += new_count
            continue

        content = files.get(target_path) or files.get(src_path)
        if content is None:
            continue

        if vars_dict:
            import os
            import re

            def _replace_var(match: re.Match) -> str:
                var_name = match.group(1)
                default = match.group(2) if match.group(2) is not None else ""
                return vars_dict.get(var_name, os.environ.get(var_name, default))

            content = re.sub(r"\$\{(\w+)(?::-(.*))?\}", _replace_var, content)

        if split_key:
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                continue

            common = data.get("common", {})
            section = data.get(split_key, {})

            for name, profile_data in section.items():
                merged = {**common, **profile_data}

                if target_path.endswith("/"):
                    individual_target = f"{target_path}{name}.yaml"
                else:
                    individual_target = f"{target_path}/{name}.yaml"

                if individual_target in _TOOL_PROFILE_PATHS:
                    dst = tool_home / individual_target
                else:
                    dst = cf_dir / individual_target
                dst.parent.mkdir(parents=True, exist_ok=True)

                merged_content = yaml.dump(
                    merged, default_flow_style=False, sort_keys=False
                )

                if dst.exists():
                    new_count = _merge_file(
                        dst, merged_content, merge_mode, individual_target
                    )
                else:
                    dst.write_text(merged_content, encoding="utf-8")
                    print(f"  {tag('CREATE')} {individual_target}")
                    new_count = 1

                count += new_count
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
            if dst.suffix == ".sh":
                import stat

                dst.chmod(
                    dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                )
            print(f"  {tag('CREATE')} {target_path}")
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
                print(f"  {tag('DELETE')} {rel}")
                deleted += 1

    if deleted:
        print(f"\n  Removed {deleted} orphaned file(s) from previous recipe.")
    else:
        print("\n  No orphaned files to clean up.")


def _print_summary(manifest: Dict[str, Any], cf_dir: Path) -> None:
    """Print a post-install summary — validate secrets, show advice, next steps."""
    from codefreedom.recipe.plan import _find_env_secrets_targets

    name = manifest.get("name", "unknown")
    description = manifest.get("description", "")
    required = manifest.get("required_secrets", [])
    config_vars = manifest.get("config_vars", [])
    advice = manifest.get("advice", "")

    print()
    print(f"  Recipe: {name}")
    if description:
        print(f"  {description}")
    print("  " + "-" * 55)

    _generate_recipe_instruction(manifest, cf_dir)

    # ── Collect env files for secret resolution ────────────────────────
    secrets_targets = _find_env_secrets_targets(manifest, cf_dir)
    env_files: list[Path] = []
    for target in secrets_targets:
        env_files.append(cf_dir / target)

    # ── Validate required secrets ─────────────────────────────────────
    missing_count = 0
    if required:
        print()
        print("  Secrets:")
        for secret in required:
            var = secret.get("var", "?")
            prompt = secret.get("prompt", "")

            value, source = _resolve_secret(var, env_files, cf_dir)
            if value is not None:
                label = f"  {green('[SET]')}   {var}"
                if source:
                    label += f"  ({source})"
                print(label)
            else:
                missing_count += 1
                label = f"  {yellow('[MISSING]')} {var}"
                if prompt:
                    label += f"  —  {prompt}"
                print(label)
                hint = secret.get("hint", "")
                if hint:
                    print(f"           {hint}")

        if missing_count:
            print()
            first_var = required[0].get("var", "?")
            tip1 = (
                "Tip: as machine env var use CF_CLI_<NAME> (e.g. CF_CLI_"
                + first_var
                + "),"
            )
            print(f"  {dim(tip1)}")
            print(f"  {dim('     or use the bare name in a .env.*.secrets file.')}")
            tip3 = "     Machine env vars take priority over secrets files."
            print(f"  {dim(tip3)}")

    # ── Validate config vars ──────────────────────────────────────────
    if config_vars:
        print()
        print("  Configuration (set in ~/.codefreedom/.env.user):")
        for cfg in config_vars:
            var = cfg.get("var", "?")
            prompt = cfg.get("prompt", "")

            value, source = _resolve_secret(var, env_files, cf_dir)
            if value is not None:
                label = f"  {green('[SET]')}   {var}"
                if source:
                    label += f"  ({source})"
                print(label)
            else:
                missing_count += 1
                label = f"  {yellow('[MISSING]')} {var}"
                if prompt:
                    label += f"  —  {prompt}"
                print(label)
                hint = cfg.get("hint", "")
                if hint:
                    print(f"           {hint}")

    # ── Show advice from recipe YAML ──────────────────────────────────
    if advice:
        advice = advice.replace("{cf_dir}", str(cf_dir))
        print()
        for line in advice.strip().splitlines():
            print(f"  {line}")

    # ── Dynamic next steps ────────────────────────────────────────────
    if missing_count:
        print()
        print(
            f"  {red(f'{missing_count} secret(s) missing — set them before starting the proxy.')}"
        )
    else:
        print()
        print(f"  {green('All secrets configured.')} Ready to start:")
        print("    cf r px start")

    print("  " + "-" * 55)
    print()


def _resolve_secret(
    name: str, env_files: list[Path], cf_dir: Path | None = None
) -> tuple[str | None, str | None]:
    """Resolve a secret across CF_CLI_* env, os.environ, and .env files.

    Priority chain:
      1. ``CF_CLI_<NAME>`` in os.environ (highest priority)
      2. ``NAME`` directly in os.environ
      3. ``NAME=`` in .env.user (user-managed overrides)
      4. ``NAME=`` in the provided env_files (ignoring CHANGE_ME)
    """
    workspace_dir = Path.cwd()
    return resolve_config_value(
        name,
        workspace_dir=workspace_dir,
        extra_env_files=env_files,
    )


def _generate_recipe_instruction(manifest: Dict[str, Any], cf_dir: Path) -> None:
    """Generate a persistent ``~/.codefreedom/RECIPE.md`` instruction file.

    This file records what recipe was installed, what files were created,
    and what tools are available. The doctor command (``cf manage doctor``) uses
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
            lines.append(f"- `{t}` — start with: `cf run tools {t} start`")
        lines.append("")

    lines.append("## Quick Start")
    lines.append("")
    required = manifest.get("required_secrets", [])
    config_vars = manifest.get("config_vars", [])
    step = 1
    if required:
        lines.append(f"{step}. Set required secrets in your `.secrets` files:")
        for s in required:
            lines.append(f"   - `{s.get('var', '?')}`")
        lines.append("")
        step += 1
    if config_vars:
        lines.append(f"{step}. Set configuration in `~/.codefreedom/.env.user`:")
        for c in config_vars:
            lines.append(f"   - `{c.get('var', '?')}`")
        lines.append("")
        step += 1
    lines.append(f"{step}. Run `cf r px start` to start the proxy")
    lines.append(f"{step + 1}. Run `cf r ag cc` to launch the agent")
    lines.append("")
    lines.append("See `COMMANDS.md` for the full command reference.")
    lines.append("")

    content = "\n".join(lines)
    instruction_path = cf_dir / "RECIPE.md"

    try:
        instruction_path.write_text(content, encoding="utf-8")
        print(f"  {tag('INFO')}  Instructions written to {instruction_path}")
    except OSError as e:
        eprint(f"{tag('RECIPE')} Warning: Could not write instructions: {e}")
