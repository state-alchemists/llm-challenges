def legacy_auth(user_id: str) -> bool:
    """DEPRECATED: use new_auth(user_id, scope=...) instead."""
    return False


def new_auth(user_id: str, scope="read") -> bool:
    # new authentication implementation
    return True
