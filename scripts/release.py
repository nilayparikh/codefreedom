#!/usr/bin/env python3
"""
CodeFreedom Release Script

Reads version from version.yaml and creates/pushes a git tag.
The tag triggers pipy.yaml to publish to PyPI and create a GitHub Release.

Usage:
    python scripts/release.py
    python scripts/release.py --dry-run
    python scripts/release.py --bump dev
    python scripts/release.py --bump rc
    python scripts/release.py --bump version
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml


VERSION_FILE = Path(__file__).parent.parent / "version.yaml"


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def load_version() -> dict:
    with open(VERSION_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_version(data: dict) -> None:
    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create and push a release tag")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without executing")
    parser.add_argument("--bump", choices=["dev", "rc", "version"], help="Bump version before release")
    args = parser.parse_args()

    data = load_version()
    version = data["version"]
    dev = data.get("dev", 1)
    rc = data.get("rc", 1)

    if args.bump == "version":
        parts = version.split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        version = ".".join(parts)
        data["version"] = version
        data["dev"] = 1
        data["rc"] = 1
    elif args.bump == "dev":
        data["dev"] = dev + 1
        dev = data["dev"]
    elif args.bump == "rc":
        data["rc"] = rc + 1
        rc = data["rc"]

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
        if args.bump:
            print(f"  Update version.yaml: version={version}, dev={dev}, rc={rc}")
            print(f"  git add version.yaml")
            print(f"  git commit -m 'chore: bump version to {version}'")
        print(f"  git tag -a {tag} -m 'Release {tag}'")
        print(f"  git push origin {tag}")
        return 0

    if args.bump:
        save_version(data)
        run(["git", "add", "version.yaml"])
        run(["git", "commit", "-m", f"chore: bump version to {version}"])
        print(f"Updated version.yaml and committed")

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
