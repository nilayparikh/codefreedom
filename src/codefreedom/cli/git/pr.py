"""cf git pr — PR generation and creation workflow."""

from __future__ import annotations

import shutil
import subprocess
import urllib.parse
from pathlib import Path

from codefreedom.cli.git import git_ops, llm
from codefreedom.cli.git.config import (
    get_model,
    get_modules,
    get_template,
    load_git_config,
)
from codefreedom.log import eprint, tag


def _build_pr_system_prompt(config: dict) -> str:
    """Build the system prompt for PR generation."""
    modules = get_modules(config)
    parts = [
        "You are a pull request description generator.",
        "",
    ]
    if modules:
        parts.append(f"Available modules/scopes: {', '.join(modules)}")
        parts.append("")
    parts.append("Generate a PR title and body.")
    parts.append("")
    parts.append("Output format:")
    parts.append("TITLE: TYPE(SCOPE): DESCRIPTION")
    parts.append("BODY:")
    parts.append("<filled PR description>")
    parts.append("")
    parts.append("TITLE must follow conventional commit format.")
    parts.append("BODY should follow the provided template structure.")
    parts.append("Output ONLY the title and body, nothing else.")
    return "\n".join(parts)


def _prompt_user(message: str) -> str:
    """Prompt the user for confirmation."""
    try:
        response = input(f"\n{message} [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return "n"
    return "y" if not response else response[0]


def _open_browser(url: str) -> bool:
    """Open a URL in the default browser."""
    import webbrowser
    try:
        webbrowser.open(url)
        return True
    except Exception as e:
        eprint(f"{tag('ERROR')} Failed to open browser: {e}")
        return False


def _gh_available() -> bool:
    """Check if gh CLI is installed."""
    return shutil.which("gh") is not None


def _create_pr_gh(
    source: str, target: str, title: str, body: str, cwd: Path
) -> tuple[bool, str]:
    """Create a PR via gh CLI."""
    result = subprocess.run(
        [
            "gh", "pr", "create",
            "--base", target,
            "--head", source,
            "--title", title,
            "--body", body,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(cwd),
    )
    return result.returncode == 0, result.stdout + result.stderr


def run_pr(args: object) -> int:
    """Execute the PR workflow."""
    work_dir = Path.cwd()

    if not git_ops.is_git_repo(work_dir):
        eprint(f"{tag('ERROR')} Not a git repository.")
        return 1

    source = getattr(args, "source", None) or git_ops.get_current_branch(work_dir)
    if not source:
        eprint(f"{tag('ERROR')} Cannot determine current branch.")
        return 1

    target = getattr(args, "target", None) or "main"
    generate_only = getattr(args, "generate", False)
    browser_mode = getattr(args, "browser_mode", False)
    dry_run = getattr(args, "dry_run", False)

    config = load_git_config(work_dir)
    model = get_model(config)

    diff = git_ops.get_diff(target, work_dir)
    log = git_ops.get_log(target, work_dir)

    if not diff.strip() and not log.strip():
        eprint(f"{tag('WARN')} No changes between {target} and {source}.")
        return 0

    system_prompt = _build_pr_system_prompt(config)
    template = get_template(config, "pr_description")
    user_prompt = (
        f"Source branch: {source}\n"
        f"Target branch: {target}\n\n"
        f"Commits since {target}:\n{log}\n\n"
        f"Diff:\n{diff}\n\n"
        f"PR description template:\n{template}"
    )

    eprint(f"{tag('PR')} Generating PR description via {model}...")
    response = llm.generate_message(model, system_prompt, user_prompt, max_tokens=1000)
    if response is None:
        return 1

    parsed = llm.parse_pr_response(response)
    pr_title = parsed["title"]
    pr_body = parsed["body"]

    eprint(f"{tag('PR')} Generated:\n  Title: {pr_title}\n")
    eprint(f"  Body:\n{pr_body}\n")

    if dry_run or generate_only:
        eprint(f"{tag('INFO')} {'Dry run' if dry_run else 'Generate only'} — no action taken.")
        return 0

    choice = _prompt_user("Confirm?")
    if choice == "n":
        eprint(f"{tag('SKIP')} PR creation aborted.")
        return 0

    if not browser_mode and _gh_available():
        eprint(f"{tag('PR')} Creating PR via gh CLI...")
        ok, output = _create_pr_gh(source, target, pr_title, pr_body, work_dir)
        if ok:
            eprint(f"{tag('OK')} PR created successfully.")
            eprint(output.strip())
            return 0
        else:
            eprint(f"{tag('WARN')} gh CLI failed, falling back to browser mode.")
            eprint(output.strip())

    remote_url = git_ops.get_remote_url(work_dir)
    if not remote_url:
        eprint(f"{tag('ERROR')} Cannot determine remote URL.")
        return 1

    owner_repo = git_ops.parse_remote_owner_repo(remote_url)
    if not owner_repo:
        eprint(f"{tag('ERROR')} Cannot parse remote URL: {remote_url}")
        return 1

    owner, repo = owner_repo
    encoded_title = urllib.parse.quote(pr_title)
    encoded_body = urllib.parse.quote(pr_body)
    url = (
        f"https://github.com/{owner}/{repo}"
        f"/compare/{target}...{source}"
        f"?title={encoded_title}&body={encoded_body}"
    )

    eprint(f"{tag('PR')} Opening browser...")
    if _open_browser(url):
        eprint(f"{tag('OK')} Browser opened with PR creation URL.")
    else:
        eprint(f"{tag('INFO')} URL:\n{url}")

    return 0
