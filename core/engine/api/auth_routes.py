# engine/api/auth_routes.py
import re
from secrets import compare_digest

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core.engine.core.auth import create_access_token, get_current_user
from core.engine.core.config import settings
from core.engine.core.db import parse_rows, pool
from core.engine.core.governed_state import GovernedStatePersistenceError, SurrealGovernedStateStore
from core.engine.core.local_owner_authority import (
    LocalOwnerAuthorityBootstrapResult,
    LocalOwnerAuthorityConflict,
    LocalOwnerAuthorityDenied,
    bootstrap_local_owner_authority,
)

router = APIRouter(prefix="/auth", tags=["auth"])

COGNITION_REVIEW_AUTHORITY = "cognition-review"
LOCAL_OWNER_AUTHORITIES = (
    COGNITION_REVIEW_AUTHORITY,
    "intelligence_build",
    "observe_read",
    "deliver_export",
    "administer_lifecycle",
)
MAX_TOKEN_AUTHORITIES = 50
_AUTHORITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")


class TokenRequest(BaseModel):
    api_key: str


class SwitchProductRequest(BaseModel):
    product_id: str


def local_owner_authority_store() -> SurrealGovernedStateStore:
    return SurrealGovernedStateStore(pool)


def _bounded_authorities(user: dict) -> list[str]:
    raw = user.get("authorities", ())
    if raw is None:
        return []
    if (
        not isinstance(raw, (list, tuple))
        or len(raw) > MAX_TOKEN_AUTHORITIES
        or any(not isinstance(item, str) or not _AUTHORITY.fullmatch(item) for item in raw)
    ):
        raise HTTPException(status_code=401, detail="Invalid authority claims")
    authorities = sorted(set(raw))
    return authorities


@router.post("/token")
async def create_token(request: Request, body: TokenRequest):
    # Accept api_key or demo_pass (never jwt_secret)
    api_key = str(settings.api_key or "")
    demo_pass = str(settings.demo_pass or "")
    if api_key and demo_pass and compare_digest(api_key, demo_pass):
        raise HTTPException(status_code=503, detail="Authentication credentials are misconfigured")
    is_api_key = bool(api_key) and compare_digest(body.api_key, api_key)
    is_demo_pass = bool(demo_pass) and compare_digest(body.api_key, demo_pass)
    if not is_api_key and not is_demo_pass:
        raise HTTPException(status_code=401, detail="Invalid API key")
    authorities = sorted(LOCAL_OWNER_AUTHORITIES) if is_api_key else []
    token = create_access_token(
        {
            "sub": "user:default",
            "product": "product:platform",
            "authorities": authorities,
            "local_owner": is_api_key,
        }
    )
    return {"token": token}


@router.post("/token/refresh")
async def refresh_token(user=Depends(get_current_user)):
    """Issue a new token with fresh expiry."""
    token = create_access_token(
        {
            "sub": user["sub"],
            "product": user["product"],
            "authorities": _bounded_authorities(user),
            "local_owner": user.get("local_owner") is True,
        }
    )
    return {"token": token}


@router.post("/local-owner/bootstrap", response_model=LocalOwnerAuthorityBootstrapResult)
async def bootstrap_local_owner(
    user=Depends(get_current_user),
    store=Depends(local_owner_authority_store),
):
    """Create or verify the four fixed grants for the local single-user owner."""

    try:
        return await bootstrap_local_owner_authority(
            user=user,
            store=store,
        )
    except LocalOwnerAuthorityDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LocalOwnerAuthorityConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except GovernedStatePersistenceError as exc:
        raise HTTPException(status_code=503, detail="Local-owner authority storage is unavailable") from exc


@router.post("/switch-product")
async def switch_product(body: SwitchProductRequest, user=Depends(get_current_user)):
    """Re-issue JWT scoped to a different product. Used by the portal."""
    async with pool.connection() as db:
        # Fetch the caller's tenant from their current product
        t_result = await db.query(
            "SELECT tenant FROM product WHERE id = <record>$product LIMIT 1",
            {"product": user["product"]},
        )
        t_rows = parse_rows(t_result)
        caller_tenant = str(t_rows[0]["tenant"]) if t_rows and t_rows[0].get("tenant") else None

        # Validate target product exists AND belongs to the same tenant
        result = await db.query(
            "SELECT id FROM product WHERE id = <record>$product AND tenant = <record>$tenant LIMIT 1",
            {"product": body.product_id, "tenant": caller_tenant},
        )
        if not parse_rows(result):
            raise HTTPException(status_code=404, detail=f"Product '{body.product_id}' not found")

    token = create_access_token(
        {
            "sub": user["sub"],
            "product": body.product_id,
            "authorities": _bounded_authorities(user),
            "local_owner": user.get("local_owner") is True,
        }
    )
    return {"token": token}
