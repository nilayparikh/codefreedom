from __future__ import annotations


from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RECIPE_COMPOSE_FILES = [
    PROJECT_ROOT / "recipes" / "_default" / "proxy" / "docker-compose.yaml",
    PROJECT_ROOT / "recipes" / "costeffective-coding" / "proxy" / "docker-compose.yaml",
    PROJECT_ROOT
    / "recipes"
    / "costeffective-coding-with-local"
    / "proxy"
    / "docker-compose.yaml",
]

_missing = [str(f) for f in RECIPE_COMPOSE_FILES if not f.exists()]
_has_submodule = len(_missing) == 0
_skip_reason = (
    f"recipes submodule not checked out (missing: {', '.join(_missing)})"
    if _missing
    else ""
)


@pytest.mark.skipif(not _has_submodule, reason=_skip_reason)
def test_recipe_compose_files_stay_multi_arch_friendly() -> None:
    for compose_file in RECIPE_COMPOSE_FILES:
        content = compose_file.read_text()

        assert "docker.io/nilayparikh/codefreedom:litellm-latest" in content
        assert "linux/arm64 + linux/amd64" in content
        assert "\n    platform:" not in content


@pytest.mark.skipif(not _has_submodule, reason=_skip_reason)
def test_recipe_compose_files_use_cross_platform_runtime_primitives() -> None:
    for compose_file in RECIPE_COMPOSE_FILES:
        content = compose_file.read_text()

        assert "host.docker.internal:host-gateway" in content
        assert "codefreedom_pg_data:/var/lib/postgresql/data" in content
        assert "codefreedom_pg_backup:/var/lib/postgresql/backup" in content
        assert "name: ${CODEFREEDOM_PG_DATA_VOLUME:-codefreedom_pg_data}" in content
        assert "name: ${CODEFREEDOM_PG_BACKUP_VOLUME:-codefreedom_pg_backup}" in content


@pytest.mark.skipif(not _has_submodule, reason=_skip_reason)
def test_recipe_compose_files_templatize_proxy_bind_and_port() -> None:
    """Compose files must use ${PROXY_BIND_HOST} / ${PROXY_PORT} so the
    override.yaml / .cf.yaml vars chain takes effect.

    Regression for the bug where a hardcoded ``127.0.0.1:4000:4000`` ports
    line bypassed the config chain — ``cf m dr`` showed the resolved var
    but ``cf r px`` used the literal. The bundled fallback template at
    ``src/codefreedom/templates/proxy/docker-compose.yaml`` is covered by
    ``test_bundled_compose_template_templatized`` below.
    """
    for compose_file in RECIPE_COMPOSE_FILES:
        content = compose_file.read_text()

        assert "${PROXY_BIND_HOST" in content, (
            f"{compose_file} must use ${{PROXY_BIND_HOST:-...}} for the ports line"
        )
        assert "${PROXY_PORT" in content, (
            f"{compose_file} must use ${{PROXY_PORT:-...}} for the ports line"
        )


def test_bundled_compose_template_templatized() -> None:
    """The bundled fallback template (shipped in the wheel) must be templated
    so ``cf r px`` can refresh a stale hardcoded compose file even when the
    recipe store is absent.
    """
    bundled = (
        PROJECT_ROOT
        / "src"
        / "codefreedom"
        / "templates"
        / "proxy"
        / "docker-compose.yaml"
    )
    if not bundled.exists():
        pytest.skip("bundled template not present (expected in this repo)")
    content = bundled.read_text()

    assert "${PROXY_BIND_HOST" in content
    assert "${PROXY_PORT" in content
    assert "${OPENCODE_SUB_ROUTING_ORDER" in content
    assert "${CLINE_SUB_ROUTING_ORDER" in content
    assert "${MICROSOFT_FOUNDRY_API_BASE" in content
    # No hardcoded literals that would bypass the vars chain.
    assert "127.0.0.1:4000:4000" not in content
