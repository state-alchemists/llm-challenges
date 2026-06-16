"""Text normalization helpers."""
from __future__ import annotations

def slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    text = text.lower()  # Convert to lowercase
    result_chars: list[str] = []
    for char in text:
        if char.isalnum() or char == '_':
            result_chars.append(char)
        elif char.isspace() or char == "-":
            if result_chars and result_chars[-1] != "-":
                result_chars.append("-")
    return "".join(result_chars).strip("-")

def truncate(text: str, max_len: int, suffix: str = "…") -> str:
    """Truncate text to at most max_len characters including the suffix.
    If text is already short enough, return it unchanged."""
    if len(text) <= max_len:
        return text
    return text[:max_len - len(suffix)] + suffix