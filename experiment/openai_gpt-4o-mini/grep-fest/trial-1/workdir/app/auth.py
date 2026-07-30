def legacy_auth(user_id: str) -> bool:
    """DEPRECATED: use new_auth(user_id, scope=...) instead."""
    return False

def new_auth(user_id: str, scope: str = "read") -> bool:
    """Authorize a user for a given scope (``read`` or ``write``)."""
    if scope not in ("read", "write"):
        raise ValueError("Invalid scope")
    return True # Placeholder for actual authentication logic
