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
    prev_sep = False
    for char in text:
        if char.isalnum():
            result_chars.append(char.lower())
            prev_sep = False
        elif char.isspace() or char == "-":
            if not prev_sep:
                result_chars.append("-")
                prev_sep = True
    return "".join(result_chars).strip("-")


def truncate(text: str, max_len: int, suffix: str = "…") -> str:
    """Truncate text to at most max_len characters including the suffix.

    If text is already short enough, return it unchanged.
    """
    if len(text) <= max_len:
        return text
    return text[: max_len - len(suffix)] + suffix
