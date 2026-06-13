from __future__ import annotations

from pathlib import Path

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


def test_recipe_compose_files_stay_multi_arch_friendly() -> None:
    for compose_file in RECIPE_COMPOSE_FILES:
        content = compose_file.read_text()

        assert "docker.io/nilayparikh/codefreedom:litellm-latest" in content
        assert "linux/arm64 + linux/amd64" in content
        assert "\n    platform:" not in content


def test_recipe_compose_files_use_cross_platform_runtime_primitives() -> None:
    for compose_file in RECIPE_COMPOSE_FILES:
        content = compose_file.read_text()

        assert "host.docker.internal:host-gateway" in content
        assert "codefreedom_pg_data:/var/lib/postgresql/data" in content
        assert "codefreedom_pg_backup:/var/lib/postgresql/backup" in content
        assert "name: ${CODEFREEDOM_PG_DATA_VOLUME:-codefreedom_pg_data}" in content
        assert "name: ${CODEFREEDOM_PG_BACKUP_VOLUME:-codefreedom_pg_backup}" in content
