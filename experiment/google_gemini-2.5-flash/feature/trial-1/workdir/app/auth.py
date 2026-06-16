from fastapi import Header, HTTPException
from typing import Optional
from .database import VALID_API_KEYS


async def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> str:
    """Validate the X-API-Key header against VALID_API_KEYS; return the username on success."""
    from fastapi import status # Import status for HTTP status codes
    if x_api_key is None or x_api_key not in VALID_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
        )
    return VALID_API_KEYS[x_api_key]
