"""Update checker — checks CodeFreedom Docker images and PyPI package for updates.

Usage:
    codefreedom manage update [service...]
    cf manage update
    cf upd

Discovers CodeFreedom images from the local Docker cache and profiles,
then compares local digests against the Docker Hub registry.
Also checks the installed PyPI package version.

Services (filter which images to check):
    chrome     Chrome browser tool image
    web        Web search tool image
    proxy      LiteLLM proxy and web-bridge images
    tools      Chrome + Web + GitHub MCP tool images (shortcut)
    all        Everything (default)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

from codefreedom.core.http_client import (
    HTTPError,
    HTTPStatusError,
    get_json,
    get_response,
)
from codefreedom.core.config import get_config_dir
from codefreedom.docker.pull import get_local_digest, normalize_ref, parse_image_ref
from codefreedom.log import eprint, tag

# ── Constants ──────────────────────────────────────────────────────────────────

PYPI_PACKAGE = "codefreedom"
PYPI_URL = f"https://pypi.org/pypi/{PYPI_PACKAGE}/json"

DOCKER_HUB_AUTH = "https://auth.docker.io/token"
DOCKER_HUB_REGISTRY = "registry-1.docker.io"
IMAGE_NAMESPACE = "nilayparikh"
IMAGE_REPO = "codefreedom"

# Known service descriptions for display
_SERVICE_DESCRIPTIONS: dict[str, str] = {
    "chrome": "tool: chrome",
    "web": "tool: web",
    "github": "tool: github",
    "litellm": "proxy: litellm",
    "web-bridge": "proxy: web-bridge",
}

# ── Helpers ───────────────────────────────────────────────────────────────────


def _read_yaml(path: Path) -> dict[str, Any] | None:
    """Read a YAML file safely. Returns None on any error."""
    if not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        return None


def _parse_compose_image(value: str) -> str | None:
    """Extract the default image reference from a docker-compose image value.

    Handles ``${VAR:-default}`` substitution and plain values.
    Returns None if the value is empty or malformed.
    """
    if not value or not value.strip():
        return None
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1]
    match = re.match(r"\$\{[^:]*:-(.+)\}", value)
    if match:
        extracted = match.group(1).strip()
        if (extracted.startswith('"') and extracted.endswith('"')) or (
            extracted.startswith("'") and extracted.endswith("'")
        ):
            extracted = extracted[1:-1]
        return extracted
    return value


def _local_images() -> list[str]:
    """Return locally-pulled CodeFreedom images.

    Only checks ``nilayparikh/codefreedom:*`` (Docker strips the
    ``docker.io/`` prefix on pull).  No GHCR, no bare ``codefreedom:*``.
    """
    if not _docker_available():
        return []
    result = subprocess.run(
        [
            "docker",
            "images",
            "--filter",
            f"reference={IMAGE_NAMESPACE}/{IMAGE_REPO}*",
            "--format",
            "{{.Repository}}:{{.Tag}}",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _image_exists_locally(image: str) -> bool:
    """Check if a Docker image exists in the local cache.

    Normalizes the reference (strips ``docker.io/``) so Docker's local
    naming matches.
    """
    normalized = normalize_ref(image)
    result = subprocess.run(
        ["docker", "image", "inspect", normalized],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return result.returncode == 0


def _get_remote_digest(image: str) -> str | None:
    """Get the remote manifest digest from Docker Hub.

    Returns the SHA256 digest string or None on failure.
    """
    registry, namespace, repo, tag = parse_image_ref(image)

    # Bare references (no registry prefix) - skip remote check
    if not registry:
        return None

    # Only check Docker Hub
    if registry not in ("docker.io", DOCKER_HUB_REGISTRY):
        return None

    ns = namespace or "library"
    return _fetch_docker_hub_manifest(ns, repo, tag)


def _fetch_docker_hub_manifest(namespace: str, repo: str, tag: str) -> str | None:
    """Fetch manifest digest from Docker Hub."""
    token = _get_docker_hub_token(namespace, repo)
    if not token:
        return None

    url = f"https://{DOCKER_HUB_REGISTRY}/v2/{namespace}/{repo}/manifests/{tag}"
    return _fetch_manifest_digest(url, token, "Docker Hub")


def _fetch_manifest_digest(url: str, token: str, _label: str) -> str | None:
    """Make a manifest request and return the raw SHA256 hex digest."""
    try:
        resp = get_response(
            url,
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
    except HTTPStatusError as exc:
        eprint(
            f"[UPDATE] Warning: Hub manifest check failed ({exc.status_code}): {url}."
        )
    except HTTPError as exc:
        eprint(f"{tag('UPDATE')} Warning: Hub unreachable ({exc}): {url}.")
    return None


def _get_docker_hub_token(namespace: str, repo: str) -> str | None:
    """Get a Docker Hub registry auth token."""
    scope = f"repository:{namespace}/{repo}:pull"
    url = f"{DOCKER_HUB_AUTH}?service=registry.docker.io&scope={scope}"
    try:
        data = get_json(url, timeout=10.0)
        return data.get("token")
    except (HTTPError, json.JSONDecodeError) as exc:
        eprint(f"{tag('UPDATE')} Warning: Docker Hub auth failed: {exc}.")
    return None


def _is_latest_tag(tag: str) -> bool:
    """Return True if the tag is a ``-latest`` variant."""
    return tag == "latest" or tag.endswith("-latest")


def _is_bare_ref(image: str) -> bool:
    """Return True if the image reference has no registry prefix."""
    if "/" not in image:
        return True
    first_seg = image.split("/")[0]
    if first_seg == "docker.io":
        return False
    if "." in first_seg or ":" in first_seg:
        return False
    return False


# ── Image Discovery ───────────────────────────────────────────────────────────


def discover_images() -> list[dict[str, str]]:
    """Discover CodeFreedom images from local Docker cache and match to profiles.

    Only returns images that are actually pulled locally.
    Enriches them with service/source metadata from profiles.

    Returns a list of dicts, each with keys:
        image, source, service
    """
    pulled = _local_images()
    if not pulled:
        return []

    config_dir = get_config_dir()
    images: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(img: str, source: str, service: str) -> None:
        if not img:
            return
        key = f"{img}|{service}"
        if key not in seen:
            seen.add(key)
            images.append({"image": img, "source": source, "service": service})

    # Build a lookup of (normalized image ref) -> (original, source, service)
    profile_images: dict[str, tuple[str, str, str]] = {}

    def _add_profile(img: str, source: str, service: str) -> None:
        """Register a profile image, normalizing its key for Docker matching."""
        if not img or not _is_managed_image(img):
            return
        norm = normalize_ref(img)
        # Only register the first source for each normalized image
        if norm not in profile_images:
            profile_images[norm] = (img, source, service)

    # 1. Unified profiles.yaml — extract tools
    profiles_data = _read_yaml(config_dir / "profiles.yaml")
    if profiles_data:
        tools_section = profiles_data.get("tools", {})
        if isinstance(tools_section, dict):
            for tname, tdef in tools_section.items():
                if isinstance(tdef, dict):
                    _add_profile(
                        tdef.get("image", ""),
                        "profiles.yaml",
                        tname,
                    )

    # 2. proxy docker-compose.yaml
    compose_path = config_dir / "proxy" / "docker-compose.yaml"
    if compose_path.exists():
        try:
            text = compose_path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        in_services = False
        current_service: str | None = None
        for line in text.splitlines():
            stripped = line.strip()
            indent = len(line) - len(line.lstrip())
            if stripped == "services:" and indent == 0:
                in_services = True
                continue
            if not in_services:
                continue
            if indent == 0 and stripped and not stripped.startswith("#"):
                in_services = False
                continue
            if indent == 2 and stripped and not stripped.startswith("#"):
                svc_match = re.match(r"^([a-zA-Z0-9_-]+):", stripped)
                if svc_match:
                    current_service = svc_match.group(1)
                    continue
            if indent == 4 and current_service and stripped.startswith("image:"):
                img_raw = stripped[len("image:") :].strip()
                img = _parse_compose_image(img_raw)
                if img:
                    _add_profile(img, "proxy/docker-compose.yaml", current_service)

    # Match pulled images against profile images
    for pulled_img in pulled:
        if pulled_img in profile_images:
            orig, src, svc = profile_images[pulled_img]
            _add(orig, src, svc)
        else:
            _add(pulled_img, "docker cache", "unknown")

    return images


def _is_managed_image(image: str) -> bool:
    """Return True if the image is a codefreedom-managed image."""
    return IMAGE_REPO in image and IMAGE_NAMESPACE in image


# ─── Registry checks ─────────────────────────────────────────────────────────


def check_image(image_ref: dict[str, str]) -> dict[str, Any]:
    """Check a single image against the registry, returning status.

    Returns a dict with keys:
        image, source, service, status, description, message
    """
    image = image_ref["image"]
    source = image_ref["source"]
    service = image_ref["service"]
    desc = _SERVICE_DESCRIPTIONS.get(service, service)

    if _is_bare_ref(image):
        return {
            "image": image,
            "source": source,
            "service": service,
            "description": desc,
            "status": "bare",
            "message": f"no registry prefix -- edit {source}",
        }

    # Image must exist locally (discover_images already guarantees this)
    tag = parse_image_ref(image)[3]
    is_latest = _is_latest_tag(tag)

    local_digest = get_local_digest(image)
    if local_digest is None:
        return {
            "image": image,
            "source": source,
            "service": service,
            "description": desc,
            "status": "ok",
            "message": "locally built -- no repo digest",
        }

    remote_digest = _get_remote_digest(image)

    if remote_digest is None:
        return {
            "image": image,
            "source": source,
            "service": service,
            "description": desc,
            "status": "ok",
            "message": "cached (remote unavailable)",
        }

    if local_digest == remote_digest:
        if is_latest:
            return {
                "image": image,
                "source": source,
                "service": service,
                "description": desc,
                "status": "ok",
                "message": "up to date",
            }
        else:
            return {
                "image": image,
                "source": source,
                "service": service,
                "description": desc,
                "status": "pinned",
                "message": f"pinned to '{tag}' -- use :{tag.split('-')[0] + '-latest' if '-' in tag else 'latest'} for auto-updates",
            }
    else:
        if is_latest:
            return {
                "image": image,
                "source": source,
                "service": service,
                "description": desc,
                "status": "new",
                "message": f"docker pull {image}",
            }
        else:
            return {
                "image": image,
                "source": source,
                "service": service,
                "description": desc,
                "status": "pinned",
                "message": f"pinned to '{tag}' -- use :{tag.split('-')[0] + '-latest' if '-' in tag else 'latest'} for auto-updates",
            }


# ─── PyPI check ──────────────────────────────────────────────────────────────


def _parse_version(version_str: str) -> tuple[int, ...]:
    """Parse version string into comparable tuple, handling pre-release tags."""
    rc_match = re.search(r"(rc|alpha|beta|a|b)(\d+)$", version_str)
    pre_release = 0 if rc_match else 1
    base = re.split(r"[^0-9]+", re.split(r"(rc|alpha|beta|a|b)", version_str)[0])
    parts = tuple(int(p) for p in base if p)
    return parts + (pre_release,)


def check_pypi() -> dict[str, Any] | None:
    """Check the installed codefreedom package version against PyPI."""
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:
        local_version = "unknown"

    else:
        try:
            local_version = version(PYPI_PACKAGE)
        except PackageNotFoundError:
            local_version = "unknown"

    try:
        data = get_json(PYPI_URL, timeout=10.0)
        remote_version = data["info"]["version"]
    except (HTTPError, json.JSONDecodeError):
        return {
            "local_version": local_version,
            "remote_version": "unknown",
            "status": "unknown",
            "message": "could not reach PyPI",
        }

    if local_version == remote_version:
        return {
            "local_version": local_version,
            "remote_version": remote_version,
            "status": "ok",
            "message": "up to date",
        }

    local_parsed = _parse_version(local_version)
    remote_parsed = _parse_version(remote_version)

    if remote_parsed > local_parsed:
        is_prerelease = re.search(r"(rc|alpha|beta|a|b)\d+", remote_version)
        if is_prerelease:
            uv_cmd = (
                f"uv tool upgrade {PYPI_PACKAGE}=={remote_version} --prerelease=allow"
            )
        else:
            uv_cmd = f"uv tool upgrade {PYPI_PACKAGE}=={remote_version}"
        pip_cmd = f"pip install --upgrade {PYPI_PACKAGE}=={remote_version}"
        return {
            "local_version": local_version,
            "remote_version": remote_version,
            "status": "new",
            "uv_cmd": uv_cmd,
            "pip_cmd": pip_cmd,
        }
    else:
        return {
            "local_version": local_version,
            "remote_version": remote_version,
            "status": "ok",
            "message": "up to date",
        }


# ─── Display ─────────────────────────────────────────────────────────────────


def _display_results(
    image_results: list[dict[str, Any]],
    pypi_result: dict[str, Any] | None,
) -> None:
    """Print the update check results as a clean ASCII table."""

    # ── Docker Images section ───────────────────────────────────────────
    if image_results:
        print("images")
        print("------")
        for r in image_results:
            status = r["status"]
            img = r["image"]
            desc = r["description"]

            if status == "ok":
                sym = " [ok]"
            elif status == "new":
                sym = "[upd]"
            elif status == "pinned":
                sym = "[pin]"
            elif status == "bare":
                sym = "[bad]"
            else:
                sym = "[???]"

            print(f"  {sym}  {img}")
            print(f"        {desc}")

            if status == "new":
                print(f"        run: {r['message']}")
            elif status == "pinned":
                print(f"        {r['message']}")
            elif status == "bare":
                print(f"        {r['message']}")

        print()

    # ── PyPI section ────────────────────────────────────────────────────
    if pypi_result:
        print("pypi")
        print("----")
        if pypi_result["status"] == "ok":
            print(f"  [ok]  codefreedom {pypi_result['local_version']} (latest)")
            print()
        elif pypi_result["status"] == "new":
            print(f" [upd]  codefreedom {pypi_result['local_version']}")
            print(
                f"        {pypi_result['uv_cmd']}  ({pypi_result['remote_version']} available)"
            )
            print()
        else:
            print(
                f"  [??]  codefreedom {pypi_result['local_version']} ({pypi_result['message']})"
            )
            print()

    # ── Summary ─────────────────────────────────────────────────────────
    if image_results:
        counts: dict[str, int] = {}
        for r in image_results:
            counts[r["status"]] = counts.get(r["status"], 0) + 1

        parts = []
        if counts.get("ok", 0):
            parts.append(f"{counts['ok']} up to date")
        if counts.get("new", 0):
            parts.append(
                f"{counts['new']} update{'s' if counts['new'] != 1 else ''} available"
            )
        if counts.get("pinned", 0):
            parts.append(f"{counts['pinned']} pinned")
        if counts.get("bare", 0):
            parts.append(f"{counts['bare']} broken ref")

        if parts:
            print("summary: " + ", ".join(parts))

    # ── Tips ────────────────────────────────────────────────────────────
    tips = []
    if any(r["status"] == "new" for r in image_results):
        tips.append("Run 'docker pull <image>' for each [upd] entry")
    if any(r["status"] == "bare" for r in image_results):
        tips.append("Broken refs: add docker.io/nilayparikh/ prefix in the profile")
    if any(r["status"] == "pinned" for r in image_results):
        tips.append("Pinned tags: switch to -latest for auto-updates")
    if pypi_result and pypi_result.get("status") == "new":
        tips.append(f"PyPI: {pypi_result['uv_cmd']}")
        tips.append(f"     pip: {pypi_result['pip_cmd']}")

    if tips:
        print()
        print("tips:")
        for t in tips:
            print(f"  * {t}")


def _docker_available() -> bool:
    """Check if the Docker CLI is reachable."""
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.SubprocessError):
        return False


# ─── Filter by service ────────────────────────────────────────────────────────


def _filter_by_service(
    images: list[dict[str, str]], services: list[str]
) -> list[dict[str, str]]:
    """Filter image list by requested service names."""
    if not services or "all" in services:
        return images

    service_map: dict[str, list[str]] = {
        "chrome": ["chrome"],
        "web": ["web"],
        "litellm": ["litellm"],
        "web-bridge": ["web-bridge"],
        "proxy": ["litellm", "web-bridge"],
        "tools": ["chrome", "web", "github"],
    }

    matched = []
    seen_keys: set[str] = set()
    for svc in services:
        prefixes = service_map.get(svc, [svc])
        for img in images:
            key = f"{img['image']}|{img['service']}"
            if key in seen_keys:
                continue
            for prefix in prefixes:
                if img["service"].startswith(prefix):
                    seen_keys.add(key)
                    matched.append(img)
                    break
    return matched


# ─── Entry point ──────────────────────────────────────────────────────────────


def run(args: argparse.Namespace) -> int:
    """Run the update check. Entry point from main dispatch."""
    services = getattr(args, "services", None) or []

    all_images = discover_images()
    images = _filter_by_service(all_images, services)

    image_results = [check_image(img) for img in images]
    pypi_result = check_pypi()

    _display_results(image_results, pypi_result)
    return 0


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Check CodeFreedom for updates")
    p.add_argument("services", nargs="*", help="Services to check")
    run(p.parse_args())
