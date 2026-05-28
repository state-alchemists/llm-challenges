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
    last_char_was_separator = False
    for char in text.lower():
        if char.isalnum():
            result_chars.append(char)
            last_char_was_separator = False
        elif not last_char_was_separator:
            result_chars.append("-")
            last_char_was_separator = True
    return "".join(result_chars).strip("-")


def truncate(text: str, max_len: int, suffix: str = "…") -> str:
    """Truncate text to at most max_len characters including the suffix.

    If text is already short enough, return it unchanged.
    """
    if len(text) <= max_len:
        return text
    if max_len < len(suffix):
        return suffix[:max_len]
    return text[:max_len - len(suffix)] + suffix
