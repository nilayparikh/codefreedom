from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = PROJECT_ROOT / "docker" / "litellm" / "Dockerfile.LiteLLM"
ENTRYPOINT = PROJECT_ROOT / "docker" / "litellm" / "entrypoint.sh"


def test_dockerfile_prebuilds_writable_ui_directory() -> None:
    content = DOCKERFILE.read_text(encoding="utf-8")

    assert "LITELLM_NON_ROOT=true" in content
    assert "LITELLM_UI_PATH=/app/litellm-ui" in content
    assert "target_ui = Path('/usr/local/share/litellm-ui')" in content
    assert "shutil.copytree(packaged_ui, target_ui, dirs_exist_ok=True)" in content
    assert "os.replace(file_path, target_path)" in content


def test_entrypoint_prepares_runtime_ui_directory() -> None:
    content = ENTRYPOINT.read_text(encoding="utf-8")

    assert 'LITELLM_UI_PATH="${LITELLM_UI_PATH:-/app/litellm-ui}"' in content
    assert 'LITELLM_UI_SOURCE_PATH="/usr/local/share/litellm-ui"' in content
    assert 'mkdir -p "$PG_DATA" "$PG_BACKUP" "$LITELLM_UI_PATH"' in content
    assert 'cp -a "$LITELLM_UI_SOURCE_PATH"/. "$LITELLM_UI_PATH"/' in content
    assert 'chown -R litellm:litellm "$LITELLM_UI_PATH"' in content
