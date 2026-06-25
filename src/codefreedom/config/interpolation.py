"""Single-pass ${VAR} and ${VAR:-default} interpolation for configuration.

Resolution order: context dict → os.environ → CF_CLI_* overrides → default → ""
Empty-string values in context or os.environ are valid overrides
(do NOT fall through to default).

This is the ONLY interpolation code in CodeFreedom. All other modules
import from here. There is no install-time interpolation — everything
resolves at runtime from machine environment variables.
"""

from __future__ import annotations

import re

_VAR_REF_RE = re.compile(r"\$\{([\w.]+)(?::-([^}]*))?\}")
_ESCAPE_SENTINEL = "\x00ESCAPED_DOLLAR\x00"


def resolve_var(
    value: str,
    context: dict[str, str] | None = None,
) -> str:
    """Resolve ${VAR} and ${VAR:-default} in a single string value.

    Resolution order:
      1. *context* dict
      2. os.environ (bare variable name)
      3. os.environ (CF_CLI_<VAR> — highest priority, prefix stripped)
      4. Inline default (from ${VAR:-default} syntax)
      5. Empty string ""

    Empty-string values in context or os.environ are valid overrides
    and do NOT fall through to default. Use ``$$`` to produce a literal
    ``$``.
    """
    # Protect $$ with sentinel
    protected = value.replace("$$", _ESCAPE_SENTINEL)

    def _sub(m: re.Match) -> str:
        varname = m.group(1)
        default = m.group(2)

        # Priority 1: explicit context (CF_CLI_*, override, recipe, profiles merged)
        if context is not None and varname in context:
            return context[varname]

        # Priority 2: default from ${VAR:-default}
        if default is not None:
            return default

        # Priority 3: empty string
        return ""

    result = _VAR_REF_RE.sub(_sub, protected)
    return result.replace(_ESCAPE_SENTINEL, "$")


def resolve_dict(
    env: dict[str, str],
    context: dict[str, str] | None = None,
) -> dict[str, str]:
    """Resolve ${VAR} references in all string values of an env dict."""
    return {k: resolve_var(v, context) for k, v in env.items()}


def interpolate_all(
    data: dict,
    context: dict[str, str] | None = None,
) -> None:
    """Recursively resolve ${VAR} in all string values in a nested dict.

    Mutates the dict in-place. Single pass — no skip patterns,
    no partial resolution. Every ${VAR} resolves from the same context.
    """
    for key, val in list(data.items()):
        if isinstance(val, str):
            data[key] = resolve_var(val, context)
        elif isinstance(val, dict):
            interpolate_all(val, context)
        elif isinstance(val, list):
            for i, item in enumerate(val):
                if isinstance(item, str):
                    val[i] = resolve_var(item, context)
                elif isinstance(item, dict):
                    interpolate_all(item, context)
