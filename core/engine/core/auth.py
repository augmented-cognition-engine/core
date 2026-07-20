# engine/core/auth.py
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError

from core.engine.core.config import settings

_bearer = HTTPBearer(auto_error=False)


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.jwt_expire_minutes))
    payload["exp"] = expire
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_ownership(record: dict, user: dict) -> None:
    """Verify the requesting user's org matches the record's org. Returns 404 to avoid leaking existence."""
    record_org = str(record.get("product", ""))
    user_org = str(user.get("product", ""))
    if record_org and user_org and record_org != user_org:
        raise HTTPException(status_code=404, detail="Not found")


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    # Header auth: Authorization: Bearer <token>
    if credentials:
        return verify_token(credentials.credentials)
    # Query param auth: ?token=<token> — used by EventSource (SSE) which can't set headers
    token = request.query_params.get("token")
    if token:
        return verify_token(token)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
