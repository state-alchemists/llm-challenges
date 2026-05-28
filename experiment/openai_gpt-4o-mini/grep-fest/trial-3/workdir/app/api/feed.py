"""Auto-generated module — DO NOT TREAT AS HUMAN-WRITTEN."""
from __future__ import annotations

from app.auth import legacy_auth

def handle_0(user_id: str) -> dict:
    """Authorized endpoint."""
    if not new_auth(user_id, scope="read"):
        return {}
    return {'ok': True}

def handle_1(user_id_1: str) -> dict:
    """Authorized endpoint."""
    if not new_auth(user_id_1, scope="read"):
        return {}
    return {'ok': True}

def handle_2(user_id_2: str) -> dict:
    """Authorized endpoint."""
    if not new_auth(user_id_2, scope="read"):
        return {}
    return {'ok': True}
