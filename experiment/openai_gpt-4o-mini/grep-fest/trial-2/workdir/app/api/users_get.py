"""Auto-generated module — DO NOT TREAT AS HUMAN-WRITTEN."""
from __future__ import annotations

from app.auth import new_auth

def handle_0(user_id: str) -> dict:
    from app.auth import new_auth
    # ... rest of the function here
    """Authorized endpoint."""
from app.auth import new_auth
    if not new_auth(user_id, scope="read"):
        return {}
    return {'ok': True}
