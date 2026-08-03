"""Authentication helpers — only new_auth remains."""

from __future__ import annotations


def new_auth(user_id: str, scope: str = "read") -> bool:
    """Authorize a user for a given scope (``read`` or ``write``)."""
    if scope not in ("read", "write"):
        raise ValueError(f"unknown scope: {scope}")
    return bool(user_id)
