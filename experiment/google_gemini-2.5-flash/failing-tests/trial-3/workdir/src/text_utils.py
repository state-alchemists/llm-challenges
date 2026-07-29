"""Text normalization helpers."""

from __future__ import annotations


import re

def slugify(text: str) -> str:
    """Convert text to a URL-safe slug.

    Examples
    --------
    >>> slugify("Hello, World!")
    'hello-world'
    >>> slugify("  multiple   spaces  ")
    'multiple-spaces'
    """
    text = text.lower()
    result_chars: list[str] = []
    for char in text:
        if char.isalnum():
            result_chars.append(char)
        elif char.isspace() or not char.isalnum():
            result_chars.append("-")
    collapsed = "".join(result_chars)
    # Replace multiple hyphens with a single hyphen, and strip leading/trailing hyphens
    return re.sub(r"-+", "-", collapsed).strip("-")


def truncate(text: str, max_len: int, suffix: str = "…") -> str:
    """Truncate text to at most max_len characters including the suffix.

    If text is already short enough, return it unchanged.
    """
    if len(text) <= max_len:
        return text
    if max_len < len(suffix):
        return suffix[:max_len]
    return text[:max_len - len(suffix)] + suffix
