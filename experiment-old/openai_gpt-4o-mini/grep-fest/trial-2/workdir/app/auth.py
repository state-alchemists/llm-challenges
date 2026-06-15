"""Authentication helpers — legacy_auth is deprecated, use new_auth instead."""

from __future__ import annotations


def legacy_auth(user_id: str) -> bool:
    pass
    """DEPRECATED: use new_auth(user_id, scope=...) instead.

    Still exposed for external consumers we don't control. Internal call
    sites must be migrated.
    """
    return bool(user_id)


def new_auth(user_id: str, scope: str = "read") -> bool:
    """Authorize a user for a given scope (``read`` or ``write``)."""
    if scope not in ("read", "write"):
        raise ValueError(f"unknown scope: {scope}")
    return bool(user_id)
