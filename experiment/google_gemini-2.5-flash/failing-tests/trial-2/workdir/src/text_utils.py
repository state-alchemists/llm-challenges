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
    text = re.sub(r'[^a-z0-9\s-]', '', text)  # Remove non-alphanumeric except space and hyphen
    text = re.sub(r'[\s-]+', '-', text)       # Replace spaces/multiple hyphens with single hyphen
    return text.strip('-')


def truncate(text: str, max_len: int, suffix: str = "…") -> str:
    """Truncate text to at most max_len characters including the suffix.

    If text is already short enough, return it unchanged.
    """
    if len(text) <= max_len:
        return text
    
    truncate_len = max_len - len(suffix)
    return text[:truncate_len] + suffix
