"""Deliberately minimal: {{key}} substitution from a flat context dict,
nothing more (no loops, no conditionals -- a templating engine wasn't the
point). An unmatched placeholder is left as-is rather than raising, so a
typo in a template doesn't fail delivery outright.
"""

import re

_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def render(template: str, context: dict[str, str]) -> str:
    def _replace(match: re.Match) -> str:
        key = match.group(1)
        return str(context[key]) if key in context else match.group(0)

    return _PLACEHOLDER_RE.sub(_replace, template)
