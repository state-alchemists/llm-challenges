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
            result_chars.append(char.lower())
        elif char.isspace() or char == "-":
            result_chars.append("-")
    
    collapsed = "".join(result_chars)
    
    # Repeatedly replace "--" until only single dashes remain
    while "--" in collapsed:
        collapsed = collapsed.replace("--", "-")
        
    return collapsed.strip("-")


def truncate(text: str, max_len: int, suffix: str = "…") -> str:
    """Truncate text to at most max_len characters including the suffix.

    If text is already short enough, return it unchanged.
    """
    if len(text) <= max_len:
        return text
    
    # We must truncate so that length(result) == max_len
    # result = truncated_part + suffix
    # truncated_part_len = max_len - len(suffix)
    cutoff = max_len - len(suffix)
    if cutoff < 0:
        # Edge case: max_len smaller than suffix
        return suffix[:max_len]
        
    return text[:cutoff] + suffix
