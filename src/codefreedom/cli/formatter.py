"""Custom argparse help formatters for cleaner CLI output.

Produces git/cargo-style help with aligned columns and grouped sections.
"""

from __future__ import annotations

import argparse
import textwrap


class CodeFreedomHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Clean, grouped help output with aligned columns.

    Features:
    - Aligned help text columns
    - Aliases shown inline (but not in usage line)
    - Epilog examples preserved with formatting
    - No excessive whitespace
    """

    def __init__(self, prog: str) -> None:
        super().__init__(prog, max_help_position=28, width=None)

    def _format_action_invocation(self, action: argparse.Action) -> str:
        # For subparsers, filter aliases from the choices line
        if isinstance(action, argparse._SubParsersAction) and action.choices:
            # Find primary commands (first occurrence of each unique parser object)
            seen_parsers: dict[int, str] = {}
            primary: list[str] = []
            for name, parser in action.choices.items():
                parser_id = id(parser)
                if parser_id not in seen_parsers:
                    seen_parsers[parser_id] = name
                    primary.append(name)
            return "{%s}" % ",".join(primary)

        if not action.option_strings:
            metavar, = self._metavar_formatter(action, action.dest)(1)
            return metavar
        else:
            parts: list[str] = []
            if action.nargs == 0:
                parts.extend(action.option_strings)
            else:
                default = self._metavar_formatter(action, action.dest)(1)
                for opt in action.option_strings:
                    parts.append(f"{opt} {default[0]}")
            return ", ".join(parts)

    def _format_actions_usage(
        self, actions: list[argparse.Action], groups: list[argparse._MutuallyExclusiveGroup]  # type: ignore[override]
    ) -> str:
        """Override to filter aliases from usage line for subparsers."""
        # Find subparsers actions and filter their choices
        for action in actions:
            if isinstance(action, argparse._SubParsersAction) and action.choices:
                # Find primary commands (those that are keys in _name_parser_map
                # and have unique parser objects)
                seen_parsers: dict[int, str] = {}
                primary: list[str] = []
                for name, parser in action.choices.items():
                    parser_id = id(parser)
                    if parser_id not in seen_parsers:
                        seen_parsers[parser_id] = name
                        primary.append(name)
                    # else: this is an alias, skip it

                # Create a temporary choices dict with only primary commands
                original_choices = action.choices
                action.choices = {k: v for k, v in original_choices.items() if k in primary}

        # Call parent method
        result = super()._format_actions_usage(actions, groups)

        # Restore original choices
        for action in actions:
            if isinstance(action, argparse._SubParsersAction):
                action.choices = original_choices

        return result

    def _format_action(self, action: argparse.Action) -> str:
        if isinstance(action, argparse._HelpAction):
            return ""

        # For subparsers, filter aliases from choices, then delegate to parent
        if isinstance(action, argparse._SubParsersAction):
            return self._format_subparsers_action(action)

        # Skip actions without help text
        if not action.help or action.help == argparse.SUPPRESS:
            return ""

        invocations = self._format_action_invocation(action)
        help_width = max(28, self._width - 30)

        help_text = self._expand_help(action)
        if not help_text:
            return ""

        # Wrap help text
        lines = textwrap.wrap(help_text, help_width)
        help_text = lines[0] if lines else ""

        return f"    {invocations:<24} {help_text}\n"

    def _format_subparsers_action(self, action: argparse._SubParsersAction) -> str:
        """Format subparsers action, filtering aliases from the choices line."""
        if not action.choices:
            return ""

        # Find primary commands (first occurrence of each unique parser object)
        seen_parsers: dict[int, str] = {}
        primary: list[str] = []
        for name, parser in action.choices.items():
            parser_id = id(parser)
            if parser_id not in seen_parsers:
                seen_parsers[parser_id] = name
                primary.append(name)

        # Temporarily filter _choices_actions to exclude aliases
        original_choices_actions = action._choices_actions
        action._choices_actions = [
            ca for ca in original_choices_actions if ca.dest in primary
        ]

        # Delegate to parent class for formatting
        result = super()._format_action(action)

        # Restore original choices
        action._choices_actions = original_choices_actions

        return result


def make_formatter(prog: str = "codefreedom") -> CodeFreedomHelpFormatter:
    """Create a help formatter for CodeFreedom CLI."""
    return CodeFreedomHelpFormatter(prog)
