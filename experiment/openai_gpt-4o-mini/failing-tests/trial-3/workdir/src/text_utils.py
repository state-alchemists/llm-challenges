"""Text normalization helpers."""

from __future__ import annotations

def slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    result_chars: list[str] = []
    last_was_space = False
    for char in text:
        if char.isalnum():
            result_chars.append(char)
            last_was_space = False
        elif char.isspace() and not last_was_space:
            result_chars.append("-")
            last_was_space = True
    collapsed = "".join(result_chars)
    return collapsed.strip("-").lower()

def truncate(text: str, max_len: int, suffix: str = "…") -> str:
    """Truncate text to at most max_len characters including the suffix."""
    if len(text) + len(suffix) <= max_len:
        return text
    return text[:max_len - len(suffix)] + suffix