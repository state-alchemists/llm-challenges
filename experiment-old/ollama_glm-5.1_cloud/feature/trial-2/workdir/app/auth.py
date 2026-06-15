from fastapi import Header, HTTPException
from typing import Optional
from .database import VALID_API_KEYS

MISSING_KEY_MESSAGE = "Missing X-API-Key header"
INVALID_KEY_MESSAGE = "Invalid API key"


async def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> str:
    """Validate the X-API-Key header against VALID_API_KEYS; return the username on success."""
    if x_api_key is None:
        raise HTTPException(status_code=401, detail=MISSING_KEY_MESSAGE)
    username = VALID_API_KEYS.get(x_api_key)
    if username is None:
        raise HTTPException(status_code=401, detail=INVALID_KEY_MESSAGE)
    return username
