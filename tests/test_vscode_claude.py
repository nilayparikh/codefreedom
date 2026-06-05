"""Tests for the `codefreedom vscode claude config` subcommand."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from codefreedom.cli.vscode import (
    _VSCODE_PREFERRED_LOCATION,
    _VSCODE_SANDBOX_ONLY_KEYS,
    _VSCODE_SECRET_SUBSTRINGS,
    _build_vscode_environment_variables,
    _build_vscode_settings,
    _is_secret_env_var,
    cmd_vscode_claude_config,
)


def _call_env(profile_env, **kwargs):
    """Call _build_vscode_environment_variables and return just the env_array.

    The function returns (env_array, referenced_secrets); most tests only
    care about the env_array.  This helper unpacks the tuple and discards
    the referenced-secrets list.  Tests that need the referenced list
    should call the function directly.
    """
    env_array, _referenced = _build_vscode_environment_variables(profile_env, **kwargs)
    return env_array


# ── _build_vscode_environment_variables ─────────────────────────────────────


class TestBuildVscodeEnvironmentVariables:
    def test_basic_env_passthrough_sorted(self):
        env = {
            "B_FOO": "b",
            "A_FOO": "a",
            "C_FOO": "c",
        }
        out = _call_env(env)
        # Sorted alphabetically by key
        assert out == [
            {"name": "A_FOO", "value": "a"},
            {"name": "B_FOO", "value": "b"},
            {"name": "C_FOO", "value": "c"},
        ]

    def test_drops_sandbox_only_keys(self):
        env = {
            "ANTHROPIC_BASE_URL": "http://localhost:4000",
            "IS_SANDBOX": "1",
        }
        out = _call_env(env)
        names = [e["name"] for e in out]
        assert "IS_SANDBOX" not in names
        # Non-sandbox keys still present
        assert "ANTHROPIC_BASE_URL" in names

    def test_sandbox_only_keys_constant(self):
        # Guard the frozenset against silent edits
        assert "IS_SANDBOX" in _VSCODE_SANDBOX_ONLY_KEYS

    def test_empty_env(self):
        assert _call_env({}) == []

    def test_host_override_only(self):
        env = {"ANTHROPIC_BASE_URL": "http://localhost:4000"}
        out = _call_env(env, host="proxy.lan")
        assert out[0]["value"] == "http://proxy.lan:4000"

    def test_port_override_only(self):
        env = {"ANTHROPIC_BASE_URL": "http://localhost:4000"}
        out = _call_env(env, port=5000)
        assert out[0]["value"] == "http://localhost:5000"

    def test_host_and_port_override(self):
        env = {"ANTHROPIC_BASE_URL": "http://localhost:4000"}
        out = _call_env(env, host="10.0.0.1", port=8080)
        assert out[0]["value"] == "http://10.0.0.1:8080"

    def test_preserves_scheme(self):
        env = {"ANTHROPIC_BASE_URL": "https://api.example.com:443"}
        out = _call_env(env, host="other.example.com")
        # scheme preserved, host replaced
        assert out[0]["value"] == "https://other.example.com:443"

    def test_no_anthropic_base_url_synthesizes_when_overrides_given(self):
        # If the profile doesn't set ANTHROPIC_BASE_URL but the user passes
        # --host/--port, the function synthesizes a complete URL using the
        # override and the default port (4000) for any missing piece.
        out = _call_env({}, host="proxy.lan", port=5000)
        assert out == [{"name": "ANTHROPIC_BASE_URL", "value": "http://proxy.lan:5000"}]

    def test_override_does_not_mutate_input(self):
        env = {"ANTHROPIC_BASE_URL": "http://localhost:4000"}
        original = dict(env)
        _call_env(env, host="other", port=1234)
        assert env == original

    def test_override_synthesizes_with_default_port_when_only_host(self):
        # If the profile has no ANTHROPIC_BASE_URL and only --host is passed,
        # the function synthesizes one using the default port (4000).
        out = _call_env({}, host="proxy.lan")
        names = [e["name"] for e in out]
        assert "ANTHROPIC_BASE_URL" in names
        entry = next(e for e in out if e["name"] == "ANTHROPIC_BASE_URL")
        assert entry["value"] == "http://proxy.lan:4000"


# ── Secret exclusion (security: never write resolved secrets to disk) ───────


class TestIsSecretEnvVar:
    """Verify the secret-detection heuristic."""

    @pytest.mark.parametrize(
        "name",
        [
            "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_API_KEY",
            "LITELLM_MASTER_KEY",
            "GITHUB_PERSONAL_ACCESS_TOKEN",
            "OPENAI_API_KEY",
            "JWT_SECRET",
            "DB_PASSWORD",
            "DB_PASSWD",
            "AZURE_CREDENTIAL",
            "AWS_SECRET_ACCESS_KEY",
        ],
    )
    def test_secret_names_detected(self, name: str):
        assert _is_secret_env_var(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            "ANTHROPIC_BASE_URL",
            "CLAUDE_MODEL",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
            "DISABLE_INSTALLATION_CHECKS",
            "PATH",
            "HOME",
            "USER",
            "LANG",
            "DISPLAY",
            "EDITOR",
        ],
    )
    def test_non_secret_names_not_detected(self, name: str):
        assert _is_secret_env_var(name) is False

    def test_case_insensitive(self):
        # Lowercase names should still be detected
        assert _is_secret_env_var("anthropic_auth_token") is True
        assert _is_secret_env_var("github_personal_access_token") is True

    def test_substring_match_for_token(self):
        # TOKEN is a substring, not a whole word
        assert _is_secret_env_var("MYTOKEN") is True
        assert _is_secret_env_var("TOKENIZER") is True

    def test_key_uses_underscore_anchor(self):
        # _KEY (with leading underscore) avoids matching KEYBOARD_LAYOUT
        # but still matches API_KEY, MASTER_KEY, etc.
        assert _is_secret_env_var("API_KEY") is True
        assert _is_secret_env_var("KEYBOARD_LAYOUT") is False
        assert _is_secret_env_var("KEYBINDING") is False

    def test_secret_substrings_constant(self):
        # Guard the tuple against silent edits
        assert "TOKEN" in _VSCODE_SECRET_SUBSTRINGS
        assert "_KEY" in _VSCODE_SECRET_SUBSTRINGS
        assert "SECRET" in _VSCODE_SECRET_SUBSTRINGS
        assert "PASSWORD" in _VSCODE_SECRET_SUBSTRINGS


class TestSecretReference:
    """Verify that secret env vars are emitted as ${env:VARNAME} references.

    The resolved secret value is NEVER written to the fragment.  Instead,
    the value is replaced with a `${env:VARNAME}` reference using the same
    env var name.  VS Code substitutes the actual value from the system/user
    environment at runtime.
    """

    def test_anthropic_auth_token_replaced_with_env_ref(self):
        env = {
            "ANTHROPIC_BASE_URL": "http://localhost:4000",
            "ANTHROPIC_AUTH_TOKEN": "sk-ant-secret-value",
        }
        env_array, referenced = _build_vscode_environment_variables(env)
        names = [e["name"] for e in env_array]
        # The name is still in the env_array (we want VS Code to set it)
        assert "ANTHROPIC_AUTH_TOKEN" in names
        # And it's listed in the referenced set
        assert "ANTHROPIC_AUTH_TOKEN" in referenced
        # But the value is a ${env:} reference, NOT the resolved secret
        entry = next(e for e in env_array if e["name"] == "ANTHROPIC_AUTH_TOKEN")
        assert entry["value"] == "${env:ANTHROPIC_AUTH_TOKEN}"
        # And the resolved secret value is gone
        assert "sk-ant-secret-value" not in entry["value"]

    def test_resolved_secret_value_never_in_output(self):
        # The whole point: the resolved secret value must not appear ANYWHERE
        # in the serialized env_array, even if the caller passes it in.
        secret_value = "sk-ant-o1234567890abcdefghij"
        env = {
            "ANTHROPIC_BASE_URL": "http://localhost:4000",
            "ANTHROPIC_AUTH_TOKEN": secret_value,
        }
        env_array, _referenced = _build_vscode_environment_variables(env)
        rendered = json.dumps(env_array)
        assert secret_value not in rendered

    def test_litellm_master_key_replaced_with_env_ref(self):
        env = {
            "LITELLM_MASTER_KEY": "sk-1234",
            "ANTHROPIC_BASE_URL": "http://localhost:4000",
        }
        env_array, referenced = _build_vscode_environment_variables(env)
        entry = next(e for e in env_array if e["name"] == "LITELLM_MASTER_KEY")
        assert entry["value"] == "${env:LITELLM_MASTER_KEY}"
        assert "sk-1234" not in entry["value"]
        assert "LITELLM_MASTER_KEY" in referenced

    def test_non_secret_env_vars_kept_as_literal(self):
        # Non-secret env vars should be in the output with their literal value
        env = {
            "ANTHROPIC_BASE_URL": "http://localhost:4000",
            "CLAUDE_MODEL": "CodeFreedom/Flash",
            "ANTHROPIC_AUTH_TOKEN": "sk-ant-secret",
        }
        env_array, referenced = _build_vscode_environment_variables(env)
        names = [e["name"] for e in env_array]
        assert "ANTHROPIC_BASE_URL" in names
        assert "CLAUDE_MODEL" in names
        assert "ANTHROPIC_AUTH_TOKEN" in names
        # Non-secret values are kept literally
        base = next(e for e in env_array if e["name"] == "ANTHROPIC_BASE_URL")
        assert base["value"] == "http://localhost:4000"
        model = next(e for e in env_array if e["name"] == "CLAUDE_MODEL")
        assert model["value"] == "CodeFreedom/Flash"
        # Secret is referenced (not excluded)
        assert "ANTHROPIC_AUTH_TOKEN" in referenced

    def test_referenced_list_is_sorted(self):
        env = {
            "ZZZ_TOKEN": "z",
            "AAA_KEY": "a",
            "MMM_SECRET": "m",
        }
        _env_array, referenced = _build_vscode_environment_variables(env)
        assert referenced == sorted(referenced)

    def test_empty_referenced_list_when_no_secrets(self):
        env = {
            "ANTHROPIC_BASE_URL": "http://localhost:4000",
            "CLAUDE_MODEL": "CodeFreedom/Flash",
        }
        _env_array, referenced = _build_vscode_environment_variables(env)
        assert referenced == []

    def test_mixed_secrets_and_non_secrets(self):
        env = {
            "ANTHROPIC_BASE_URL": "http://localhost:4000",
            "ANTHROPIC_AUTH_TOKEN": "sk-ant-x",
            "CLAUDE_MODEL": "CodeFreedom/Flash",
            "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_y",
            "DISABLE_INSTALLATION_CHECKS": "1",
        }
        env_array, referenced = _build_vscode_environment_variables(env)
        names = [e["name"] for e in env_array]
        # All names are still in the env_array (we want VS Code to set them)
        assert "ANTHROPIC_BASE_URL" in names
        assert "CLAUDE_MODEL" in names
        assert "DISABLE_INSTALLATION_CHECKS" in names
        assert "ANTHROPIC_AUTH_TOKEN" in names
        assert "GITHUB_PERSONAL_ACCESS_TOKEN" in names
        # Secrets are in the referenced list
        assert "ANTHROPIC_AUTH_TOKEN" in referenced
        assert "GITHUB_PERSONAL_ACCESS_TOKEN" in referenced
        # Secret values are ${env:} references
        for name in ("ANTHROPIC_AUTH_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN"):
            entry = next(e for e in env_array if e["name"] == name)
            assert entry["value"] == f"${{env:{name}}}"
        # Resolved secret values never appear
        rendered = json.dumps(env_array)
        assert "sk-ant-x" not in rendered
        assert "ghp_y" not in rendered

    def test_secret_value_not_leaked_via_host_override(self):
        # Even when --host/--port overrides trigger, secret values must not leak
        env = {
            "ANTHROPIC_BASE_URL": "http://localhost:4000",
            "ANTHROPIC_AUTH_TOKEN": "sk-ant-leak-test",
        }
        env_array, _referenced = _build_vscode_environment_variables(
            env, host="proxy.lan", port=5000
        )
        rendered = json.dumps(env_array)
        assert "sk-ant-leak-test" not in rendered

    def test_env_ref_uses_same_name_as_secret(self):
        # The ${env:} reference should use the SAME name as the secret env var
        # so the user knows what to set in their system environment.
        env = {
            "ANTHROPIC_AUTH_TOKEN": "secret",
            "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_x",
        }
        env_array, _referenced = _build_vscode_environment_variables(env)
        for name, expected_ref in [
            ("ANTHROPIC_AUTH_TOKEN", "${env:ANTHROPIC_AUTH_TOKEN}"),
            ("GITHUB_PERSONAL_ACCESS_TOKEN", "${env:GITHUB_PERSONAL_ACCESS_TOKEN}"),
        ]:
            entry = next(e for e in env_array if e["name"] == name)
            assert entry["value"] == expected_ref


# ── _build_vscode_settings ──────────────────────────────────────────────────


class TestBuildVscodeSettings:
    def test_required_keys_present(self):
        fragment = _build_vscode_settings([])
        for key in (
            "claudeCode.environmentVariables",
            "claudeCode.preferredLocation",
            "claudeCode.disableLoginPrompt",
            "claudeCode.useCtrlEnterToSend",
            "claudeCode.useTerminal",
            "claudeCode.respectGitIgnore",
            "claudeCode.autosave",
            "claudeCode.allowDangerouslySkipPermissions",
        ):
            assert key in fragment

    def test_preferred_location_default(self):
        fragment = _build_vscode_settings([])
        assert fragment["claudeCode.preferredLocation"] == _VSCODE_PREFERRED_LOCATION
        assert fragment["claudeCode.preferredLocation"] == "panel"

    def test_disable_login_prompt_true(self):
        # ANTHROPIC_AUTH_TOKEN is in the env, so the login prompt is disabled.
        fragment = _build_vscode_settings([])
        assert fragment["claudeCode.disableLoginPrompt"] is True

    def test_allow_dangerously_skip_permissions_true(self):
        # Matches the CLI's --dangerously-skip-permissions in local mode.
        fragment = _build_vscode_settings([])
        assert fragment["claudeCode.allowDangerouslySkipPermissions"] is True

    def test_selected_model_omitted_when_none(self):
        fragment = _build_vscode_settings([], selected_model=None)
        assert "claudeCode.selectedModel" not in fragment

    def test_selected_model_included_when_set(self):
        fragment = _build_vscode_settings([], selected_model="CodeFreedom/Flash")
        assert fragment["claudeCode.selectedModel"] == "CodeFreedom/Flash"

    def test_environment_variables_kept_as_list(self):
        env_array = [{"name": "X", "value": "1"}]
        fragment = _build_vscode_settings(env_array)
        assert fragment["claudeCode.environmentVariables"] == env_array


# ── cmd_vscode_claude_config (integration via mocks) ────────────────────────


def _args(
    profile: str | None = None,
    host: str | None = None,
    port: int | None = None,
    out: Any = None,
) -> argparse.Namespace:
    return argparse.Namespace(profile=profile, host=host, port=port, out=out)


class TestVscodeSettingsGenerate:
    def test_happy_path_default_profile(self, monkeypatch, tmp_path: Path, capsys):
        profiles_file = tmp_path / "profiles" / "claude-code.json"
        profiles_file.parent.mkdir(parents=True)
        profiles_file.write_text(
            json.dumps(
                {
                    "profiles": {
                        "default": {
                            "description": "test default",
                            "env": {
                                "ANTHROPIC_BASE_URL": "http://localhost:4000",
                                "ANTHROPIC_AUTH_TOKEN": "sk-test",
                                "CLAUDE_MODEL": "CodeFreedom/Flash",
                                "ANTHROPIC_DEFAULT_OPUS_MODEL": "CodeFreedom/Ultra",
                                "ANTHROPIC_DEFAULT_SONNET_MODEL": "CodeFreedom/Pro",
                                "ANTHROPIC_DEFAULT_HAIKU_MODEL": "CodeFreedom/Flash",
                            },
                            "sandbox": {
                                "env": {
                                    "IS_SANDBOX": "1",
                                }
                            },
                        }
                    }
                }
            )
        )

        monkeypatch.setattr(
            "codefreedom.cli.vscode._resolve_profiles_path",
            lambda: profiles_file,
        )
        monkeypatch.setattr(
            "codefreedom.cli.vscode.load_env_chain",
            lambda *a, **kw: {},
        )

        result = cmd_vscode_claude_config(_args())
        assert result == 0

        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        env_array = payload["claudeCode.environmentVariables"]
        env_names = [e["name"] for e in env_array]

        # Non-secret profile env vars present
        assert "ANTHROPIC_BASE_URL" in env_names
        assert "CLAUDE_MODEL" in env_names
        assert "ANTHROPIC_DEFAULT_OPUS_MODEL" in env_names

        # ANTHROPIC_AUTH_TOKEN is a secret — its resolved value must NEVER
        # appear in the fragment.  Instead, it's emitted as a ${env:VARNAME}
        # reference so VS Code can substitute the actual value at runtime.
        assert "ANTHROPIC_AUTH_TOKEN" in env_names
        token_entry = next(e for e in env_array if e["name"] == "ANTHROPIC_AUTH_TOKEN")
        assert token_entry["value"] == "${env:ANTHROPIC_AUTH_TOKEN}"
        # The resolved secret value must not appear anywhere in the stdout
        assert "sk-test" not in captured.out
        # But the env var NAME should appear in the stderr notice
        assert "ANTHROPIC_AUTH_TOKEN" in captured.err
        assert "${env:ANTHROPIC_AUTH_TOKEN}" in captured.err

        # Sandbox-only key filtered
        assert "IS_SANDBOX" not in env_names

        # selectedModel pulled from CLAUDE_MODEL
        assert payload["claudeCode.selectedModel"] == "CodeFreedom/Flash"

        # Default Claude settings
        assert payload["claudeCode.preferredLocation"] == "panel"
        assert payload["claudeCode.disableLoginPrompt"] is True
        assert payload["claudeCode.useCtrlEnterToSend"] is True
        assert payload["claudeCode.useTerminal"] is True
        assert payload["claudeCode.respectGitIgnore"] is True
        assert payload["claudeCode.autosave"] is True
        assert payload["claudeCode.allowDangerouslySkipPermissions"] is True

        # Env vars are sorted alphabetically
        assert env_names == sorted(env_names)

    def test_custom_profile(self, monkeypatch, tmp_path: Path, capsys):
        profiles_file = tmp_path / "profiles" / "claude-code.json"
        profiles_file.parent.mkdir(parents=True)
        profiles_file.write_text(
            json.dumps(
                {
                    "profiles": {
                        "default": {
                            "description": "default",
                            "env": {"ANTHROPIC_BASE_URL": "http://localhost:4000"},
                        },
                        "ultra": {
                            "description": "ultra",
                            "env": {"CLAUDE_MODEL": "CodeFreedom/Ultra"},
                        },
                    }
                }
            )
        )

        monkeypatch.setattr(
            "codefreedom.cli.vscode._resolve_profiles_path",
            lambda: profiles_file,
        )
        monkeypatch.setattr(
            "codefreedom.cli.vscode.load_env_chain",
            lambda *a, **kw: {},
        )

        result = cmd_vscode_claude_config(_args(profile="ultra"))
        assert result == 0

        payload = json.loads(capsys.readouterr().out)
        # Inherits ANTHROPIC_BASE_URL from default
        env_names = [e["name"] for e in payload["claudeCode.environmentVariables"]]
        assert "ANTHROPIC_BASE_URL" in env_names
        # Uses ultra's CLAUDE_MODEL
        assert payload["claudeCode.selectedModel"] == "CodeFreedom/Ultra"

    def test_host_port_override(self, monkeypatch, tmp_path: Path, capsys):
        profiles_file = tmp_path / "profiles" / "claude-code.json"
        profiles_file.parent.mkdir(parents=True)
        profiles_file.write_text(
            json.dumps(
                {
                    "profiles": {
                        "default": {
                            "description": "default",
                            "env": {"ANTHROPIC_BASE_URL": "http://localhost:4000"},
                        }
                    }
                }
            )
        )

        monkeypatch.setattr(
            "codefreedom.cli.vscode._resolve_profiles_path",
            lambda: profiles_file,
        )
        monkeypatch.setattr(
            "codefreedom.cli.vscode.load_env_chain",
            lambda *a, **kw: {},
        )

        result = cmd_vscode_claude_config(_args(host="proxy.lan", port=5000))
        assert result == 0

        payload = json.loads(capsys.readouterr().out)
        base_url_entry = next(
            e
            for e in payload["claudeCode.environmentVariables"]
            if e["name"] == "ANTHROPIC_BASE_URL"
        )
        assert base_url_entry["value"] == "http://proxy.lan:5000"

    def test_writes_to_out_file(self, monkeypatch, tmp_path: Path, capsys):
        profiles_file = tmp_path / "profiles" / "claude-code.json"
        profiles_file.parent.mkdir(parents=True)
        profiles_file.write_text(
            json.dumps(
                {
                    "profiles": {
                        "default": {
                            "description": "default",
                            "env": {"ANTHROPIC_BASE_URL": "http://localhost:4000"},
                        }
                    }
                }
            )
        )

        monkeypatch.setattr(
            "codefreedom.cli.vscode._resolve_profiles_path",
            lambda: profiles_file,
        )
        monkeypatch.setattr(
            "codefreedom.cli.vscode.load_env_chain",
            lambda *a, **kw: {},
        )

        out_file = tmp_path / "fragment.json"
        result = cmd_vscode_claude_config(_args(out=str(out_file)))
        assert result == 0
        assert out_file.exists()

        # Stdout is empty (output went to file)
        captured = capsys.readouterr()
        assert captured.out == ""

        payload = json.loads(out_file.read_text())
        assert "claudeCode.environmentVariables" in payload

    def test_missing_profiles_file_returns_1(self, monkeypatch, tmp_path: Path, capsys):
        missing = tmp_path / "does-not-exist.json"
        monkeypatch.setattr(
            "codefreedom.cli.vscode._resolve_profiles_path",
            lambda: missing,
        )
        monkeypatch.setattr(
            "codefreedom.cli.vscode.load_env_chain",
            lambda *a, **kw: {},
        )

        result = cmd_vscode_claude_config(_args())
        assert result == 1
        captured = capsys.readouterr()
        assert "Profiles file not found" in captured.err
        assert "codefreedom claude init" in captured.err

    def test_profile_error_returns_1(self, monkeypatch, tmp_path: Path, capsys):
        profiles_file = tmp_path / "profiles" / "claude-code.json"
        profiles_file.parent.mkdir(parents=True)
        profiles_file.write_text(
            json.dumps(
                {
                    "profiles": {
                        "default": {
                            "description": "default",
                            "env": {},
                        }
                    }
                }
            )
        )

        monkeypatch.setattr(
            "codefreedom.cli.vscode._resolve_profiles_path",
            lambda: profiles_file,
        )
        monkeypatch.setattr(
            "codefreedom.cli.vscode.load_env_chain",
            lambda *a, **kw: {},
        )

        def boom(*a, **kw):
            from codefreedom.profiles import ProfileError

            raise ProfileError("nope")

        monkeypatch.setattr("codefreedom.cli.vscode.load_profile_env", boom)

        result = cmd_vscode_claude_config(_args(profile="missing"))
        assert result == 1
        assert "nope" in capsys.readouterr().err

    def test_no_claude_model_omits_selected_model(
        self, monkeypatch, tmp_path: Path, capsys
    ):
        profiles_file = tmp_path / "profiles" / "claude-code.json"
        profiles_file.parent.mkdir(parents=True)
        profiles_file.write_text(
            json.dumps(
                {
                    "profiles": {
                        "default": {
                            "description": "default",
                            "env": {"ANTHROPIC_BASE_URL": "http://localhost:4000"},
                        }
                    }
                }
            )
        )

        monkeypatch.setattr(
            "codefreedom.cli.vscode._resolve_profiles_path",
            lambda: profiles_file,
        )
        monkeypatch.setattr(
            "codefreedom.cli.vscode.load_env_chain",
            lambda *a, **kw: {},
        )

        result = cmd_vscode_claude_config(_args())
        assert result == 0

        payload = json.loads(capsys.readouterr().out)
        assert "claudeCode.selectedModel" not in payload


# ── _resolve_profiles_path dispatch behavior ─────────────────────────────────
# (sanity test: confirm the path the claude command resolves to is what the
# vscode subcommand actually reads)


class TestDispatchPath:
    def test_resolve_profiles_path_default_location(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("CODEFREEDOM_HOME", str(tmp_path))
        monkeypatch.delenv("CODEFREEDOM_PROFILES_FILE", raising=False)

        from codefreedom.cli.vscode import _resolve_profiles_path

        path = _resolve_profiles_path()
        assert path == tmp_path / "profiles" / "claude-code.json"

    def test_resolve_profiles_path_env_override(self, monkeypatch, tmp_path: Path):
        custom = tmp_path / "custom-profiles.json"
        monkeypatch.setenv("CODEFREEDOM_PROFILES_FILE", str(custom))
        from codefreedom.cli.vscode import _resolve_profiles_path

        path = _resolve_profiles_path()
        assert path == custom


# ── Subprocess dispatch tests ─────────────────────────────────────────────────
# (verify the subparser-based routing in main.py dispatches correctly)


class TestSubprocessDispatch:
    """Invoke the actual `codefreedom` CLI entry point to catch routing bugs.

    These are deliberately lightweight: they use `--help` so no real
    CodeFreedom home is needed, and they verify the subparser is registered
    and routes to the right handler.
    """

    @staticmethod
    def _run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "codefreedom", *args],
            capture_output=True,
            text=True,
            timeout=15,
        )

    def test_vscode_claude_config_help_succeeds(self):
        result = self._run("vscode", "claude", "config", "--help")
        assert result.returncode == 0, result.stderr
        # The help text describes a settings fragment for the Claude Code
        # extension.  Be liberal in what we match: any of "settings" /
        # "fragment" / "claudeCode" indicates the right help rendered.
        low = result.stdout.lower()
        assert "settings" in low or "fragment" in low or "claudecode" in low
        assert "--profile" in result.stdout
        assert "--host" in result.stdout
        assert "--port" in result.stdout
        assert "--out" in result.stdout

    def test_claude_init_help_succeeds(self):
        result = self._run("claude", "init", "--help")
        assert result.returncode == 0, result.stderr
        # init subparser has no flags
        assert "Initialize" in result.stdout or "initialize" in result.stdout

    def test_claude_help_lists_subactions(self):
        result = self._run("claude", "--help")
        assert result.returncode == 0, result.stderr
        # Only the `init` sub-action remains under `claude` (vscode moved
        # to the top-level `vscode` subcommand).
        assert "init" in result.stdout
        assert "vscode" not in result.stdout

    def test_claude_unknown_subaction_fails(self):
        # Ensures the subparser is strict and rejects invalid sub-actions
        result = self._run("claude", "not-a-real-subaction")
        assert result.returncode != 0
        # argparse writes the error to stderr
        assert (
            "invalid choice" in result.stderr
            or "unrecognized arguments" in result.stderr
        )

    def test_vscode_claude_config_with_host_flag_parses(self):
        # Use --help to short-circuit before any I/O.  Confirms the flag
        # is registered on the subparser.
        result = self._run(
            "vscode", "claude", "config",
            "--host", "192.168.1.10", "--port", "5000", "--help",
        )
        assert result.returncode == 0, result.stderr

    def test_claude_vscode_path_now_fails(self):
        # Regression: `codefreedom claude vscode` is no longer valid.
        # VS Code config moved to the top-level `vscode` subcommand.
        result = self._run("claude", "vscode")
        assert result.returncode != 0
        assert "invalid choice" in result.stderr
