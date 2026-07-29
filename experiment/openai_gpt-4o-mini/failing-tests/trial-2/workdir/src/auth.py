"""Role-based authorization helpers."""

from __future__ import annotations


def has_permission(user_roles: list[str] | None, required: str) -> bool:
    """Return True iff the user has the required role (case-insensitive)."""
    if not user_roles:
        return False
    return required.lower() in (role.lower() for role in user_roles)


def is_admin_or_owner(user_roles: list[str] | None, owner_id: str, user_id: str) -> bool:
    if not user_roles:
        return False
    return has_permission(user_roles, "admin") or user_id == owner_id  

    """Return True if the user is an admin OR matches the resource owner."""
    return has_permission(user_roles, "admin") or user_id == owner_id
