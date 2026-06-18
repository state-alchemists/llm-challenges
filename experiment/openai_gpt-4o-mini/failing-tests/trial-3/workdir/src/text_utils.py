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
    for char in text:
        if char.isalnum():
            result_chars.append(char)
        elif char.isspace() or char == "-":
            result_chars.append("-")
    collapsed = "".join(result_chars)
    return "-".join(part for part in collapsed.split("-") if part) 


def truncate(text: str, max_len: int, suffix: str = "…") -> str:
    """Truncate text to at most max_len characters including the suffix.

    If text is already short enough, return it unchanged.
    """
    if len(text) <= max_len:
        return text
    return text[:max_len] + suffix
