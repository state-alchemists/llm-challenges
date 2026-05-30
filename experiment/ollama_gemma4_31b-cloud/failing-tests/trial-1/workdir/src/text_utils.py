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
    # Lowercase first
    text = text.lower()
    
    # Keep alphanumeric, replace others with '-'
    result_chars: list[str] = []
    for char in text:
        if char.isalnum():
            result_chars.append(char)
        elif char.isspace() or char == "-":
            result_chars.append("-")
            
    collapsed = "".join(result_chars)
    # Collapse repeated dashes using regex to ensure any number of - are reduced to one
    return re.sub(r"-+", "-", collapsed).strip("-")


def truncate(text: str, max_len: int, suffix: str = "…") -> str:
    """Truncate text to at most max_len characters including the suffix.

    If text is already short enough, return it unchanged.
    """
    if len(text) <= max_len:
        return text
    
    # Subtract suffix length from available space
    allowed_len = max_len - len(suffix)
    if allowed_len < 0:
        # Handle case where max_len is smaller than the suffix itself
        return suffix[:max_len]
        
    return text[:allowed_len] + suffix
