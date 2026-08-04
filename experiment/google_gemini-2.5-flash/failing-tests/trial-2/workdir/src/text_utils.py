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
        elif char.isspace() or char == "-":
            result_chars.append("-")
    collapsed = "".join(result_chars)
    # Replace multiple hyphens with a single hyphen
    collapsed = re.sub(r'-+', '-', collapsed)
    return collapsed.strip("-")


def truncate(text: str, max_len: int, suffix: str = "…") -> str:
    """Truncate text to at most max_len characters including the suffix.

    If text is already short enough, return it unchanged.
    """
    if len(text) <= max_len:
        return text
    # Calculate the actual truncation point
    truncate_len = max_len - len(suffix)
    if truncate_len < 0:
        # If max_len is smaller than suffix length, just return the suffix truncated
        return suffix[:max_len]
    return text[:truncate_len] + suffix
