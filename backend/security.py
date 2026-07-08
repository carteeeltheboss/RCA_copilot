from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from backend.config import get_settings


async def require_internal_token(
    x_rca_service_token: str | None = Header(default=None, alias="X-RCA-Service-Token"),
) -> None:
    configured = get_settings().rca_internal_service_token
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "internal service token is not configured"},
        )
    if not x_rca_service_token or not hmac.compare_digest(x_rca_service_token, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid internal service token"},
        )
