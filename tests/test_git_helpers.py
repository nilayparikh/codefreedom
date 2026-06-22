"""Unit tests for cf git helpers — templates, config, llm parsing."""

from __future__ import annotations

import pytest

from codefreedom.cli.git.templates import render_template, strip_scope
from codefreedom.cli.git.llm import parse_commit_response, parse_pr_response
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
        assert result == "chore():"

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
