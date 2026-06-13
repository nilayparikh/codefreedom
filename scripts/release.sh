#!/usr/bin/env bash
# ── CodeFreedom Release Script ─────────────────────────────────────────────────
# Two modes:
#   --version  — update version in pyproject.toml and commit
#   --tag      — verify version files match, then tag v* and push
#
# Prerelease workflow:
#   ./scripts/release.sh --version 0.2.0 --pre-release --candidate 1
#   ./scripts/release.sh --tag 0.2.0 --pre-release --candidate 1
#
# Final release workflow:
#   ./scripts/release.sh --version 0.2.0
#   ./scripts/release.sh --tag 0.2.0
#
# Tag push triggers:
#   • PyPI publish + GitHub Release  (.github/workflows/pipy.yaml)
#
# ────────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Help ──────────────────────────────────────────────────────────────────
usage() {
  cat <<'EOF'
Usage:
  ./scripts/release.sh --version <X.Y.Z> [--pre-release] [--candidate <N>] [--dry-run]
  ./scripts/release.sh --tag     <X.Y.Z> [--pre-release] [--candidate <N>] [--dry-run] [--force]

Modes:
  -v, --version <X.Y.Z>    Update version in pyproject.toml and commit.
  -t, --tag     <X.Y.Z>    Verify version, tag v<version>, and push to origin.

Options:
  -p, --pre-release         Mark as prerelease. Builds PEP 440 version X.Y.ZrcN.
  -c, --candidate <N>       Release candidate number (1-10). Required with --pre-release.
  --dry-run                 Preview changes without committing or pushing.
  --force                   Overwrite an existing tag (only with --tag).
  -h, --help                Show this message.

Version resolution:
  --version 0.2.0                        → 0.2.0      (final)
  --version 0.2.0 --pre-release -c 1    → 0.2.0rc1   (prerelease)
  --version 0.2.0 --pre-release -c 10   → 0.2.0rc10  (prerelease)

Examples:
  # Prerelease (on rc-* branch):
  ./scripts/release.sh -v 0.2.0 -p -c 1               # bump to 0.2.0rc1
  ./scripts/release.sh -t 0.2.0 -p -c 1               # tag + push → PyPI prerelease

  # Final release (on main):
  ./scripts/release.sh -v 0.2.0                       # bump to 0.2.0
  ./scripts/release.sh -t 0.2.0                       # tag + push → PyPI + GitHub Release

  # Dry run / force:
  ./scripts/release.sh -t 0.2.0 --dry-run             # preview tagging
  ./scripts/release.sh -t 0.2.0 -p -c 1 --force       # overwrite existing RC tag
EOF
  exit 0
}

# ── Parse arguments ─────────────────────────────────────────────────────
DRY_RUN=false
FORCE=false
MODE=""
VERSION=""
PRE_RELEASE=false
CANDIDATE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h) usage ;;
    --dry-run) DRY_RUN=true; shift ;;
    --force)   FORCE=true; shift ;;
    --pre-release|-p) PRE_RELEASE=true; shift ;;
    --candidate|-c)
      shift
      if [[ $# -eq 0 || "$1" == -* ]]; then
        echo "Error: --candidate requires a number argument (1-10)."
        exit 1
      fi
      CANDIDATE="$1"
      shift
      ;;
    --version|-v)
      if [[ -n "$MODE" ]]; then echo "Error: specify only one mode (--version or --tag)."; exit 1; fi
      MODE="version"
      shift
      if [[ $# -eq 0 || "$1" == -* ]]; then echo "Error: --version requires a version argument (X.Y.Z)."; exit 1; fi
      VERSION="$1"
      shift
      ;;
    --tag|-t)
      if [[ -n "$MODE" ]]; then echo "Error: specify only one mode (--version or --tag)."; exit 1; fi
      MODE="tag"
      shift
      if [[ $# -eq 0 || "$1" == -* ]]; then echo "Error: --tag requires a version argument (X.Y.Z)."; exit 1; fi
      VERSION="$1"
      shift
      ;;
    *)
      echo "Error: unknown option: $1"
      usage
      ;;
  esac
done

if [[ -z "$MODE" ]]; then
  echo "Error: specify --version <X.Y.Z> or --tag <X.Y.Z>."
  usage
fi

# ── Validate base version (must be X.Y.Z, no suffix) ────────────────────
if ! echo "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "Error: version must be in X.Y.Z format (e.g., 0.2.0), got: $VERSION"
  exit 1
fi

# ── Validate prerelease flags ────────────────────────────────────────────
if [[ "$PRE_RELEASE" == true && -z "$CANDIDATE" ]]; then
  echo "Error: --pre-release requires --candidate <N> (1-10)."
  exit 1
fi

if [[ -n "$CANDIDATE" ]]; then
  PRE_RELEASE=true
  if ! echo "$CANDIDATE" | grep -qE '^[0-9]+$'; then
    echo "Error: --candidate must be a number, got: $CANDIDATE"
    exit 1
  fi
  if [[ "$CANDIDATE" -lt 1 || "$CANDIDATE" -gt 10 ]]; then
    echo "Error: --candidate must be between 1 and 10, got: $CANDIDATE"
    exit 1
  fi
fi

# ── Build full version string ────────────────────────────────────────────
IS_RC=false
if [[ "$PRE_RELEASE" == true ]]; then
  IS_RC=true
  FULL_VERSION="${VERSION}rc${CANDIDATE}"
else
  FULL_VERSION="$VERSION"
fi

TAG="v${FULL_VERSION}"

echo "📋 Version: $FULL_VERSION (tag: $TAG)"

# ── Mode: --version (update files + commit) ─────────────────────────────
if [[ "$MODE" == "version" ]]; then
  if $FORCE; then
    echo "Warning: --force is ignored in --version mode."
  fi

  echo "📝 Updating pyproject.toml → $FULL_VERSION"
  if ! grep -q "^version = " pyproject.toml; then
    echo "Error: 'version = ' line not found in pyproject.toml"
    exit 1
  fi

  CURRENT_VERSION=$(grep '^version' pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/')
  echo "   Current: $CURRENT_VERSION → New: $FULL_VERSION"

  if $DRY_RUN; then
    if [[ "$CURRENT_VERSION" == "$FULL_VERSION" ]]; then
      echo "[DRY RUN] Version already at $FULL_VERSION — nothing to commit."
    else
      echo "[DRY RUN] Would update pyproject.toml and commit."
    fi
  else
    if [[ "$CURRENT_VERSION" == "$FULL_VERSION" ]]; then
      echo "   Version already at $FULL_VERSION — nothing to do."
    else
      # Update pyproject.toml in-place (macOS + Linux compatible)
      if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/^version = \".*\"/version = \"${FULL_VERSION}\"/" pyproject.toml
      else
        sed -i "s/^version = \".*\"/version = \"${FULL_VERSION}\"/" pyproject.toml
      fi

      git add pyproject.toml
      git commit -m "release: bump to ${FULL_VERSION}"

      echo ""
      echo "Version bumped to $FULL_VERSION and committed on $(git rev-parse --abbrev-ref HEAD)."
      echo "   Run ./scripts/release.sh --tag $VERSION$( $IS_RC && echo " -p -c $CANDIDATE" ) when ready to publish."
    fi
  fi
  exit 0
fi

# ── Mode: --tag (verify files, then tag + push) ─────────────────────────
# ── Branch validation: RC tags on rc-* branches, final tags on main ────
BRANCH=$(git rev-parse --abbrev-ref HEAD)

if $IS_RC; then
  if [[ "$BRANCH" != rc-* ]]; then
    echo "Error: RC tags require an 'rc-*' branch. Current branch: $BRANCH"
    exit 1
  fi
else
  if [[ "$BRANCH" != "main" ]]; then
    echo "Error: final release tags require 'main' branch. Current branch: $BRANCH"
    exit 1
  fi
fi

# ── Ensure working tree is clean ─────────────────────────────────────────
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Error: working tree is dirty. Commit or stash changes first."
  git status --short
  exit 1
fi

# ── Pull latest ──────────────────────────────────────────────────────────
echo "⬇️  Pulling latest $BRANCH..."
git pull origin "$BRANCH"

# ── Verify pyproject.toml version matches requested tag ────────────────
echo "🔍 Verifying version files match $FULL_VERSION ..."

if ! grep -q "^version = " pyproject.toml; then
  echo "Error: 'version = ' line not found in pyproject.toml"
  exit 1
fi

FILE_VERSION=$(grep '^version' pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/')

if [[ "$FILE_VERSION" != "$FULL_VERSION" ]]; then
  echo "Error: pyproject.toml has version $FILE_VERSION, but tag wants $FULL_VERSION."
  echo "   Run './scripts/release.sh --version $VERSION$( $IS_RC && echo " -p -c $CANDIDATE" )' first."
  exit 1
fi

echo "   pyproject.toml: $FILE_VERSION ✓"

# ── Check if tag already exists ──────────────────────────────────────────
if git rev-parse "$TAG" >/dev/null 2>&1; then
  if $FORCE; then
    echo "Warning: Tag $TAG already exists. --force supplied; overwriting."
    if $DRY_RUN; then
      echo "[DRY RUN] Would delete and recreate tag $TAG"
    else
      git tag -d "$TAG"
      git push origin ":refs/tags/$TAG" || true
    fi
  else
    echo "Error: tag $TAG already exists. Use --force to overwrite."
    exit 1
  fi
fi

if $DRY_RUN; then
  echo "[DRY RUN] Would tag HEAD as $TAG and push."
else
  # Tag
  echo "🏷️  Tagging HEAD as $TAG ..."
  if $IS_RC; then
    git tag -a "$TAG" -m "Pre-release ${TAG}"
  else
    git tag -a "$TAG" -m "Release ${TAG}"
  fi

  # Push commit + tag
  git push origin "$BRANCH"
  git push origin "$TAG"

  echo ""
  echo "Release $TAG pushed!"
  echo ""
  echo "   Watch workflows:"
  echo "   • PyPI:  https://github.com/nilayparikh/codefreedom/actions/workflows/pipy.yaml"
fi
