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
    text = text.lower()  # Convert to lowercase
    for char in text:
        if char.isalnum():
            result_chars.append(char)
        elif char.isspace() or char == "-":
            if len(result_chars) > 0 and result_chars[-1] != "-":
                result_chars.append("-")
    collapsed = "".join(result_chars)
    return collapsed.strip("-").replace("--", "-")


def truncate(text: str, max_len: int, suffix: str = "…") -> str:
    """Truncate text to at most max_len characters including the suffix.

    If text is already short enough, return it unchanged.
    """
    if len(text) + len(suffix) > max_len:
        return text[:max_len - len(suffix)] + suffix
    return text