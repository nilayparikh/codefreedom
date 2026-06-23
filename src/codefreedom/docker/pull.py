"""Digest-based image pull — only pulls when remote has a newer manifest.

Compares local vs remote digests before pulling. Falls back gracefully
if the registry is unreachable (uses cached image).
"""

from __future__ import annotations

import json
import subprocess

from codefreedom.core.http_client import (
    HTTPError,
    HTTPStatusError,
    get_json,
    get_response,
)
from codefreedom.log import eprint

DOCKER_HUB_AUTH = "https://auth.docker.io/token"
DOCKER_HUB_REGISTRY = "registry-1.docker.io"


def _normalize_ref(image: str) -> str:
    """Strip the default ``docker.io/`` prefix."""
    if image.startswith("docker.io/"):
        return image[len("docker.io/"):]
    return image


def _parse_image_ref(image: str) -> tuple[str, str, str, str]:
    """Parse an image reference into (registry, namespace, repo, tag)."""
    rest = image
    registry = ""
    if "/" in image:
        parts = image.split("/", 1)
        if "." in parts[0] or ":" in parts[0] or parts[0] in ("docker.io",):
            registry = parts[0]
            rest = parts[1]

    if ":" in rest:
        rest_part, tag = rest.rsplit(":", 1)
    else:
        rest_part, tag = rest, "latest"

    if "/" in rest_part:
        namespace, repo = rest_part.split("/", 1)
    else:
        namespace = ""
        repo = rest_part

    return registry, namespace, repo, tag


def _get_local_digest(image: str) -> str | None:
    """Get the locally cached manifest digest for an image."""
    normalized = _normalize_ref(image)
    result = subprocess.run(
        ["docker", "image", "inspect", normalized, "--format", "{{json .RepoDigests}}"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        digests = json.loads(result.stdout.strip())
        for d in digests:
            if "@sha256:" in d:
                return d.split("@sha256:")[1]
    except (json.JSONDecodeError, IndexError, AttributeError):
        pass
    return None


def _get_remote_digest(image: str) -> str | None:
    """Get the remote manifest digest from Docker Hub."""
    registry, namespace, repo, tag = _parse_image_ref(image)

    if not registry:
        return None

    if registry not in ("docker.io", DOCKER_HUB_REGISTRY):
        return None

    ns = namespace or "library"
    scope = f"repository:{ns}/{repo}:pull"
    url = f"{DOCKER_HUB_AUTH}?service=registry.docker.io&scope={scope}"
    try:
        data = get_json(url, timeout=10.0)
        token = data.get("token")
    except (HTTPError, json.JSONDecodeError):
        return None

    if not token:
        return None

    manifest_url = f"https://{DOCKER_HUB_REGISTRY}/v2/{ns}/{repo}/manifests/{tag}"
    try:
        resp = get_response(
            manifest_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": (
                    "application/vnd.docker.distribution.manifest.v2+json,"
                    " application/vnd.oci.image.manifest.v1+json,"
                    " application/vnd.docker.distribution.manifest.list.v2+json,"
                    " application/vnd.oci.image.index.v1+json"
                ),
            },
            timeout=15.0,
        )
        digest = resp.headers.get("Docker-Content-Digest")
        if digest:
            return digest.strip().removeprefix("sha256:")
    except (HTTPStatusError, HTTPError):
        pass
    return None


def _is_latest_tag(tag: str) -> bool:
    """Return True if the tag is a ``-latest`` variant."""
    return tag == "latest" or tag.endswith("-latest")


def digests_differ(image: str) -> bool:
    """Check if local and remote digests differ for an image.

    Returns True if an update is available, False if up-to-date or
    unable to determine (registry unreachable, locally built, etc.).
    """
    tag = _parse_image_ref(image)[3]
    if not _is_latest_tag(tag):
        return False

    local_digest = _get_local_digest(image)
    if local_digest is None:
        return False

    remote_digest = _get_remote_digest(image)
    if remote_digest is None:
        return False

    return local_digest != remote_digest


def pull_if_stale(image: str, label: str = "IMAGE") -> bool:
    """Pull an image only if the remote digest differs from local.

    Returns True if an image was pulled, False if already up-to-date
    or unable to check.
    """
    if not digests_differ(image):
        return False

    eprint(f"[{label}] New version available for '{image}', pulling...")
    result = subprocess.run(
        ["docker", "pull", image],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        eprint(f"[{label}] Pull failed for '{image}'.")
        if result.stderr:
            eprint(f"   {result.stderr.strip()}")
        return False

    eprint(f"[{label}] Updated '{image}'.")
    return True
