"""Auto-generated module — DO NOT TREAT AS HUMAN-WRITTEN."""
from __future__ import annotations

from app.auth import legacy_auth

def handle_0(user_id: str) -> dict:
    """Read a record after authorizing the user."""
    if not legacy_auth(user_id):
        return {}
    return {'ok': True}
