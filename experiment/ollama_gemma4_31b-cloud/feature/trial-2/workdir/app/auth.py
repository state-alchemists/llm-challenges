from fastapi import Header, HTTPException
from typing import Optional
from .database import VALID_API_KEYS


async def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> str:
    """Validate the X-API-Key header against VALID_API_KEYS; return the username on success."""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key missing")
    
    user = VALID_API_KEYS.get(x_api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return user
