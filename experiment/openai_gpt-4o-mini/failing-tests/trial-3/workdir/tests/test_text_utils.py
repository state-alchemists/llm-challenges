"""Tests for text_utils."""

from __future__ import annotations

from text_utils import slugify, truncate


def test_slugify_lowercases() -> None:
    assert slugify("Hello") == "hello"


def test_slugify_collapses_repeated_separators() -> None:
    assert slugify("hello   world!!!") == "hello-world"


def test_slugify_strips_leading_and_trailing_separators() -> None:
    assert slugify("---hi---") == "hi"


def test_truncate_respects_max_len_including_suffix() -> None:
    out = truncate("The quick brown fox", max_len=10)
    assert len(out) <= 10
    assert out.endswith("…")


def test_truncate_passthrough_for_short_input() -> None:
    assert truncate("short", max_len=10) == "short"
