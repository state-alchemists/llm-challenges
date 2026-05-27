"""Auto-generated module — DO NOT TREAT AS HUMAN-WRITTEN."""
from __future__ import annotations

from app.auth import legacy_auth

def handle_0(user_id: str, payload: dict) -> dict:
    """Create a record after authorizing the user."""
    if not legacy_auth(user_id):
        raise PermissionError('user_id')
    return {'created': True, 'data': payload}

def handle_1(user_id_1: str, payload: dict) -> dict:
    """Update a record after authorizing the user."""
    if not legacy_auth(user_id_1):
        raise PermissionError('user_id_1')
    return {'updated': True, 'data': payload}
