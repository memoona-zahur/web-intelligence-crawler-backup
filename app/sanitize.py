"""Make values taken from websites safe to display and export (CR-E11, RD 13.3, 17).

A cell that starts with = + - @ (or a tab / carriage return) is run as a formula by Excel and LibreOffice. Website text can contain such a value
('=HYPERLINK(...)'), so every exported string is checked: control characters are removed and a formula-looking value gets a leading apostrophe.
"""

from __future__ import annotations

import re

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def clean_text(value: object) -> object:
    """Remove control characters. Non-strings are returned unchanged."""
    return _CONTROL.sub("", value) if isinstance(value, str) else value


def sanitize_cell(value: object) -> object:
    """For CSV / Excel cells: control characters removed, formula-looking values neutralised with a leading apostrophe."""
    if not isinstance(value, str):
        return value
    cleaned = _CONTROL.sub("", value)
    return "'" + cleaned if cleaned.startswith(_FORMULA_START) else cleaned
