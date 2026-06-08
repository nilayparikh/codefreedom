"""Recipe subsystem for ``cf init --recipe <name>``.

Fetches predefined configuration recipes from the codefreedom-recipes
GitHub repository, then applies them to ``~/.codefreedom/`` with
intelligent structural merging via DeepDiff when a target file already
exists (second+ recipe or pre-existing config).

Recipe source priority:
  1. Local submodule at ``recipes/{name}/`` (development / git-clone installs)
  2. GitHub raw content (pip-installed / fallback)

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
      - path: profiles/claude-code.json
        target: profiles/claude-code.json
        merge: deepdiff
      - path: proxy/config/config.yaml
        target: proxy/config/config.yaml
        merge: deepdiff
      # ...

    required_secrets:
      - var: OPENCODE_ZEN_API_KEY
        prompt: "OpenCode Zen API key"

    optional_config:
      - var: LITELLM_MODEL_ALIAS_ULTRA
        default: "OpenCode/MiMo-V2.5-FREE"

Merge modes (``merge`` field in files):
  - ``deepdiff`` — structural YAML/JSON diff via DeepDiff
  - ``env`` — key=value .env-style merge (keeps existing keys)
  - ``auto`` — infer from file extension / name
  - ``overwrite`` — always write the recipe version
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from codefreedom.config import get_codefreedom_dir
from codefreedom.env_loader import eprint

# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

RECIPE_OWNER = "nilayparikh"
RECIPE_REPO = "codefreedom-recipes"
RECIPE_BRANCH = "main"

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


def list_recipes() -> int:
    """List all available recipes from the GitHub repository.

    Returns exit code 0 on success, 1 on failure.
    """
    recipes = _fetch_available_recipes()
    if not recipes:
        print("[recipe] No recipes found.")
        print(f"         {_GITHUB_API_BASE}")
        return 1

    print(f"[recipe] Available recipes ({len(recipes)}):")
    for name in recipes:
        print(f"           {name}")
    print()
    print("  Use:  cf init --recipe <name>")
    print(f"  Repo: https://github.com/{RECIPE_OWNER}/{RECIPE_REPO}")
    return 0


def init_recipe(name: str) -> int:
    """Fetch and apply a recipe to ``~/.codefreedom/``.

    This is the main entry point for ``cf init --recipe <name>``.

    Steps:
      1. Try local submodule ``recipes/{name}/``, fall back to GitHub raw.
      2. Parse ``recipe.yaml`` manifest.
      3. For each file in the manifest:
         - If target does **not** exist → create fresh.
         - If target **does** exist → merge using DeepDiff (YAML) or
           key-by-key (.env), preserving existing values.
      4. Print a "What's Next" summary with required secrets and next steps.
    """
    cf_dir = get_codefreedom_dir()

    # ── 1. Recipe source ────────────────────────────────────────────────
    manifest, files = _resolve_recipe(name)
    if manifest is None:
        print(f"[recipe] Recipe '{name}' not found.")
        print("         Run 'cf init --list-recipes' to see available recipes.")
        print(f"         Repo: https://github.com/{RECIPE_OWNER}/{RECIPE_REPO}")
        return 1

    # ── 1b. If recipe extends a base, resolve and install it first ──────
    extends = manifest.get("extends")
    if extends:
        print(f"  [EXTENDS] Installing base recipe '{extends}' first...")
        base_manifest, base_files = _resolve_recipe(extends)
        if base_manifest is None:
            print(
                f"  [WARN] Base recipe '{extends}' not found — continuing without it."
            )
        else:
            _install_recipe_files(base_manifest, base_files, cf_dir)

    # ── 2. Install / merge each file ─────────────────────────────────────
    _install_recipe_files(manifest, files, cf_dir)

    # ── 3. What's Next summary ──────────────────────────────────────────
    _print_summary(manifest, cf_dir)
    return 0


# ═══════════════════════════════════════════════════════════════════════════════
# Recipe resolution (local submodule → GitHub raw)
# ═══════════════════════════════════════════════════════════════════════════════


def _resolve_recipe(
    name: str,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, str]]:
    """Resolve a recipe from local submodule or GitHub.

    Returns (manifest, file_contents_dict).
    If the recipe cannot be found, returns (None, {}).
    """
    # 1. Try local submodule (dev installs with git clone)
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

    # 2. Fall back to GitHub raw
    try:
        manifest = _fetch_recipe_manifest(name)
        files = _fetch_recipe_files(name, manifest)
        return manifest, files
    except RecipeError as e:
        eprint(f"  [WARN] Could not fetch recipe '{name}' from GitHub: {e}")
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
    """Read all recipe files from the local filesystem."""
    files: Dict[str, str] = {}
    for entry in manifest.get("files", []):
        src_path = entry.get("path", "")
        target = entry.get("target", src_path)
        file_path = recipe_dir / src_path
        if file_path.exists():
            files[target] = file_path.read_text(encoding="utf-8")
        else:
            eprint(f"  [WARN] Local file not found: {file_path}")
    return files


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

    Returns count of files installed / modified.
    """
    file_entries = manifest.get("files", [])
    count = 0

    for entry in file_entries:
        src_path = entry.get("path", "")
        target_path = entry.get("target", src_path)
        merge_mode = entry.get("merge", "auto")

        content = files.get(target_path) or files.get(src_path)
        if content is None:
            continue

        dst = cf_dir / target_path
        dst.parent.mkdir(parents=True, exist_ok=True)

        if dst.exists():
            new_count = _merge_file(dst, content, merge_mode, target_path)
        else:
            dst.write_text(content, encoding="utf-8")
            print(f"  [CREATE] {target_path}")
            new_count = 1

        count += new_count

    if count:
        print(f"\n  Recipe applied — {count} file(s) created/updated.")
    else:
        print("\n  No files were changed.")

    return count


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
        from deepdiff import DeepDiff
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
    print("  " + "─" * 55)
    print()


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
                targets.append(str(dst))
    return targets
