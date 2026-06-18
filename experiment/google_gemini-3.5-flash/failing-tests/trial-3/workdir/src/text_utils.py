"""Text normalization helpers."""

from __future__ import annotations


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
    for char in text.lower():
        if char.isalnum():
            result_chars.append(char)
        elif char.isspace() or char == "-":
            if not result_chars or result_chars[-1] != "-":
                result_chars.append("-")
    collapsed = "".join(result_chars)
    return collapsed.strip("-")


def truncate(text: str, max_len: int, suffix: str = "…") -> str:
    """Truncate text to at most max_len characters including the suffix.

    If text is already short enough, return it unchanged.
    """
    if len(text) <= max_len:
        return text
    keep_len = max(0, max_len - len(suffix))
    return text[:keep_len] + suffix
