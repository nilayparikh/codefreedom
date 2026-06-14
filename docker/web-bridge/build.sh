#!/usr/bin/env bash
# ── CodeFreedom Web Bridge — Multi-arch Build + Push ─────────────────────────
# Builds linux/amd64 + linux/arm64 images via docker buildx and pushes to
# Docker Hub and (optionally) GitHub Container Registry.
#
# Usage:
#   ./docker/web-bridge/build.sh                   # build + push to both registries
#   ./docker/web-bridge/build.sh --load             # single-arch, load into local docker
#   ./docker/web-bridge/build.sh --push --ghcr      # push to both docker.io and ghcr.io
#   ./docker/web-bridge/build.sh --dry-run          # show commands without executing
#
# Requires: docker (with buildx plugin), logged in to target registries.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKERFILE="${SCRIPT_DIR}/Dockerfile.Bridge"
CONTEXT="${SCRIPT_DIR}"

DOCKER_HUB_REPO="docker.io/nilayparikh/codefreedom"
GHCR_REPO="ghcr.io/nilayparikh/codefreedom"
BUILDER_NAME="cf-web-bridge-builder"
PLATFORMS="linux/amd64,linux/arm64"

DRY_RUN=false
PUSH=true
USE_GHCR=false
LOAD=false

# ── Parse args ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)  DRY_RUN=true; shift ;;
        --push)     PUSH=true; shift ;;
        --no-push)  PUSH=false; shift ;;
        --ghcr)     USE_GHCR=true; shift ;;
        --load)     LOAD=true; PUSH=false; shift ;;
        -h|--help)
            sed -n '2,/^# ─/{ /^#/s/^# \{0,1\}//p }' "$0"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ── Extract version from Dockerfile ──────────────────────────────────────────
VERSION=$(grep '^ARG IMAGE_VERSION=' "$DOCKERFILE" | head -1 | sed 's/.*=\(.*\)/\1/')
MAJOR_MINOR=$(echo "${VERSION}" | cut -d. -f1,2)

if [[ -z "$VERSION" ]]; then
    echo "ERROR: Could not extract IMAGE_VERSION from ${DOCKERFILE}" >&2
    exit 1
fi

echo "Version:    v${VERSION}"
echo "Major.Minor: v${MAJOR_MINOR}"
echo "Platforms:  ${PLATFORMS}"
echo "Push:       ${PUSH}"
echo "GHCR:       ${USE_GHCR}"
echo "Load local: ${LOAD}"
echo ""

# ── Build tag list ───────────────────────────────────────────────────────────
TAGS=()
TAGS+=("-t" "${DOCKER_HUB_REPO}:web-bridge-v${VERSION}")
TAGS+=("-t" "${DOCKER_HUB_REPO}:web-bridge-v${MAJOR_MINOR}")
TAGS+=("-t" "${DOCKER_HUB_REPO}:web-bridge-latest")

if [[ "$USE_GHCR" == true ]]; then
    TAGS+=("-t" "${GHCR_REPO}:web-bridge-v${VERSION}")
    TAGS+=("-t" "${GHCR_REPO}:web-bridge-v${MAJOR_MINOR}")
    TAGS+=("-t" "${GHCR_REPO}:web-bridge-latest")
fi

# ── Helper ───────────────────────────────────────────────────────────────────
run() {
    echo "+ $*"
    if [[ "$DRY_RUN" == false ]]; then
        "$@"
    fi
}

# ── Ensure buildx builder exists ─────────────────────────────────────────────
if [[ "$LOAD" == true ]]; then
    # --load only works with a single platform; default to host arch.
    PLATFORMS="linux/$(uname -m)"
    echo "Single-platform load mode: ${PLATFORMS}"
    echo ""
fi

if [[ "$DRY_RUN" == false ]]; then
    if ! docker buildx inspect "${BUILDER_NAME}" &>/dev/null; then
        echo "Creating buildx builder '${BUILDER_NAME}'..."
        docker buildx create --name "${BUILDER_NAME}" --driver docker-container --use
    else
        docker buildx use "${BUILDER_NAME}"
    fi
fi

# ── Build (and optionally push) ──────────────────────────────────────────────
BUILD_CMD=(
    docker buildx build
    --platform "${PLATFORMS}"
    --build-arg "IMAGE_VERSION=${VERSION}"
    "${TAGS[@]}"
    -f "${DOCKERFILE}"
    "${CONTEXT}"
)

if [[ "$PUSH" == true ]]; then
    BUILD_CMD+=(--push)
elif [[ "$LOAD" == true ]]; then
    BUILD_CMD+=(--load)
else
    BUILD_CMD+=(--output type=docker)
fi

echo "Building..."
run "${BUILD_CMD[@]}"

echo ""
echo "Done. Tags:"
for t in "${TAGS[@]}"; do
    [[ "$t" == "-t" ]] && continue
    echo "  ${t}"
done
