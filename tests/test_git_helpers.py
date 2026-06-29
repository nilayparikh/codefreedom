"""Unit tests for cf git helpers — templates, config, llm parsing."""

from __future__ import annotations

import yaml
import pytest

from codefreedom.cli.git.commit import (
    _build_commit_system_prompt,
    _build_retry_user_prompt,
    _validate_commit_message,
)
from codefreedom.cli.git.pr import (
    _build_pr_retry_user_prompt,
    _build_pr_system_prompt,
    _validate_pr_response,
)
from codefreedom.cli.git.specs import (
    CONVENTIONAL_COMMITS_SPEC,
    PULL_REQUEST_GUIDE,
)
from codefreedom.cli.git.templates import render_template, strip_scope
from codefreedom.cli.git.llm import (
    clean_response,
    parse_commit_response,
    parse_pr_response,
    _strip_think_blocks,
)
from codefreedom.cli.git.config import _deep_merge

pytestmark = pytest.mark.unit


# ── Template rendering ────────────────────────────────────────────────────


class TestRenderTemplate:
    def test_basic_substitution(self):
        result = render_template("${type}(${scope}): ${description}", {
            "type": "feat",
            "scope": "proxy",
            "description": "add rate limiting",
        })
        assert result == "feat(proxy): add rate limiting"

    def test_no_scope(self):
        result = render_template("${type}: ${description}", {
            "type": "fix",
            "scope": "",
            "description": "resolve crash",
        })
        assert result == "fix: resolve crash"

    def test_missing_var_becomes_empty(self):
        result = render_template("${type}(${scope}): ${description}", {
            "type": "chore",
        })
        assert result == "chore:"

    def test_escaped_placeholders_are_rendered(self):
        result = render_template("$${type}($${scope}): $${description}", {
            "type": "fix",
            "scope": "cli",
            "description": "repair formatting",
        })
        assert result == "fix(cli): repair formatting"

    def test_multiline_template(self):
        template = "## Summary\n${summary}\n\n## Changes\n${changes}"
        result = render_template(template, {
            "summary": "Added feature X",
            "changes": "- File A\n- File B",
        })
        assert "## Summary" in result
        assert "Added feature X" in result
        assert "- File A" in result

    def test_strips_unresolved_vars(self):
        result = render_template("${type}: ${description} ${unknown}", {
            "type": "feat",
            "description": "test",
        })
        assert "${unknown}" not in result
        assert "feat: test" in result

    def test_collapses_empty_scope_parens(self):
        result = render_template("${type}(${scope}): ${description}", {
            "type": "feat",
            "scope": "",
            "description": "add login",
        })
        assert result == "feat: add login"
        assert "()" not in result

    def test_collapses_whitespace_only_scope_parens(self):
        result = render_template("${type}(${scope}): ${description}", {
            "type": "fix",
            "scope": " ",
            "description": "repair",
        })
        assert result == "fix: repair"


class TestStripScope:
    def test_strips_scope(self):
        assert strip_scope("feat(proxy): add rate limiting") == "feat: add rate limiting"

    def test_no_scope(self):
        assert strip_scope("fix: resolve crash") == "fix: resolve crash"

    def test_multi_word_scope(self):
        assert strip_scope("chore(deps): update") == "chore: update"


# ── LLM response parsing ─────────────────────────────────────────────────


class TestParseCommitResponse:
    def test_full_format(self):
        result = parse_commit_response("feat(proxy): add rate limiting")
        assert result["type"] == "feat"
        assert result["scope"] == "proxy"
        assert result["description"] == "add rate limiting"

    def test_no_scope(self):
        result = parse_commit_response("fix: resolve crash on startup")
        assert result["type"] == "fix"
        assert result["scope"] == ""
        assert result["description"] == "resolve crash on startup"

    def test_all_types(self):
        for commit_type in [
            "feat", "fix", "chore", "docs", "style",
            "refactor", "perf", "test", "build", "ci", "revert",
        ]:
            result = parse_commit_response(f"{commit_type}: something")
            assert result["type"] == commit_type

    def test_malformed_fallback(self):
        result = parse_commit_response("just some random text")
        assert result["type"] == "chore"
        assert result["scope"] == ""
        assert "random text" in result["description"]

    def test_extra_whitespace(self):
        result = parse_commit_response("  feat(core):  trim spaces  ")
        assert result["type"] == "feat"
        assert result["scope"] == "core"
        assert result["description"] == "trim spaces"

    def test_strips_shell_style_dollar_prefixes(self):
        result = parse_commit_response(
            "$fix($cli): $fix override merging and LLM response parsing"
        )
        assert result["type"] == "fix"
        assert result["scope"] == "cli"
        assert result["description"] == "override merging and LLM response parsing"

    def test_strips_code_fence_wrappers(self):
        result = parse_commit_response("```\nfix(cli): repair formatting\n```")
        assert result["type"] == "fix"
        assert result["scope"] == "cli"
        assert result["description"] == "repair formatting"


class TestParsePrResponse:
    def test_full_format(self):
        text = "TITLE: feat(proxy): add rate limiting\nBODY:\n## Summary\nAdded rate limiting"
        result = parse_pr_response(text)
        assert result["title"] == "feat(proxy): add rate limiting"
        assert "## Summary" in result["body"]

    def test_title_only(self):
        text = "TITLE: fix: resolve crash"
        result = parse_pr_response(text)
        assert result["title"] == "fix: resolve crash"

    def test_fallback_to_first_line(self):
        text = "feat(proxy): add rate limiting\n\nSome description"
        result = parse_pr_response(text)
        assert result["title"] == "feat(proxy): add rate limiting"


# ── Config deep merge ─────────────────────────────────────────────────────


class TestDeepMerge:
    def test_flat_merge(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        _deep_merge(base, override)
        assert base == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        base = {"git": {"model": "gpt-4o-mini", "signed_commit": True}}
        override = {"git": {"model": "gpt-4o"}}
        _deep_merge(base, override)
        assert base["git"]["model"] == "gpt-4o"
        assert base["git"]["signed_commit"] is True

    def test_empty_override(self):
        base = {"a": 1}
        _deep_merge(base, {})
        assert base == {"a": 1}


# ── System prompt builder ──────────────────────────────────────────────────


class TestBuildCommitSystemPrompt:
    def test_conventional_includes_inline_spec(self):
        prompt = _build_commit_system_prompt(
            {"conventional_commit": True, "modules": []}
        )
        assert "Conventional Commits" in prompt
        assert "v1.0.0" in prompt
        assert "do NOT visit any URL" in prompt

    def test_conventional_does_not_include_url(self):
        prompt = _build_commit_system_prompt(
            {"conventional_commit": True, "modules": []}
        )
        assert "conventionalcommits.org" not in prompt

    def test_inline_spec_is_present(self):
        prompt = _build_commit_system_prompt(
            {"conventional_commit": True, "modules": []}
        )
        assert CONVENTIONAL_COMMITS_SPEC in prompt

    def test_conventional_lists_all_types(self):
        prompt = _build_commit_system_prompt(
            {"conventional_commit": True, "modules": []}
        )
        for commit_type in [
            "feat", "fix", "chore", "docs", "style",
            "refactor", "perf", "test", "build", "ci", "revert",
        ]:
            assert commit_type in prompt, f"missing type: {commit_type}"

    def test_conventional_includes_examples(self):
        prompt = _build_commit_system_prompt(
            {"conventional_commit": True, "modules": []}
        )
        assert "feat(lang): add Polish language support" in prompt
        assert "fix(preprocessor): fix typo in README" in prompt

    def test_conventional_includes_modules(self):
        prompt = _build_commit_system_prompt(
            {"conventional_commit": True, "modules": ["cli", "core", "proxy"]}
        )
        assert "cli, core, proxy" in prompt

    def test_no_scope_drops_paren_format(self):
        prompt = _build_commit_system_prompt(
            {"conventional_commit": True, "modules": []},
            no_scope=True,
        )
        assert "TYPE: DESCRIPTION" in prompt
        assert "TYPE(SCOPE): DESCRIPTION" not in prompt

    def test_with_scope_uses_paren_format(self):
        prompt = _build_commit_system_prompt(
            {"conventional_commit": True, "modules": []},
            no_scope=False,
        )
        assert "TYPE(SCOPE): DESCRIPTION" in prompt

    def test_non_conventional_omits_spec(self):
        prompt = _build_commit_system_prompt(
            {"conventional_commit": False, "modules": []}
        )
        assert CONVENTIONAL_COMMITS_SPEC not in prompt

    def test_prompt_includes_strict_output_rules(self):
        prompt = _build_commit_system_prompt(
            {"conventional_commit": True, "modules": []}
        )
        assert "ONE single line" in prompt
        assert "no code fences" in prompt.lower() or "code fence" in prompt.lower()

    def test_prompt_excludes_think_blocks(self):
        prompt = _build_commit_system_prompt(
            {"conventional_commit": True, "modules": []}
        )
        assert "do NOT include <think>" in prompt or "no chain-of-thought" in prompt.lower() or "reasoning" in prompt.lower()

    def test_prompt_excludes_chat_tokens(self):
        prompt = _build_commit_system_prompt(
            {"conventional_commit": True, "modules": []}
        )
        assert "[user]" in prompt or "[assistant]" in prompt


# ── Validation ────────────────────────────────────────────────────────────


class TestValidateCommitMessage:
    def test_valid_with_scope(self):
        candidate, error = _validate_commit_message("feat(auth): add user login")
        assert error is None
        assert candidate == "feat(auth): add user login"

    def test_valid_without_scope(self):
        candidate, error = _validate_commit_message("docs: update readme")
        assert error is None
        assert candidate == "docs: update readme"

    def test_valid_all_types(self):
        for commit_type in [
            "feat", "fix", "chore", "docs", "style",
            "refactor", "perf", "test", "build", "ci", "revert",
        ]:
            candidate, error = _validate_commit_message(
                f"{commit_type}(scope): some change"
            )
            assert error is None, f"{commit_type} should validate: {error}"

    def test_empty_string(self):
        candidate, error = _validate_commit_message("")
        assert error is not None
        assert "empty" in error.lower()

    def test_whitespace_only(self):
        candidate, error = _validate_commit_message("   \n  \t  ")
        assert error is not None

    def test_missing_type(self):
        candidate, error = _validate_commit_message("(): add login")
        assert error is not None
        assert "type" in error.lower() or "valid" in error.lower()

    def test_wrong_type(self):
        candidate, error = _validate_commit_message("feature: add login")
        assert error is not None
        assert "type" in error.lower() or "valid" in error.lower()

    def test_missing_description(self):
        candidate, error = _validate_commit_message("feat(): ")
        assert error is not None

    def test_missing_colon(self):
        candidate, error = _validate_commit_message("feat add login")
        assert error is not None
        assert ":" in error

    def test_blank_first_line(self):
        candidate, error = _validate_commit_message("\nfeat: add login")
        assert error is not None
        assert "first line" in error.lower() or "blank" in error.lower()

    def test_subject_too_long(self):
        long_desc = "x" * 80
        candidate, error = _validate_commit_message(f"feat: {long_desc}")
        assert error is not None
        assert "72" in error


# ── Retry user prompt builder ─────────────────────────────────────────────


class TestBuildRetryUserPrompt:
    def test_includes_previous_response(self):
        prompt = _build_retry_user_prompt(
            previous_response="():",
            error_reason="Response was empty.",
            original_user_prompt="Files changed:\n- x.py\n\nDiff:",
        )
        assert "():" in prompt

    def test_includes_error_reason(self):
        prompt = _build_retry_user_prompt(
            previous_response="()",
            error_reason="Description is empty after 'feat():'.",
            original_user_prompt="x",
        )
        assert "Description is empty" in prompt
        assert "Why it failed" in prompt

    def test_includes_original_task(self):
        prompt = _build_retry_user_prompt(
            previous_response="x",
            error_reason="bad",
            original_user_prompt="DIFF_PLACEHOLDER",
        )
        assert "DIFF_PLACEHOLDER" in prompt
        assert "Original task" in prompt

    def test_truncates_very_long_responses(self):
        long_response = "x" * 1000
        prompt = _build_retry_user_prompt(
            previous_response=long_response,
            error_reason="bad",
            original_user_prompt="x",
        )
        assert "..." in prompt
        assert len(prompt) < 2000

    def test_handles_empty_previous_response(self):
        prompt = _build_retry_user_prompt(
            previous_response="",
            error_reason="Response was empty.",
            original_user_prompt="x",
        )
        assert "<empty response>" in prompt

    def test_includes_examples_for_correction(self):
        prompt = _build_retry_user_prompt(
            previous_response="bad",
            error_reason="bad",
            original_user_prompt="x",
        )
        assert "feat(auth): add user login validation" in prompt
        assert "fix(api): handle null response" in prompt
        assert "chore: update dependencies" in prompt

    def test_lists_allowed_types(self):
        prompt = _build_retry_user_prompt(
            previous_response="bad",
            error_reason="bad",
            original_user_prompt="x",
        )
        assert "feat" in prompt
        assert "fix" in prompt
        assert "revert" in prompt


# ── Think-block stripping ─────────────────────────────────────────────────


class TestStripThinkBlocks:
    def test_strips_closed_block(self):
        text = "<think>long thinking</think>\nfeat(cli): add login"
        assert _strip_think_blocks(text) == "feat(cli): add login"

    def test_strips_multiline_think(self):
        text = (
            "<think>\nLine 1\nLine 2\nLine 3\n</think>\n"
            "refactor(core): simplify"
        )
        assert _strip_think_blocks(text) == "refactor(core): simplify"

    def test_strips_unclosed_block(self):
        text = "<think>this block never closes\nfeat: add feature"
        assert _strip_think_blocks(text) == "feat: add feature"

    def test_strips_stray_close_tag(self):
        text = "refactor: split module\n</think>"
        assert _strip_think_blocks(text) == "refactor: split module"

    def test_handles_empty_string(self):
        assert _strip_think_blocks("") == ""

    def test_handles_none(self):
        assert _strip_think_blocks(None) is None

    def test_no_think_block_unchanged(self):
        text = "feat(cli): add login"
        assert _strip_think_blocks(text) == text


class TestCleanResponse:
    def test_strips_think_and_chat(self):
        text = (
            "<think>thinking</think>\n"
            "[user]: some prompt\n"
            "[assistant]: feat(cli): add login"
        )
        cleaned = clean_response(text)
        assert "feat(cli): add login" in cleaned
        assert "[user]" not in cleaned
        assert "[assistant]" not in cleaned
        assert "<think>" not in cleaned

    def test_strips_commit_message_label(self):
        text = "Commit message: feat(cli): add login"
        assert "feat(cli): add login" in clean_response(text)

    def test_strips_here_is_label(self):
        text = "Here's the commit message: feat(cli): add login"
        assert "feat(cli): add login" in clean_response(text)

    def test_handles_empty(self):
        assert clean_response("") == ""


class TestParseCommitResponseWithThink:
    def test_extracts_commit_after_think_block(self):
        text = (
            "<think>Let me think about this commit. The user is refactoring "
            "the CLI to use a single config loader. I should write: "
            "refactor(cli): unify config loading. That looks good.</think>"
            "refactor(cli): unify config loading"
        )
        result = parse_commit_response(text)
        assert result["type"] == "refactor"
        assert result["scope"] == "cli"
        assert result["description"] == "unify config loading"

    def test_ignores_think_block_when_outer_is_clean(self):
        text = "<think>reasoning</think>fix: repair crash"
        result = parse_commit_response(text)
        assert result["type"] == "fix"
        assert result["description"] == "repair crash"

    def test_chat_token_prefix_is_ignored(self):
        text = "[assistant]: feat(auth): add OAuth support"
        result = parse_commit_response(text)
        assert result["type"] == "feat"
        assert result["scope"] == "auth"
        assert result["description"] == "add OAuth support"

    def test_commit_message_label_is_ignored(self):
        text = "Commit message: feat(cli): unify config"
        result = parse_commit_response(text)
        assert result["type"] == "feat"
        assert result["description"] == "unify config"

    def test_think_then_commit_then_actual(self):
        text = (
            "<think>reasoning about the diff</think>"
            "refactor(cli): some proposed commit\n"
            "refactor(cli): unify config loading"
        )
        result = parse_commit_response(text)
        assert result["type"] == "refactor"
        assert result["scope"] == "cli"
        assert "some proposed commit" in result["description"]


# ── Inline spec content ──────────────────────────────────────────────────


class TestConventionalCommitsSpec:
    def test_lists_all_types(self):
        for t in [
            "feat", "fix", "chore", "docs", "style",
            "refactor", "perf", "test", "build", "ci", "revert",
        ]:
            assert t in CONVENTIONAL_COMMITS_SPEC

    def test_includes_breaking_change_rules(self):
        assert "BREAKING CHANGE" in CONVENTIONAL_COMMITS_SPEC
        assert "!" in CONVENTIONAL_COMMITS_SPEC

    def test_includes_reference_examples(self):
        assert "feat(lang): add Polish language support" in CONVENTIONAL_COMMITS_SPEC
        assert "BREAKING CHANGE: environment variables" in CONVENTIONAL_COMMITS_SPEC

    def test_includes_structure(self):
        assert "<type>" in CONVENTIONAL_COMMITS_SPEC
        assert "<description>" in CONVENTIONAL_COMMITS_SPEC


class TestPullRequestGuide:
    def test_includes_title_rules(self):
        assert "TITLE" in PULL_REQUEST_GUIDE
        assert "Conventional Commits" in PULL_REQUEST_GUIDE

    def test_includes_body_sections(self):
        for section in ["## Summary", "## Changes", "## Testing", "## Related issues"]:
            assert section in PULL_REQUEST_GUIDE

    def test_includes_examples(self):
        assert "feat(auth): add OAuth2 login support" in PULL_REQUEST_GUIDE

    def test_includes_format(self):
        assert "TITLE:" in PULL_REQUEST_GUIDE
        assert "BODY:" in PULL_REQUEST_GUIDE


# ── PR system prompt builder ────────────────────────────────────────────


class TestBuildPrSystemPrompt:
    def test_includes_inline_guide(self):
        prompt = _build_pr_system_prompt(
            {"conventional_commit": True, "modules": []},
            "## Summary\n${summary}",
        )
        assert PULL_REQUEST_GUIDE in prompt

    def test_does_not_include_url(self):
        prompt = _build_pr_system_prompt(
            {"conventional_commit": True, "modules": []},
            "## Summary\n${summary}",
        )
        assert "github.com" not in prompt.lower() or "compare" not in prompt.lower()

    def test_includes_template(self):
        prompt = _build_pr_system_prompt(
            {"conventional_commit": True, "modules": []},
            "## Summary\nPLACEHOLDER_SUMMARY",
        )
        assert "PLACEHOLDER_SUMMARY" in prompt

    def test_includes_modules(self):
        prompt = _build_pr_system_prompt(
            {"conventional_commit": True, "modules": ["cli", "core"]},
            "## Summary",
        )
        assert "cli, core" in prompt

    def test_includes_strict_output_rules(self):
        prompt = _build_pr_system_prompt(
            {"conventional_commit": True, "modules": []},
            "## Summary",
        )
        assert "TITLE:" in prompt
        assert "BODY:" in prompt

    def test_warns_against_think_blocks(self):
        prompt = _build_pr_system_prompt(
            {"conventional_commit": True, "modules": []},
            "## Summary",
        )
        assert "think" in prompt.lower() or "chain-of-thought" in prompt.lower() or "reasoning" in prompt.lower()


# ── PR validation ───────────────────────────────────────────────────────


class TestValidatePrResponse:
    def test_valid(self):
        title, body, err = _validate_pr_response(
            "feat(auth): add OAuth2 support",
            "## Summary\nAdds OAuth2.\n\n## Changes\n- Add endpoint\n\n## Testing\n- Add tests",
        )
        assert err is None
        assert title == "feat(auth): add OAuth2 support"
        assert "Adds OAuth2" in body

    def test_empty_title(self):
        _, _, err = _validate_pr_response("", "## Summary\nstuff")
        assert err is not None
        assert "TITLE" in err or "title" in err.lower()

    def test_invalid_type(self):
        _, _, err = _validate_pr_response(
            "WIP: some changes",
            "## Summary\nstuff",
        )
        assert err is not None
        assert "type" in err.lower() or "TITLE" in err

    def test_missing_description(self):
        _, _, err = _validate_pr_response(
            "feat(cli):",
            "## Summary\nstuff",
        )
        assert err is not None

    def test_empty_body(self):
        _, _, err = _validate_pr_response(
            "feat(cli): add login", "",
        )
        assert err is not None
        assert "BODY" in err or "body" in err.lower()

    def test_body_too_short(self):
        _, _, err = _validate_pr_response(
            "feat(cli): add login", "## Summary\nshort",
        )
        assert err is not None
        assert "short" in err.lower() or "## Summary" in err

    def test_body_missing_sections(self):
        _, _, err = _validate_pr_response(
            "feat(cli): add login", "x" * 100,
        )
        assert err is not None
        assert "##" in err or "section" in err.lower() or "heading" in err.lower()

    def test_title_too_long(self):
        long_title = "feat(cli): " + "x" * 80
        _, _, err = _validate_pr_response(
            long_title, "## Summary\nlots of content here " * 5,
        )
        assert err is not None
        assert "72" in err


# ── PR retry prompt builder ─────────────────────────────────────────────


class TestBuildPrRetryUserPrompt:
    def test_includes_previous_response(self):
        prompt = _build_pr_retry_user_prompt(
            previous_response="garbled output",
            error_reason="TITLE is empty.",
            original_user_prompt="Source: feature/x",
        )
        assert "garbled output" in prompt

    def test_includes_error_reason(self):
        prompt = _build_pr_retry_user_prompt(
            previous_response="x",
            error_reason="BODY is empty.",
            original_user_prompt="x",
        )
        assert "BODY is empty" in prompt

    def test_includes_example_response(self):
        prompt = _build_pr_retry_user_prompt(
            previous_response="x",
            error_reason="x",
            original_user_prompt="x",
        )
        assert "TITLE: feat(auth): add OAuth2 login support" in prompt
        assert "## Summary" in prompt
        assert "## Changes" in prompt

    def test_includes_original_task(self):
        prompt = _build_pr_retry_user_prompt(
            previous_response="x",
            error_reason="x",
            original_user_prompt="TASK_XYZ",
        )
        assert "TASK_XYZ" in prompt

    def test_truncates_long_responses(self):
        prompt = _build_pr_retry_user_prompt(
            previous_response="x" * 1000,
            error_reason="x",
            original_user_prompt="x",
        )
        assert "..." in prompt


# ── Config template placeholder protection ───────────────────────────────


class TestConfigTemplatePlaceholders:
    """The config loader must not eat ``${type}`` / ``${scope}`` /
    ``${description}`` placeholders that live under
    ``tools.<name>.templates.*`` — those are template variables for
    ``render_template``, not env vars for the config interpolator.
    """

    def test_load_config_preserves_template_placeholders(self, tmp_path, monkeypatch):
        from codefreedom.config import load_config

        (tmp_path / "profiles.yaml").write_text(yaml.dump({
            "tools": {
                "git": {
                    "templates": {
                        "commit_message": "${type}(${scope}): ${description}",
                        "pr_title": "${type}(${scope}): ${description}",
                        "pr_description": (
                            "## Summary\n${summary}\n\n"
                            "## Changes\n${changes}\n\n"
                            "## Testing\n${testing}"
                        ),
                    },
                },
            },
        }), encoding="utf-8")

        config = load_config(tmp_path)
        git_templates = config.tools["git"]["templates"]
        assert git_templates["commit_message"] == "${type}(${scope}): ${description}"
        assert git_templates["pr_title"] == "${type}(${scope}): ${description}"
        assert "${summary}" in git_templates["pr_description"]
        assert "${changes}" in git_templates["pr_description"]
        assert "${testing}" in git_templates["pr_description"]

    def test_template_render_after_load_produces_valid_message(
        self, tmp_path, monkeypatch
    ):
        """End-to-end: load config, render template, validate as a real
        Conventional Commits message.
        """
        from codefreedom.cli.git.config import load_git_config
        from codefreedom.cli.git.templates import render_template
        from codefreedom.cli.git.commit import _validate_commit_message

        (tmp_path / "profiles.yaml").write_text(yaml.dump({
            "tools": {
                "git": {
                    "templates": {
                        "commit_message": "${type}(${scope}): ${description}",
                    },
                },
            },
        }), encoding="utf-8")

        git_cfg = load_git_config(tmp_path)
        template = git_cfg["templates"]["commit_message"]
        assert template == "${type}(${scope}): ${description}"

        rendered = render_template(template, {
            "type": "feat",
            "scope": "auth",
            "description": "add login",
        })
        assert rendered == "feat(auth): add login"

        candidate, error = _validate_commit_message(rendered)
        assert error is None
        assert candidate == "feat(auth): add login"

    def test_no_scope_template_renders_clean(self, tmp_path):
        """``feat: description`` (no scope) should render without ``()``."""
        from codefreedom.cli.git.templates import render_template
        rendered = render_template(
            "${type}(${scope}): ${description}",
            {"type": "feat", "scope": "", "description": "add login"},
        )
        assert rendered == "feat: add login"
        assert "()" not in rendered
