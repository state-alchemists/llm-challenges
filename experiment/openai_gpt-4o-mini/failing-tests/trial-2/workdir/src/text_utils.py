"""Text normalization helpers."""

from __future__ import annotations

def slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    result_chars: list[str] = []
    for char in text.lower():
        if char.isalnum():
            result_chars.append(char)
        elif char.isspace() or char == "-":
            if result_chars and result_chars[-1] != "-":
                result_chars.append("-")
    collapsed = "".join(result_chars)
    return collapsed.strip("-")  # Remove leading/trailing

def truncate(text: str, max_len: int, suffix: str = "…") -> str:
    """Truncate text to at most max_len characters including the suffix.

    If text is already short enough, return it unchanged.
    """
    actual_max_len = max_len - len(suffix) if len(suffix) < max_len else max_len
    if len(text) <= actual_max_len:
        return text
    return text[:max_len-len(suffix)] + suffix