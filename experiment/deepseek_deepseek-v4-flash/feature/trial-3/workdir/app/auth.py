from fastapi import Header, HTTPException, status
from typing import Optional
from .database import VALID_API_KEYS


async def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> str:
    """Validate the X-API-Key header against VALID_API_KEYS; return the username on success."""
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")
    username = VALID_API_KEYS.get(x_api_key)
    if username is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return username
