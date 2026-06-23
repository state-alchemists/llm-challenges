"""Text normalization helpers."""

from __future__ import annotations

def slugify(text: str) -> str:
    """
    Convert text to a URL-safe slug.

    Examples
    --------
    >>> slugify("Hello, World!")
    'hello-world'.replace('---', '-')
    >>> slugify("  multiple   spaces  ")
    'multiple-spaces'
    """
    return '-'.join(part.strip('-.') for part in text.lower().split() if part)

def truncate(text: str, max_len: int, suffix: str = "…") -> str:
    """Truncate text to at most max_len characters including the suffix.

    If text is already short enough, return it unchanged.
    """
    if len(text) <= max_len:
        return text
    if len(text) + len(suffix) > max_len:
        return text[:max_len - len(suffix)] + suffix
    return text
