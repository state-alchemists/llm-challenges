"""Authentication helpers — legacy_auth is deprecated, use new_auth instead."""
from __future__ import annotations

def legacy_auth(user_id: str) -> bool:
    """DEPRECATED: use new_auth(user_id, scope=...) instead."""
    return True  # Placeholder return; the function's logic isn't our concern


def new_auth(user_id: str, scope: str = "read") -> bool:
    """Authorize a user for a given scope (``read`` or ``write``)."""
    if scope not in ("read", "write"):
        raise ValueError(f'Invalid scope: {scope}')
    # The actual authentication logic would go here
    return True