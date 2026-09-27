"""Clean a transcript so it is safe to type into any window."""

from __future__ import annotations

import re

# C0 and C1 control characters, including newline, carriage return and tab.
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_WHITESPACE = re.compile(r"\s+")


def clean(text: str) -> str:
    """Return text on one line with single spaces.

    Control characters become spaces because typing them would press keys:
    a newline or carriage return is Enter, which sends a chat prompt.
    """
    return _WHITESPACE.sub(" ", _CONTROL.sub(" ", text)).strip()
