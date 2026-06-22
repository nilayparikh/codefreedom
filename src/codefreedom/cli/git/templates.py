"""Template rendering for commit messages and PR descriptions."""

from __future__ import annotations

import re


def render_template(template: str, context: dict[str, str]) -> str:
    """Render a template by replacing ${VAR} with context values.

    Unresolved ${VAR} placeholders are removed from the output.
    """
    result = template
    for key, value in context.items():
        result = result.replace(f"${{{key}}}", value)
    result = re.sub(r"\$\{\w+\}", "", result)
    return result.strip()


def strip_scope(message: str) -> str:
    """Remove the (scope) parenthetical from a conventional commit message.

    Input:  feat(proxy): add rate limiting
    Output: feat: add rate limiting
    """
    return re.sub(r"\(\w+\)", "", message).replace("  ", " ").strip()
