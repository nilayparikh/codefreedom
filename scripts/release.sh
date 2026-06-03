#!/usr/bin/env bash
# ── CodeFreedom Release Script ─────────────────────────────────────────────────
# Two modes:
#   --version  — bump version in pyproject.toml (any branch, no push/tag)
#   --tag      — full release: bump, tag v* and push (main branch only)
#
# Tag push triggers:
#   • PyPI publish      (.github/workflows/pipy.yaml)
#   • Docker publish    (.github/workflows/publish-docker.yml)
#   • Docs publish      (.github/workflows/publish-docs.yml)
#
# ────────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Help ──────────────────────────────────────────────────────────────────
usage() {
  cat <<'EOF'
Usage: ./scripts/release.sh --version <semver> [--dry-run]
       ./scripts/release.sh --tag <semver> [--dry-run] [--force]

Modes:
  --version <semver>   Bump version in pyproject.toml and commit.
                       Works on any branch — use this to set a pre-release
                       version on feature branches for testing.

  --tag <semver>       Full release: bump version, tag v<semver>, push.
                       Only allowed on 'main' branch with clean working tree.

Options:
  --dry-run   Preview changes without committing or pushing.
  --force     Overwrite an existing tag (only with --tag).
  --help      Show this message.

Examples:
  ./scripts/release.sh --version 0.2.0-beta          # bump on any branch
  ./scripts/release.sh --tag 0.1.1                    # full release
  ./scripts/release.sh --tag 0.2.0 --dry-run          # preview a release
  ./scripts/release.sh --tag 0.1.1 --force             # overwrite existing tag
EOF
  exit 0
}

# ── Parse arguments ─────────────────────────────────────────────────────
DRY_RUN=false
FORCE=false
MODE=""
VERSION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h) usage ;;
    --dry-run) DRY_RUN=true; shift ;;
    --force)   FORCE=true; shift ;;
    --version)
      if [[ -n "$MODE" ]]; then echo "❌ Error: specify only one mode (--version or --tag)."; exit 1; fi
      MODE="version"
      shift
      if [[ $# -eq 0 || "$1" == -* ]]; then echo "❌ Error: --version requires a version argument."; exit 1; fi
      VERSION="$1"
      shift
      ;;
    --tag)
      if [[ -n "$MODE" ]]; then echo "❌ Error: specify only one mode (--version or --tag)."; exit 1; fi
      MODE="tag"
      shift
      if [[ $# -eq 0 || "$1" == -* ]]; then echo "❌ Error: --tag requires a version argument."; exit 1; fi
      VERSION="$1"
      shift
      ;;
    *)
      echo "❌ Unknown option: $1"
      usage
      ;;
  esac
done

if [[ -z "$MODE" ]]; then
  echo "❌ Error: specify --version <semver> or --tag <semver>."
  usage
fi

# Validate semver-like format
if ! echo "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "❌ Error: version must be in semver format (e.g., 0.1.1), got: $VERSION"
  exit 1
fi

TAG="v${VERSION}"

# ── Mode: --version (bump only, any branch) ─────────────────────────────
if [[ "$MODE" == "version" ]]; then
  if $FORCE; then
    echo "⚠️  --force is ignored in --version mode (no tagging involved)."
  fi

  echo "📝 Updating pyproject.toml version → $VERSION"
  if ! grep -q "^version = " pyproject.toml; then
    echo "❌ Error: 'version = ' line not found in pyproject.toml"
    exit 1
  fi

  CURRENT_VERSION=$(grep '^version' pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/')
  echo "   Current: $CURRENT_VERSION → New: $VERSION"

  if $DRY_RUN; then
    echo "[DRY RUN] Would update pyproject.toml and commit."
  else
    # Update pyproject.toml in-place (macOS + Linux compatible)
    if [[ "$OSTYPE" == "darwin"* ]]; then
      sed -i '' "s/^version = \".*\"/version = \"${VERSION}\"/" pyproject.toml
    else
      sed -i "s/^version = \".*\"/version = \"${VERSION}\"/" pyproject.toml
    fi

    git add pyproject.toml
    git commit -m "release: bump to ${VERSION}"

    echo ""
    echo "✅ Version bumped to $VERSION and committed on $(git rev-parse --abbrev-ref HEAD)."
    echo "   Run ./scripts/release.sh --tag $VERSION when ready to publish."
  fi
  exit 0
fi

# ── Mode: --tag (full release, main branch only) ───────────────────────
# ── Ensure we're on main ─────────────────────────────────────────────────
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$BRANCH" != "main" ]]; then
  echo "❌ Error: --tag requires 'main' branch. Current branch: $BRANCH"
  exit 1
fi

# ── Ensure working tree is clean ─────────────────────────────────────────
if [[ -n "$(git status --porcelain)" ]]; then
  echo "❌ Error: working tree is dirty. Commit or stash changes first."
  git status --short
  exit 1
fi

# ── Pull latest ──────────────────────────────────────────────────────────
echo "⬇️  Pulling latest main..."
git pull origin main

# ── Check if tag already exists ──────────────────────────────────────────
if git rev-parse "$TAG" >/dev/null 2>&1; then
  if $FORCE; then
    echo "⚠️  Tag $TAG already exists. --force supplied; overwriting."
    if $DRY_RUN; then
      echo "[DRY RUN] Would delete and recreate tag $TAG"
    else
      git tag -d "$TAG"
      git push origin ":refs/tags/$TAG" || true
    fi
  else
    echo "❌ Error: tag $TAG already exists. Use --force to overwrite."
    exit 1
  fi
fi

# ── Update version in pyproject.toml ─────────────────────────────────────
echo "📝 Updating pyproject.toml version → $VERSION"
if ! grep -q "^version = " pyproject.toml; then
  echo "❌ Error: 'version = ' line not found in pyproject.toml"
  exit 1
fi

CURRENT_VERSION=$(grep '^version' pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/')
echo "   Current: $CURRENT_VERSION → New: $VERSION"

# __init__.py derives __version__ from importlib.metadata — no need to patch it.
# Only pyproject.toml is the version source of truth.

if $DRY_RUN; then
  echo "[DRY RUN] Would update pyproject.toml, commit, tag $TAG, and push."
else
  # Update pyproject.toml in-place (macOS + Linux compatible)
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/^version = \".*\"/version = \"${VERSION}\"/" pyproject.toml
  else
    sed -i "s/^version = \".*\"/version = \"${VERSION}\"/" pyproject.toml
  fi

  # Commit
  git add pyproject.toml
  git commit -m "release: bump to ${VERSION}"

  # Tag
  git tag -a "$TAG" -m "Release ${TAG}"

  # Push commit + tag
  git push origin main
  git push origin "$TAG"

  echo ""
  echo "✅ Release $TAG pushed!"
  echo ""
  echo "   Watch workflows:"
  echo "   • PyPI:      https://github.com/nilayparikh/codefreedom/actions/workflows/pipy.yaml"
  echo "   • Docker:    https://github.com/nilayparikh/codefreedom/actions/workflows/publish-docker.yml"
  echo "   • Docs:      https://github.com/nilayparikh/codefreedom/actions/workflows/publish-docs.yml"
fi
