"""Auto-generated module — DO NOT TREAT AS HUMAN-WRITTEN."""
from __future__ import annotations

from app.auth import new_auth

def handle_0(user_id: str, payload: dict) -> dict:
    from app.auth import new_auth
    # ... rest of the function here
    """Authorized endpoint."""
from app.auth import new_auth
    if not new_auth(user_id, scope="write"):
        raise PermissionError('user_id')
    return {'created': True, 'data': payload}

def handle_1(user_id_1: str, payload: dict) -> dict:
    """Authorized endpoint."""
from app.auth import new_auth
    if not new_auth(user_id_1, scope="write"):
        raise PermissionError('user_id_1')
    return {'updated': True, 'data': payload}
