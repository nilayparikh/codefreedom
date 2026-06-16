#!/usr/bin/env bash
set -euo pipefail

FORK="https://github.com/nilayparikh/litellm.git"
UPSTREAM="https://github.com/BerriAI/litellm.git"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMP_DIR="${SCRIPT_DIR}/.temp"

usage() {
  echo "Usage: $0 --tag <version-tag>"
  echo "Example: $0 --tag v1.89.1"
  exit 1
}

cleanup() {
  if [ -d "${TEMP_DIR}" ]; then
    echo "[CLEANUP] Removing ${TEMP_DIR}..."
    rm -rf "${TEMP_DIR}"
    echo "[OK] Temporary directory cleaned up."
  fi
}

TAG=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --tag) TAG="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

if [ -z "${TAG}" ]; then
  echo "Error: --tag is required."
  usage
fi

trap cleanup EXIT

echo "[SETUP] Cloning fork into ${TEMP_DIR}..."
rm -rf "${TEMP_DIR}"
mkdir -p "${TEMP_DIR}"
git clone --origin origin "${FORK}" "${TEMP_DIR}"

cd "${TEMP_DIR}"

echo "[UPSTREAM] Adding upstream remote..."
git remote add upstream "${UPSTREAM}"

echo "[FETCH] Fetching upstream tags..."
git fetch upstream --tags

if ! git rev-parse "${TAG}" >/dev/null 2>&1; then
  git fetch upstream tag "${TAG}"
fi

if ! git cat-file -t "$(git rev-parse "${TAG}^{commit}")" >/dev/null 2>&1; then
  echo "[ERROR] Tag '${TAG}' does not exist upstream."
  exit 1
fi

BRANCH_NAME="sync/${TAG}"
echo "[SYNC] Creating branch ${BRANCH_NAME} from tag ${TAG}..."
git checkout -b "${BRANCH_NAME}" "${TAG}"

echo "[PUSH] Pushing ${BRANCH_NAME} to fork..."
git push origin "${BRANCH_NAME}"

echo "[TAG] Pushing tag ${TAG} to fork..."
git push origin "${TAG}"

echo "[VERIFY] Checking tag on fork..."
git fetch origin --tags
if git rev-parse "${TAG}" >/dev/null 2>&1; then
  echo "[OK] Tag '${TAG}' is now available on fork."
else
  echo "[FAIL] Tag '${TAG}' not found on fork after push."
  exit 1
fi

echo ""
echo "[DONE] Tag ${TAG} synced to fork successfully. Temp directory cleaned up."
