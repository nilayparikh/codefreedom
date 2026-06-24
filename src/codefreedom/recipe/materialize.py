"""Recipe materialization — flatten chains, merge blocks, normalize output."""

from __future__ import annotations

from typing import Any

from codefreedom.recipe.generated_artifacts import (
    render_bash_setup_script,
    render_env_template,
    render_powershell_setup_script,
)


def flatten_recipe_chain(
    manifest: dict[str, Any], base_manifest: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Merge base and child recipe metadata into a single flattened dict.

    Child entries override base entries for scalar/list fields. For files
    and required_secrets, entries are concatenated with child entries taking
    priority on key conflicts (same target path or same var name).
    """
    if base_manifest is None:
        return manifest

    merged: dict[str, Any] = dict(manifest)

    list_merge_keys = ["files", "required_secrets", "config_vars", "generated_artifacts"]
    for key in list_merge_keys:
        base_val = base_manifest.get(key) or []
        child_val = manifest.get(key) or []
        if key == "files":
            merged[key] = _merge_file_lists(base_val, child_val)
        elif key == "required_secrets":
            merged[key] = _merge_secrets_lists(base_val, child_val)
        else:
            merged[key] = _merge_by_key(base_val, child_val)

    # dirs is a list of strings, deduplicated preserving order
    base_dirs = base_manifest.get("dirs") or []
    child_dirs = manifest.get("dirs") or []
    if base_dirs or child_dirs:
        seen_dirs: dict[str, None] = {}
        for d in base_dirs:
            seen_dirs[d] = None
        for d in child_dirs:
            seen_dirs[d] = None
        merged["dirs"] = list(seen_dirs.keys())

    dict_merge_keys = ["common_blocks", "profile_presets"]
    for key in dict_merge_keys:
        base_val = base_manifest.get(key)
        child_val = manifest.get(key)
        if base_val is None and child_val is None:
            continue
        base_val = base_val or {}
        child_val = child_val or {}
        merged[key] = {**base_val, **child_val}

    return merged


def merge_recipe_blocks(manifest: dict[str, Any]) -> dict[str, Any]:
    """Resolve common_blocks.secret_groups into manifest's required_secrets.

    All secret entries from all secret_groups are appended to the
    manifest's required_secrets list. Existing entries are preserved.
    """
    result = dict(manifest)
    common_blocks = manifest.get("common_blocks")
    if not common_blocks:
        return result

    secret_groups = common_blocks.get("secret_groups", {})
    existing_secrets = list(result.get("required_secrets") or [])

    for _group_name, group_data in secret_groups.items():
        group_secrets = group_data.get("required_secrets", [])
        existing_secrets.extend(group_secrets)

    result["required_secrets"] = existing_secrets
    return result


def materialize_recipe(
    manifest: dict[str, Any], files: dict[str, str]
) -> dict[str, Any]:
    """Produce a normalized structure with static and generated entries.

    Returns:
        {
            "entries": [...],
            "managed_targets": {"path/to/file", ...},
            "summary": {"recipe": ..., "static_count": ..., "generated_count": ..., ...}
        }
    """
    entries: list[dict[str, Any]] = []
    managed_targets: set[str] = set()

    recipe_name = manifest.get("name", "")

    # Static file entries
    for file_entry in manifest.get("files", []):
        src_path = file_entry.get("path", "")
        target = file_entry.get("target", src_path)
        merge_mode = file_entry.get("merge", "auto")
        content = files.get(target) or files.get(src_path) or ""
        entry: dict[str, Any] = {
            "type": "static",
            "target": target,
            "content": content,
            "merge": merge_mode,
        }
        if file_entry.get("split_by_key"):
            entry["split_by_key"] = file_entry["split_by_key"]
        if file_entry.get("copy_dir"):
            entry["copy_dir"] = file_entry["copy_dir"]
            entry["path"] = src_path
        entries.append(entry)
        managed_targets.add(target)

    # Resolve common_blocks into required_secrets before generating artifacts
    resolved = merge_recipe_blocks(manifest)

    # Generated artifact entries
    secrets = [
        {"var": s["var"], "prompt": s.get("prompt", ""), "default": s.get("default")}
        for s in resolved.get("required_secrets", [])
    ]
    config_vars = [
        {"var": c["var"], "prompt": c.get("prompt", ""), "default": c.get("default")}
        for c in resolved.get("config_vars", [])
    ]
    service_groups = resolved.get("service_groups", [])

    for artifact in manifest.get("generated_artifacts", []):
        kind = artifact.get("kind", "")
        target = artifact.get("target", "")
        content = _render_artifact(kind, recipe_name, secrets, config_vars, service_groups)
        entries.append(
            {
                "type": "generated",
                "target": target,
                "kind": kind,
                "content": content,
            }
        )
        managed_targets.add(target)

    # Summary
    secret_count = len(resolved.get("required_secrets", []))
    config_count = len(resolved.get("config_vars", []))
    static_count = sum(1 for e in entries if e["type"] == "static")
    generated_count = sum(1 for e in entries if e["type"] == "generated")

    return {
        "entries": entries,
        "managed_targets": managed_targets,
        "summary": {
            "recipe": recipe_name,
            "static_count": static_count,
            "generated_count": generated_count,
            "secret_count": secret_count,
            "config_count": config_count,
        },
    }


def _merge_file_lists(
    base: list[dict[str, Any]], child: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge file lists; child entries override base by target path."""
    by_target: dict[str, dict[str, Any]] = {}
    for entry in base:
        target = entry.get("target", entry.get("path", ""))
        if target:
            by_target[target] = entry
    for entry in child:
        target = entry.get("target", entry.get("path", ""))
        if target:
            by_target[target] = entry
    result = list(by_target.values())
    for entry in result:
        if "target" not in entry and "path" in entry:
            entry["target"] = entry["path"]
    return result


def _merge_secrets_lists(
    base: list[dict[str, Any]], child: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge secrets lists; child entries override base by var name."""
    by_var: dict[str, dict[str, Any]] = {}
    for entry in base:
        by_var[entry["var"]] = entry
    for entry in child:
        by_var[entry["var"]] = entry
    return list(by_var.values())


def _merge_by_key(
    base: list[dict[str, Any]], child: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Generic list merge using a 'name' or 'var' key."""
    by_key: dict[str, dict[str, Any]] = {}
    for entry in base:
        k = entry.get("name") or entry.get("var") or entry.get("path", "")
        if k:
            by_key[k] = entry
    for entry in child:
        k = entry.get("name") or entry.get("var") or entry.get("path", "")
        if k:
            by_key[k] = entry
    return list(by_key.values())


def _render_artifact(
    kind: str,
    recipe_name: str,
    secrets: list[dict[str, str]],
    config_vars: list[dict[str, str]],
    service_groups: list[dict[str, Any]],
) -> str:
    """Render a generated artifact by kind."""
    if kind == "setup_script_bash":
        return render_bash_setup_script(recipe_name, secrets, config_vars, service_groups)
    if kind == "setup_script_powershell":
        return render_powershell_setup_script(
            recipe_name, secrets, config_vars, service_groups
        )
    if kind == "env_template":
        return render_env_template(secrets)
    return ""
