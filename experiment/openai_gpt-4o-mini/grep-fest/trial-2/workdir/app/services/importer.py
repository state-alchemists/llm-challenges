"""Auto-generated module — DO NOT TREAT AS HUMAN-WRITTEN."""
from __future__ import annotations

from app.auth import new_auth

def handle_0(user_id: str, payload: dict) -> dict:
    """Authorized endpoint."""
    if not new_auth(user_id, scope="read"):
        raise PermissionError('user_id')
    return {'created': True, 'data': payload}
