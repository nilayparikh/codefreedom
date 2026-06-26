"""Recipe merge engines — DeepDiff structural merge, .env key merge, diffs."""

from __future__ import annotations

import datetime
import difflib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from codefreedom.log import eprint, tag

MERGEABLE_EXTENSIONS = {".yaml", ".yml", ".json"}


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
        print(f"  [RECIPE] {display_path}")
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
            "[RECIPE] Warning: deepdiff not installed — falling back to overwrite "
            f"for {display_path}"
        )
        return incoming

    try:
        existing_obj = yaml.safe_load(existing)
        incoming_obj = yaml.safe_load(incoming)
    except yaml.YAMLError as e:
        eprint(f"{tag('RECIPE')} Warning: YAML parse error in {display_path}: {e}")
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
# Diff helpers (for plan generation and apply)
# ═══════════════════════════════════════════════════════════════════════════════


def _make_diff(
    existing: str, incoming: str, path: str, from_devnull: bool = False
) -> str:
    """Generate a unified diff between existing and incoming content.

    When *from_devnull* is ``True``, the diff shows the incoming content
    as a new file (``/dev/null`` → ``b/path``), matching ``git diff``
    style for new files.
    """
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
