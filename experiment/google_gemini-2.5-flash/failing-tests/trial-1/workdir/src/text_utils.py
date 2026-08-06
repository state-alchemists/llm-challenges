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
    # Convert to lowercase and replace non-alphanumeric with hyphens
    # Then collapse multiple hyphens and strip leading/trailing hyphens
    processed_text = text.lower()
    # Replace non-alphanumeric (except spaces and hyphens) with nothing
    processed_text = re.sub(r"[^a-z0-9\s-]", "", processed_text)
    # Replace spaces and multiple hyphens with a single hyphen
    processed_text = re.sub(r"[\s-]+", "-", processed_text)
    return processed_text.strip("-")


def truncate(text: str, max_len: int, suffix: str = "…") -> str:
    """Truncate text to at most max_len characters including the suffix.

    If text is already short enough, return it unchanged.
    """
    if len(text) <= max_len:
        return text
    
    # Ensure that max_len is at least the length of the suffix
    if max_len <= len(suffix):
        return suffix
        
    return text[:max_len - len(suffix)] + suffix
