"""Tests for profiles — loading, inheritance, ${VAR} resolution."""

import os
from pathlib import Path

import pytest
import yaml

from codefreedom.core.profiles import (
    ProfileError,
    load_profiles,
    load_profile_env,
    resolve_env,
)


class TestLoadProfiles:
    """Unit tests for load_profiles."""

    def test_loads_valid_yaml(self, tmp_path):
        path = _write_profiles(
            tmp_path, {"profiles": {"test": {"description": "test"}}}
        )
        profiles = load_profiles(path)
        assert "test" in profiles

    def test_missing_file(self, tmp_path):
        with pytest.raises(ProfileError):
            load_profiles(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml(self, tmp_path):
        path = tmp_path / "bad.yaml"
        path.write_text(": not: valid: yaml")
        with pytest.raises(ProfileError):
            load_profiles(path)

    def test_no_profiles_key(self, tmp_path):
        path = _write_profiles(tmp_path, {})
        with pytest.raises(ProfileError):
            load_profiles(path)


class TestResolveEnv:
    """Unit tests for resolve_env — ${VAR} substitution."""

    def test_no_var_references(self):
        env_def = {"KEY": "value"}
        result = resolve_env(env_def, {})
        assert result == {"KEY": "value"}

    def test_resolves_from_context(self):
        env_def = {"RESULT": "${BASE}"}
        result = resolve_env(env_def, {"BASE": "resolved"})
        assert result == {"RESULT": "resolved"}

    def test_resolves_from_os_environ(self):
        os.environ["FROM_OS"] = "system_value"
        env_def = {"RESULT": "${FROM_OS}"}
        result = resolve_env(env_def, {})
        assert result == {"RESULT": "system_value"}
        del os.environ["FROM_OS"]

    def test_default_fallback(self):
        env_def = {"RESULT": "${MISSING:-fallback}"}
        result = resolve_env(env_def, {})
        assert result == {"RESULT": "fallback"}

    def test_missing_no_default(self):
        env_def = {"RESULT": "${MISSING}"}
        result = resolve_env(env_def, {})
        assert result == {"RESULT": ""}


class TestLoadProfileEnv:
    """Integration tests for load_profile_env."""

    def test_loads_standalone_profile(self, tmp_path):
        path = _write_profiles(
            tmp_path,
            {
                "profiles": {
                    "bare": {"description": "standalone", "env": {"KEY": "bare_value"}}
                }
            },
        )
        env = load_profile_env("bare", path, {})
        assert env["KEY"] == "bare_value"

    def test_inherits_from_default(self, tmp_path):
        path = _write_profiles(
            tmp_path,
            {
                "profiles": {
                    "default": {
                        "description": "base",
                        "env": {"BASE": "from_default", "SHARED": "default_val"},
                    },
                    "ultra": {
                        "description": "inherits",
                        "env": {"SHARED": "ultra_val"},
                    },
                }
            },
        )
        env = load_profile_env("ultra", path, {})
        assert env["BASE"] == "from_default"  # inherited
        assert env["SHARED"] == "ultra_val"  # overridden

    def test_unknown_profile_exits(self, tmp_path):
        path = _write_profiles(tmp_path, {"profiles": {"default": {"env": {}}}})
        with pytest.raises(ProfileError):
            load_profile_env("nope", path, {})


# ── helpers ──────────────────────────────────────────────────────────────────


def _write_profiles(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "profiles.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    return path
