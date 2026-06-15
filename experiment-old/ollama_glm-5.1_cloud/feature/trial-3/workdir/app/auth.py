from fastapi import Header, HTTPException
from typing import Optional
from .database import VALID_API_KEYS

_MISSING_KEY_DETAIL = "Invalid or missing API key"


async def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> str:
    """Validate the X-API-Key header against VALID_API_KEYS; return the username on success."""
    if x_api_key is None or x_api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=401, detail=_MISSING_KEY_DETAIL)
    return VALID_API_KEYS[x_api_key]