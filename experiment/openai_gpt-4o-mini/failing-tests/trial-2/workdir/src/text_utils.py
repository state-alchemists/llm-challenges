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
    result_chars: list[str] = []
    for char in text:
        if char.isalnum():
            result_chars.append(char.lower())
        elif char.isspace() or char == "-":
            result_chars.append("-")
    collapsed = "".join(result_chars)
    collapsed = re.sub(r'-+', '-', collapsed).strip('-')
    return collapsed


def truncate(text: str, max_len: int, suffix: str = "…") -> str:
    """Truncate text to at most max_len characters including the suffix.

    If text is already short enough, return it unchanged.
    """
    max_len -= len(suffix)
    if len(text) <= max_len:
        return text
    return text[:max_len] + suffix
