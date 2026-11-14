from __future__ import annotations

import secrets
from fastapi import Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from packages.common.config import get_settings

api_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


async def require_admin_auth(
    x_admin_key: str | None = Security(api_key_header),
    bearer: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> str:
    """Enforce constant-time API key authentication on all administrative endpoints."""
    settings = get_settings()
    expected = settings.jobre_admin_api_key
    candidate = x_admin_key or (bearer.credentials if bearer else None)

    if not candidate or not secrets.compare_digest(candidate.strip(), expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid administrative credentials required (X-Admin-Key or Bearer token).",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return "admin"
