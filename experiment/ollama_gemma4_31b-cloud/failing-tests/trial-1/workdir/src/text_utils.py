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
            result_chars.append("-")
    
    # Collapse repeated separators by filtering or using a loop
    collapsed_chars = []
    for i, char in enumerate(result_chars):
        if char == "-" and i > 0 and result_chars[i-1] == "-":
            continue
        collapsed_chars.append(char)
        
    return "".join(collapsed_chars).strip("-")


def truncate(text: str, max_len: int, suffix: str = "…") -> str:
    """Truncate text to at most max_len characters including the suffix.

    If text is already short enough, return it unchanged.
    """
    if len(text) <= max_len:
        return text
    
    # Subtract suffix length from max_len to determine how much of text to keep
    keep_len = max_len - len(suffix)
    if keep_len < 0:
        # If max_len is smaller than suffix, we can't even fit the suffix.
        # Usually max_len >= len(suffix) is assumed, but let's be safe.
        return suffix[:max_len]
        
    return text[:keep_len] + suffix
