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
from codefreedom.cli.git.specs import CONVENTIONAL_COMMITS_SPEC
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

_CONVENTIONAL_TYPE_DOCS = {
    "feat": "A new feature for the user",
    "fix": "A bug fix",
    "docs": "Documentation-only changes",
    "style": "Formatting, whitespace, or missing semicolons (no code change)",
    "refactor": "A code change that neither fixes a bug nor adds a feature",
    "perf": "A code change that improves performance",
    "test": "Adding or fixing tests",
    "build": "Build system or external dependency changes",
    "ci": "CI configuration files and scripts",
    "chore": "Other changes that do not modify src or test files",
    "revert": "Reverts a previous commit",
}

_VALID_MSG_RE = re.compile(
    r"^(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)"
    r"(?:\([a-zA-Z0-9_\-/]+\))?:\s+.+$"
)
_TYPE_AT_START_RE = re.compile(
    r"^\s*(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)"
    r"(?:\(([a-zA-Z0-9_\-/]*)\))?\s*:",
)
_MAX_RETRIES = 2
_RETRY_PREVIEW_CHARS = 240


def _build_commit_system_prompt(
    config: dict,
    no_scope: bool = False,
) -> str:
    """Build the system prompt for commit message generation.

    The full Conventional Commits spec is bundled inline as a "skill"
    so the model has the reference available without URL lookups.
    """
    modules = get_modules(config)
    conventional = is_conventional_commit(config)

    parts: list[str] = []

    if conventional:
        parts.extend([
            "You are a git commit message generator.",
            "Apply the Conventional Commits spec that follows INLINE — do "
            "NOT visit any URL; the spec is provided below.",
            "",
        ])

        parts.append(CONVENTIONAL_COMMITS_SPEC)
        parts.append("")

        if modules:
            parts.extend([
                "## Available scopes (for this project)",
                ", ".join(modules),
                "Pick the most relevant scope. Lowercase only.",
                "",
            ])
        else:
            parts.extend([
                "## Scope",
                "Infer the scope from the changed files (a short lowercase "
                "noun). Use a short, stable name; if none fits well, omit it.",
                "",
            ])

        if no_scope:
            parts.extend([
                "## Output format (no scope)",
                "TYPE: DESCRIPTION",
                "  - TYPE is mandatory.",
                "  - DESCRIPTION is mandatory; see the inline spec for rules.",
                "",
            ])
        else:
            parts.extend([
                "## Output format",
                "TYPE(SCOPE): DESCRIPTION",
                "  - TYPE is mandatory (from the spec).",
                "  - SCOPE is optional but recommended (lowercase noun).",
                "  - DESCRIPTION is mandatory (see inline spec).",
                "",
            ])

        parts.extend([
            "## Strict output rules for this task",
            "- Output ONE single line — no body, no trailers, no bullet points.",
            "- No code fences, no quotes, no \"Here is the commit message:\" prefix.",
            "- No markdown, no backticks, no leading bullet.",
            "- The very first character of your reply must be the type word.",
            "- Do NOT include ``, reasoning, or chain-of-thought blocks "
            "in your final output. If your model emits them, strip them "
            "and return only the final commit message line.",
            "- Do NOT include any role tags like [user], [assistant], or "
            "chat-format tokens in your final output.",
            "- Do NOT include any explanation, apology, or commentary.",
        ])
    else:
        parts.extend([
            "You are a git commit message generator.",
            "Generate a short, clear commit message describing the changes.",
            "Output ONLY the commit message — no quotes, no code fences, no prefix.",
            "Do NOT include `` blocks, role tags, or any extra text.",
        ])

    return "\n".join(parts)


def _build_retry_user_prompt(
    previous_response: str,
    error_reason: str,
    original_user_prompt: str,
) -> str:
    """Build the user prompt sent on a retry attempt.

    Surfaces the exact previous response and the specific validation
    failure so the LLM can self-correct instead of guessing.
    """
    preview = previous_response.strip()
    if len(preview) > _RETRY_PREVIEW_CHARS:
        preview = preview[:_RETRY_PREVIEW_CHARS] + "..."
    safe_preview = preview if preview else "<empty response>"

    return (
        "Your previous response did not match the required format.\n\n"
        "## Your previous response (verbatim)\n"
        f"```\n{safe_preview}\n```\n\n"
        "## Why it failed\n"
        f"{error_reason}\n\n"
        "## How to fix\n"
        "Reply with ONE single line that starts with one of the allowed "
        "types (feat, fix, chore, docs, style, refactor, perf, test, "
        "build, ci, revert), followed by an optional (scope) in lowercase, "
        "then ': ' and an imperative description (max 72 chars). "
        "Do not include quotes, code fences, or any other text.\n\n"
        "## Examples of valid messages\n"
        "feat(auth): add user login validation\n"
        "fix(api): handle null response\n"
        "chore: update dependencies\n\n"
        "## Original task\n"
        f"{original_user_prompt}"
    )


def _validate_commit_message(candidate: str) -> tuple[str, str | None]:
    """Validate a rendered commit message against the conventional spec.

    Returns ``(candidate, None)`` when the message is valid, or
    ``(candidate, error_reason)`` describing the specific failure.
    The candidate is returned in both cases so the caller can still use
    it as a last resort.
    """
    if not candidate or not candidate.strip():
        return candidate, "Response was empty (no text returned by the LLM)."

    if "\n" in candidate:
        first_line, *_ = candidate.split("\n")
        if not first_line.strip():
            return candidate, (
                "Response was empty on the first line; the LLM must output "
                "the commit message as the very first line."
            )

    first_line = candidate.split("\n", 1)[0].strip()

    if not first_line:
        return candidate, (
            "First line is blank; the commit message must be on the first line."
        )

    m = _TYPE_AT_START_RE.match(first_line)
    if not m:
        allowed = ", ".join(_CONVENTIONAL_TYPES)
        return candidate, (
            f"First line does not start with a valid Conventional Commits type. "
            f"Allowed types: {allowed}. "
            f"Got: {first_line!r}."
        )

    commit_type = m.group(1)
    scope = m.group(2) or ""
    prefix = f"{commit_type}({scope})" if scope else commit_type

    description = first_line[m.end():].strip()
    if not description:
        return candidate, (
            f"Description is empty after '{prefix}:'. "
            "A short imperative description is mandatory."
        )

    if not _VALID_MSG_RE.match(candidate):
        return candidate, (
            f"Message did not match the strict Conventional Commits pattern. "
            f"Expected: {prefix}: lowercase imperative description "
            "(max 72 chars)."
        )

    if len(first_line) > 72:
        return candidate, (
            f"Subject line is {len(first_line)} chars; the Conventional Commits "
            "spec recommends no more than 72."
        )

    return candidate, None


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

    original_user_prompt = user_prompt

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

        validated, error_reason = _validate_commit_message(candidate)
        if error_reason is None:
            return validated, -1

        if attempt < _MAX_RETRIES:
            preview = response.strip()
            if len(preview) > _RETRY_PREVIEW_CHARS:
                preview = preview[:_RETRY_PREVIEW_CHARS] + "..."
            preview = preview if preview else "<empty>"
            eprint(
                f"{tag('WARN')} Malformed commit message "
                f"(attempt {attempt + 1}/{_MAX_RETRIES + 1}), retrying..."
            )
            eprint(f"   LLM returned: {preview}")
            eprint(f"   Reason: {error_reason}")
            user_prompt = _build_retry_user_prompt(
                previous_response=response,
                error_reason=error_reason,
                original_user_prompt=original_user_prompt,
            )
        else:
            preview = response.strip()
            if len(preview) > _RETRY_PREVIEW_CHARS:
                preview = preview[:_RETRY_PREVIEW_CHARS] + "..."
            preview = preview if preview else "<empty>"
            eprint(
                f"{tag('WARN')} LLM produced malformed message after "
                f"{_MAX_RETRIES + 1} attempts — using as-is."
            )
            eprint(f"   LLM returned: {preview}")
            eprint(f"   Last failure: {error_reason}")
            return validated, -1

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
