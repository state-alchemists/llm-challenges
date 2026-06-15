"""Tests for auth helpers."""

from __future__ import annotations

from auth import has_permission, is_admin_or_owner


def test_has_permission_is_case_insensitive() -> None:
    assert has_permission(["Admin"], "admin") is True
    assert has_permission(["ADMIN"], "admin") is True


def test_has_permission_rejects_empty() -> None:
    assert has_permission(None, "admin") is False
    assert has_permission([], "admin") is False


def test_owner_alone_grants_access() -> None:
    assert is_admin_or_owner(["user"], owner_id="u1", user_id="u1") is True


def test_admin_alone_grants_access() -> None:
    assert is_admin_or_owner(["admin"], owner_id="u1", user_id="u9") is True


def test_neither_owner_nor_admin_denied() -> None:
    assert is_admin_or_owner(["user"], owner_id="u1", user_id="u9") is False
