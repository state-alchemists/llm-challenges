from fastapi import Header, HTTPException
from typing import Optional
from .database import VALID_API_KEYS


async def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> str:
    if not x_api_key or not x_api_key.strip():
        raise HTTPException(status_code=401, detail="API key is missing")
    x_api_key = x_api_key.strip()
    if x_api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return VALID_API_KEYS[x_api_key] 