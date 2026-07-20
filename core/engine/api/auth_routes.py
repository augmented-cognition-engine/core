# engine/api/auth_routes.py
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core.engine.core.auth import create_access_token, get_current_user
from core.engine.core.config import settings
from core.engine.core.db import parse_rows, pool

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenRequest(BaseModel):
    api_key: str


class SwitchProductRequest(BaseModel):
    product_id: str


@router.post("/token")
async def create_token(request: Request, body: TokenRequest):
    # Accept api_key or demo_pass (never jwt_secret)
    valid = False
    if settings.api_key and body.api_key == settings.api_key:
        valid = True
    elif settings.demo_pass and body.api_key == settings.demo_pass:
        valid = True
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid API key")
    token = create_access_token({"sub": "user:default", "product": "product:platform"})
    return {"token": token}


@router.post("/token/refresh")
async def refresh_token(user=Depends(get_current_user)):
    """Issue a new token with fresh expiry."""
    token = create_access_token({"sub": user["sub"], "product": user["product"]})
    return {"token": token}


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

    token = create_access_token({"sub": user["sub"], "product": body.product_id})
    return {"token": token}
