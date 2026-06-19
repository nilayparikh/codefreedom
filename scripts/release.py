#!/usr/bin/env python3
"""
CodeFreedom Release Script

Creates and pushes a git tag from the main branch.
The tag triggers pipy.yaml to publish to PyPI and create a GitHub Release.

Usage:
    python scripts/release.py 0.2.1
    python scripts/release.py 0.2.1 --dry-run
"""

from __future__ import annotations

import argparse
import subprocess
import sys


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create and push a release tag")
    parser.add_argument("version", help="Version to release (e.g., 0.2.1)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without executing")
    args = parser.parse_args()

    version = args.version.lstrip("v")
    tag = f"v{version}"

    result = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], check=False)
    branch = result.stdout.strip()

    if branch != "main":
        print(f"Error: releases must be created from main branch. Current: {branch}")
        return 1

    result = run(["git", "status", "--porcelain"], check=False)
    if result.stdout.strip():
        print("Error: working tree is dirty. Commit or stash changes first.")
        return 1

    result = run(["git", "rev-parse", tag], check=False)
    if result.returncode == 0:
        print(f"Error: tag {tag} already exists")
        return 1

    print(f"Release: {version}")
    print(f"Tag: {tag}")
    print(f"Branch: {branch}")
    print()

    if args.dry_run:
        print("Dry run — would execute:")
        print(f"  git tag -a {tag} -m 'Release {tag}'")
        print(f"  git push origin {tag}")
        return 0

    run(["git", "tag", "-a", tag, "-m", f"Release {tag}"])
    print(f"Created tag: {tag}")

    run(["git", "push", "origin", tag])
    print(f"Pushed tag: {tag}")
    print()
    print(f"Tag {tag} pushed. GitHub Actions will now:")
    print(f"  1. Run tests")
    print(f"  2. Build package")
    print(f"  3. Publish to PyPI")
    print(f"  4. Create GitHub Release")
    print()
    print(f"Watch: https://github.com/nilayparikh/codefreedom/actions/workflows/pipy.yaml")

    return 0


if __name__ == "__main__":
    sys.exit(main())
