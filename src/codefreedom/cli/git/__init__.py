"""cf git — Git commit and PR workflow commands.

Subcommands:
    cf git commit   — LLM-powered commit message generation and committing
    cf git pr       — LLM-powered PR title/description generation and creation
"""

from __future__ import annotations

import argparse
import sys

from codefreedom.log import eprint, tag


def build_parser(parser: argparse.ArgumentParser) -> None:
    """Build the argument parser for cf git."""
    sub = parser.add_subparsers(dest="git_command", title="git commands")

    # ── git commit ───────────────────────────────────────────────────────
    cmt = sub.add_parser(
        "commit",
        aliases=["c", "cmt"],
        help="Generate commit message via LLM and commit",
        description="LLM-powered commit workflow: stage, generate message, confirm, commit.",
    )
    cmt.add_argument(
        "-m", "--message",
        type=str, default=None,
        help="Provide commit message directly, skip LLM generation",
    )
    cmt.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Auto-commit without confirmation prompt",
    )
    cmt.add_argument(
        "-n", "--no-scope",
        action="store_true",
        help="Skip scope in conventional commit (type: desc instead of type(scope): desc)",
    )
    cmt.add_argument(
        "-S", "--signed",
        action="store_true", default=None,
        help="Override: sign this commit with GPG",
    )
    cmt.add_argument(
        "--no-sign",
        action="store_true",
        help="Override: don't sign this commit",
    )
    cmt.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview generated message without committing",
    )
    cmt.add_argument(
        "-s", "--stage-only",
        action="store_true",
        help="Only commit manually staged changes (don't auto-stage)",
    )
    cmt.add_argument(
        "files",
        nargs="*",
        metavar="FILE",
        help="Specific files to stage (default: all changed)",
    )
    cmt.set_defaults(func=_dispatch_cmt)

    # ── git pr ───────────────────────────────────────────────────────────
    pr = sub.add_parser(
        "pr",
        aliases=["p"],
        help="Generate PR title/description and create PR (default: create)",
        description="LLM-powered PR workflow: generate title and body, create PR.",
    )
    pr_sub = pr.add_subparsers(dest="pr_action", title="pr actions")
    pr_sub.required = False

    pr_default = pr_sub.add_parser(
        "create",
        help="Create PR via gh CLI (default action)",
    )
    _add_pr_flags(pr_default)
    pr_default.set_defaults(func=_dispatch_pr_create)

    pr_gen = pr_sub.add_parser(
        "generate",
        aliases=["gen"],
        help="Generate PR title and body without creating",
    )
    _add_pr_flags(pr_gen)
    pr_gen.set_defaults(func=_dispatch_pr_generate)

    pr.set_defaults(pr_action="create", func=_dispatch_pr_create)


def _add_pr_flags(parser: argparse.ArgumentParser) -> None:
    """Add shared flags to a PR subparser."""
    parser.add_argument(
        "-f", "--from",
        type=str, default=None, dest="source",
        help="Source branch (default: current branch)",
    )
    parser.add_argument(
        "-t", "--target",
        type=str, default=None,
        help="Target branch (default: main)",
    )
    parser.add_argument(
        "-b", "--browser-mode",
        action="store_true",
        help="Open browser instead of using gh CLI",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without any action",
    )


def _dispatch_cmt(args: argparse.Namespace) -> None:
    """Dispatch cf git cmt."""
    from codefreedom.cli.git.commit import run_commit
    sys.exit(run_commit(args))


def _dispatch_pr_create(args: argparse.Namespace) -> None:
    """Dispatch cf git pr create."""
    from codefreedom.cli.git.pr import run_pr
    args.create = True
    args.generate = False
    sys.exit(run_pr(args))


def _dispatch_pr_generate(args: argparse.Namespace) -> None:
    """Dispatch cf git pr generate."""
    from codefreedom.cli.git.pr import run_pr
    args.create = False
    args.generate = True
    sys.exit(run_pr(args))


def run(args: argparse.Namespace) -> int:
    """Entry point for cf git subcommands."""
    func = getattr(args, "func", None)
    if func:
        return func(args)

    eprint(f"{tag('ERROR')} No git subcommand specified.")
    return 1
