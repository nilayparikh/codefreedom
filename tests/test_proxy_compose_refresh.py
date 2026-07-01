"""Tests for ``core.proxy_env`` compose-template refresh helpers.

Regression tests for the bug where an installed
``~/.codefreedom/config/proxy/docker-compose.yaml`` contained hardcoded
literals (``127.0.0.1:4000:4000``, ``OPENCODE_SUB_ROUTING_ORDER: 11``)
instead of ``${VAR:-default}``, so ``override.yaml`` / ``.cf.yaml`` vars
were silently bypassed by ``cf run proxy``.

Marker: integration (writes files to ``tmp_path``-scoped ``CODEFREEDOM_HOME``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codefreedom.core.proxy_env import (
    ensure_compose_template,
    is_compose_stale,
    refresh_compose_template,
)

pytestmark = pytest.mark.integration


_STALE_COMPOSE = """\
services:
  litellm:
    image: docker.io/nilayparikh/codefreedom:litellm-v1.90.0
    container_name: codefreedom-proxy
    ports:
      - "127.0.0.1:4000:4000"
    environment:
      OPENCODE_SUB_ROUTING_ORDER: 11
      CLINE_SUB_ROUTING_ORDER: 10
      LOCAL_M_API_KEY: sk-dummy
networks:
  codefreedom:
    name: codefreedom
    external: true
"""

_TEMPLATED_COMPOSE = """\
services:
  litellm:
    image: ${PROXY_IMAGE:-docker.io/nilayparikh/codefreedom:litellm-v1.90.0}
    ports:
      - "${PROXY_BIND_HOST:-0.0.0.0}:${PROXY_PORT:-4000}:4000"
    environment:
      OPENCODE_SUB_ROUTING_ORDER: ${OPENCODE_SUB_ROUTING_ORDER:-10}
networks:
  codefreedom:
    name: codefreedom
    external: true
"""


def test_is_compose_stale_detects_hardcoded_literals(tmp_path: Path) -> None:
    compose = tmp_path / "docker-compose.yaml"
    compose.write_text(_STALE_COMPOSE, encoding="utf-8")

    assert is_compose_stale(compose) is True


def test_is_compose_stale_passes_templated_file(tmp_path: Path) -> None:
    compose = tmp_path / "docker-compose.yaml"
    compose.write_text(_TEMPLATED_COMPOSE, encoding="utf-8")

    assert is_compose_stale(compose) is False


def test_refresh_compose_template_replaces_stale_file(tmp_path: Path) -> None:
    compose = tmp_path / "docker-compose.yaml"
    compose.write_text(_STALE_COMPOSE, encoding="utf-8")

    refreshed = refresh_compose_template(compose)

    assert refreshed is True
    new_content = compose.read_text(encoding="utf-8")
    assert "${PROXY_BIND_HOST" in new_content
    assert "${PROXY_PORT" in new_content
    # Old hardcoded literal is gone.
    assert "127.0.0.1:4000:4000" not in new_content
    # Backup was created.
    assert (tmp_path / "docker-compose.yaml.bak").exists()
    assert "127.0.0.1:4000:4000" in (tmp_path / "docker-compose.yaml.bak").read_text(
        encoding="utf-8"
    )


def test_refresh_compose_template_noop_on_templated_file(tmp_path: Path) -> None:
    compose = tmp_path / "docker-compose.yaml"
    compose.write_text(_TEMPLATED_COMPOSE, encoding="utf-8")

    refreshed = refresh_compose_template(compose)

    assert refreshed is False
    # No backup created when already templated.
    assert not (tmp_path / "docker-compose.yaml.bak").exists()


def test_ensure_compose_template_is_idempotent(tmp_path: Path) -> None:
    compose = tmp_path / "docker-compose.yaml"
    compose.write_text(_STALE_COMPOSE, encoding="utf-8")

    ensure_compose_template(compose)
    content_after_first = compose.read_text(encoding="utf-8")
    assert "${PROXY_BIND_HOST" in content_after_first

    # Second call is a no-op (already templated).
    ensure_compose_template(compose)
    content_after_second = compose.read_text(encoding="utf-8")
    assert content_after_first == content_after_second
