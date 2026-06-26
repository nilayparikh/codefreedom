"""cf git cmt — Commit workflow with LLM-generated messages."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from codefreedom.cli.git import git_ops, llm, templates
from codefreedom.cli.git.config import (
    get_model,
    get_modules,
    get_template,
    is_conventional_commit,
    is_signed_commit,
    load_git_config,
)
from codefreedom.log import eprint, tag

_CONVENTIONAL_TYPES = [
    "feat",
    "fix",
    "chore",
    "docs",
    "style",
    "refactor",
    "perf",
    "test",
    "build",
    "ci",
    "revert",
]

_VALID_MSG_RE = re.compile(
    r"^(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)"
    r"(?:\([a-zA-Z0-9_\-/]+\))?:\s+.+$"
)
_MAX_RETRIES = 2


def _build_commit_system_prompt(
    config: dict,
    no_scope: bool = False,
) -> str:
    """Build the system prompt for commit message generation."""
    modules = get_modules(config)
    conventional = is_conventional_commit(config)

    parts = ["You are a git commit message generator.", ""]

    if conventional:
        if modules:
            parts.append(f"Available modules/scopes: {', '.join(modules)}")
            parts.append("Pick the most relevant module for the scope.")
        else:
            parts.append("Infer the scope from the changed files.")
        parts.append("")

        if no_scope:
            parts.append("Output format (no scope):")
            parts.append("TYPE: DESCRIPTION")
            parts.append("")
            parts.append(f"TYPE must be one of: {', '.join(_CONVENTIONAL_TYPES)}")
        else:
            parts.append("Output format:")
            parts.append("TYPE(SCOPE): DESCRIPTION")
            parts.append("")
            parts.append(f"TYPE must be one of: {', '.join(_CONVENTIONAL_TYPES)}")
            parts.append("SCOPE is the module/area affected.")

        parts.append("")
        parts.append(
            "DESCRIPTION should be a short imperative description (max 72 chars)."
        )
        parts.append("Output ONLY the commit message, nothing else.")
    else:
        parts.append("Generate a short, clear commit message describing the changes.")
        parts.append("Output ONLY the commit message, nothing else.")

    return "\n".join(parts)


def _prompt_user(message: str, default: str = "y") -> str:
    """Prompt the user for confirmation. Returns 'y' or 'n'."""
    hint = "Y/n" if default == "y" else "y/N"
    try:
        response = input(f"\n{message} [{hint}]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return "n"
    if not response:
        return default
    return response[0]


def _open_editor(initial_text: str) -> str | None:
    """Open $EDITOR with the initial text. Returns edited text or None on failure."""
    editor = os.environ.get("EDITOR", "vi")
    tmp_path = Path("/tmp") / "cf_commit_msg.txt"
    tmp_path.write_text(initial_text, encoding="utf-8")
    try:
        subprocess.run([editor, str(tmp_path)], check=True)
        return tmp_path.read_text(encoding="utf-8").strip()
    except Exception:
        return None
    finally:
        tmp_path.unlink(missing_ok=True)


def _prepare_staged_diff(
    args: object, work_dir: Path, changed: list[str]
) -> tuple[str, int]:
    """Stage files and return the staged diff.

    Returns (staged_diff, exit_code). exit_code != 0 means bail early.
    """
    dry_run = getattr(args, "dry_run", False)
    stage_only = getattr(args, "stage_only", False)
    files = getattr(args, "files", None)

    if dry_run:
        staged = git_ops.get_staged_files(work_dir)
        unstaged = [f for f in changed if f not in staged]
        if not staged and not unstaged:
            eprint(f"{tag('WARN')} No changes to commit.")
            return "", 0
        if unstaged:
            eprint(
                f"{tag('INFO')} Unstaged files (not staging in dry-run): {', '.join(unstaged)}"
            )
        if not staged:
            staged_diff = "\n".join(
                f"diff --git a/{f} b/{f}\nnew file mode 100644\n--- /dev/null\n+++ b/{f}"
                for f in unstaged[:5]
            )
        else:
            staged_diff = git_ops.get_staged_diff(work_dir)
    elif stage_only:
        staged = git_ops.get_staged_files(work_dir)
        if files:
            ok = git_ops.stage_files(files, cwd=work_dir)
            if not ok:
                eprint(f"{tag('ERROR')} Failed to stage files.")
                return "", 1
            staged = git_ops.get_staged_files(work_dir)
        if not staged:
            eprint(
                f"{tag('WARN')} No staged changes. Use 'git add' first or run without --stage-only."
            )
            return "", 0
        staged_diff = git_ops.get_staged_diff(work_dir)
    else:
        if files:
            ok = git_ops.stage_files(files, cwd=work_dir)
        else:
            ok = git_ops.stage_files(cwd=work_dir)
        if not ok:
            eprint(f"{tag('ERROR')} Failed to stage files.")
            return "", 1
        staged_diff = git_ops.get_staged_diff(work_dir)

    if not staged_diff.strip():
        eprint(f"{tag('WARN')} No staged changes to commit.")
        return "", 0

    return staged_diff, -1


def _generate_commit_message(
    args: object, config: dict, work_dir: Path, staged_diff: str
) -> tuple[str, int]:
    """Generate or retrieve the commit message.

    Returns (commit_msg, exit_code). exit_code != 0 means bail early.
    """
    explicit_message = getattr(args, "message", None)
    no_scope = getattr(args, "no_scope", False)

    if explicit_message:
        return explicit_message, -1

    model = get_model(config)
    system_prompt = _build_commit_system_prompt(config, no_scope)
    staged_files = git_ops.get_staged_files(work_dir)
    files_list = "\n".join(f"- {f}" for f in staged_files)
    user_prompt = f"Files changed:\n{files_list}\n\nDiff:\n\n{staged_diff}"

    eprint(f"{tag('COMMIT')} Generating commit message via {model}...")

    for attempt in range(_MAX_RETRIES + 1):
        response = llm.generate_message(
            model,
            system_prompt,
            user_prompt,
            max_tokens=16000,
            work_dir=work_dir,
        )
        if response is None:
            return "", 1

        parsed = llm.parse_commit_response(response)
        template = get_template(config, "commit_message")
        candidate = templates.render_template(template, parsed)

        if no_scope:
            candidate = templates.strip_scope(candidate)

        if _VALID_MSG_RE.match(candidate):
            return candidate, -1

        if attempt < _MAX_RETRIES:
            eprint(
                f"{tag('WARN')} Malformed commit message "
                f"(attempt {attempt + 1}/{_MAX_RETRIES + 1}), retrying..."
            )
            user_prompt = (
                f"Your previous response was malformed:\n{candidate}\n\n"
                "Follow the required format exactly.\n\n"
                f"{user_prompt}"
            )
        else:
            eprint(
                f"{tag('WARN')} LLM produced malformed message after "
                f"{_MAX_RETRIES + 1} attempts — using as-is."
            )
            return candidate, -1

    return "", 1


def _execute_commit(
    args: object, work_dir: Path, commit_msg: str, use_signed: bool
) -> int:
    """Execute the commit (and optionally push). Returns exit code."""
    auto_yes = getattr(args, "yes", False)
    dry_run = getattr(args, "dry_run", False)

    eprint(f"{tag('COMMIT')} Generated message:\n  {commit_msg}")

    if dry_run:
        eprint(f"{tag('INFO')} Dry run — not committing.")
        return 0

    if not auto_yes:
        choice = _prompt_user("Commit?")
        if choice == "n":
            eprint(f"{tag('SKIP')} Commit aborted.")
            return 0
        elif choice == "e":
            edited = _open_editor(commit_msg)
            if edited:
                commit_msg = edited
            else:
                eprint(f"{tag('ERROR')} Editor failed.")
                return 1

    ok, output = git_ops.commit(commit_msg, signed=use_signed, cwd=work_dir)
    if ok:
        eprint(f"{tag('OK')} Committed successfully.")
        if output.strip():
            eprint(output.strip())

        if not auto_yes:
            push_choice = _prompt_user("Push to remote?")
            if push_choice == "y":
                eprint(f"{tag('PUSH')} Pushing to origin...")
                push_ok, push_output = git_ops.push(cwd=work_dir)
                if push_ok:
                    eprint(f"{tag('OK')} Pushed successfully.")
                else:
                    eprint(f"{tag('ERROR')} Push failed:\n{push_output}")

        return 0
    else:
        eprint(f"{tag('ERROR')} Commit failed:\n{output}")
        return 1


def run_commit(args: object) -> int:
    """Execute the commit workflow."""
    work_dir = Path.cwd()

    if not git_ops.is_git_repo(work_dir):
        eprint(f"{tag('ERROR')} Not a git repository.")
        return 1

    no_sign = getattr(args, "no_sign", False)
    force_signed = getattr(args, "signed", None)

    config = load_git_config(work_dir)
    use_signed = is_signed_commit(config) if not no_sign else False
    if force_signed:
        use_signed = True

    changed = git_ops.get_changed_files(work_dir)
    if not changed:
        eprint(f"{tag('WARN')} No changes to commit.")
        return 0

    staged_diff, rc = _prepare_staged_diff(args, work_dir, changed)
    if rc != -1:
        return rc

    commit_msg, rc = _generate_commit_message(args, config, work_dir, staged_diff)
    if rc != -1:
        return rc

    return _execute_commit(args, work_dir, commit_msg, use_signed)
