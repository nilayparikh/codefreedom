"""Docker client adapter wrapping docker-py.

Provides a single seam for all Docker operations currently scattered as raw
subprocess.run(["docker", ...]) calls across 13+ files.

If the Docker daemon socket is unavailable (e.g., Docker not installed),
all operations raise DockerUnavailableError with a clear message.
"""

from __future__ import annotations

import docker as _docker  # type: ignore[import-untyped]
from docker.errors import DockerException, NotFound  # type: ignore[import-untyped]


class DockerUnavailableError(RuntimeError):
    """Raised when the Docker daemon socket is unreachable."""


class _LazyClient:
    """Lazy singleton — docker.from_env() is called on first use."""

    def __init__(self) -> None:
        self._client: object | None = None

    def _get(self):
        if self._client is None:
            try:
                self._client = _docker.from_env()
            except DockerException as exc:
                raise DockerUnavailableError(
                    "Docker daemon is not reachable. "
                    "Is Docker installed and running? "
                    "Original error: " + str(exc)
                ) from exc
        return self._client

    def __getattr__(self, name: str):
        return getattr(self._get(), name)


_client = _LazyClient()


def ensure_image(image: str) -> None:
    """Pull a Docker image if it is not cached locally or is stale.

    Compares local vs remote digests before pulling to avoid unnecessary
    downloads. Falls back to cache if the registry is unreachable.
    """
    from codefreedom.docker.pull import pull_if_stale

    try:
        _client.images.get(image)
    except Exception:
        _client.images.pull(image)
        return

    pull_if_stale(image)


def container_is_running(name: str) -> bool:
    """Return True if a container with the given name is running."""
    try:
        c = _client.containers.get(name)
        return c.status == "running"
    except NotFound:
        return False


def container_exists(name: str) -> bool:
    """Return True if a container with the given name exists (any status)."""
    try:
        _client.containers.get(name)
        return True
    except NotFound:
        return False


def stop_container(name: str, timeout: int = 15) -> None:
    """Stop a running container by name. No-op if not found."""
    try:
        c = _client.containers.get(name)
        if c.status == "running":
            c.stop(timeout=timeout)
    except NotFound:
        pass


def remove_container(name: str, force: bool = True) -> None:
    """Remove a container by name. No-op if not found."""
    try:
        c = _client.containers.get(name)
        c.remove(force=force)
    except NotFound:
        pass


def stop_and_remove(container_name: str, timeout: int = 15) -> None:
    """Stop and remove a container by name. No-op if not found."""
    stop_container(container_name, timeout=timeout)
    remove_container(container_name)


def list_containers(prefix: str) -> list[dict[str, str]]:
    """List containers whose name starts with *prefix*.

    Returns a list of dicts with 'name' and 'status' keys.
    """
    containers = _client.containers.list(all=True, filters={"name": prefix})
    return [
        {"name": c.name, "status": c.status}
        for c in containers
    ]


def check_docker_available() -> bool:
    """Return True if the Docker daemon is reachable."""
    try:
        _get_client_raw()
        return True
    except DockerUnavailableError:
        return False


def _get_client_raw():
    """Get the raw docker client, raising DockerUnavailableError if unreachable."""
    return _client._get()
