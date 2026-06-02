#!/usr/bin/env bash
# ── CodeFreedom Release Script ─────────────────────────────────────────────────
# Creates a version tag and pushes it to trigger:
#   • PyPI publish      (.github/workflows/pipy.yaml)
#   • Docker publish    (.github/workflows/publish-docker.yml)
#   • Docs publish      (.github/workflows/publish-docs.yml)
#
# Usage:
#   ./scripts/release.sh 0.1.1              # Set version and tag v0.1.1
#   ./scripts/release.sh 0.1.1 --dry-run    # Preview without pushing
#   ./scripts/release.sh 0.2.0 --force      # Overwrite existing tag
#
# The script updates pyproject.toml version, commits, tags, and pushes.
# All three publish workflows trigger on: tags: ["v*"]
# ────────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Help ──────────────────────────────────────────────────────────────────
usage() {
  cat <<'EOF'
Usage: ./scripts/release.sh <version> [--dry-run] [--force]

  <version>   Semantic version (e.g., 0.1.1). A "v" prefix is added automatically.

Options:
  --dry-run   Preview changes without pushing.
  --force     Overwrite an existing tag (uses --force on git tag).
  --help      Show this message.

Examples:
  ./scripts/release.sh 0.1.1
  ./scripts/release.sh 0.2.0 --dry-run
  ./scripts/release.sh 0.1.1 --force
EOF
  exit 0
}

# ── Parse arguments ─────────────────────────────────────────────────────
DRY_RUN=false
FORCE=false
VERSION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h) usage ;;
    --dry-run) DRY_RUN=true; shift ;;
    --force)   FORCE=true; shift ;;
    -*)
      echo "❌ Unknown option: $1"
      usage
      ;;
    *)
      if [[ -z "$VERSION" ]]; then
        VERSION="$1"
        shift
      else
        echo "❌ Unexpected argument: $1"
        usage
      fi
      ;;
  esac
done

if [[ -z "$VERSION" ]]; then
  echo "❌ Error: version is required."
  usage
fi

# Validate semver-like format
if ! echo "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "❌ Error: version must be in semver format (e.g., 0.1.1), got: $VERSION"
  exit 1
fi

TAG="v${VERSION}"

# ── Ensure we're on main ─────────────────────────────────────────────────
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$BRANCH" != "main" ]]; then
  echo "❌ Error: must be on 'main' branch. Current branch: $BRANCH"
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
