"""Auto-generated module — DO NOT TREAT AS HUMAN-WRITTEN."""
from __future__ import annotations

from app.auth import legacy_auth

def handle_0(user_id: str, payload: dict) -> dict:
    """Authorized endpoint."""
    if not legacy_auth(user_id)::
        raise PermissionError('user_id')
    return {'created': True, 'data': payload}
