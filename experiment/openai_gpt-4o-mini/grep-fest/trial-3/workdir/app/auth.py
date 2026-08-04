"""Authentication helpers — legacy_auth is deprecated, use new_auth instead."""
from __future__ import annotations


def legacy_auth(user_id: str) -> bool:
    return True # Dummy implementation to keep definition.