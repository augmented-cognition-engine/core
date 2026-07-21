"""Authenticated, read-only public access to the Living Product Graph."""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status

from core.engine.core.auth import get_current_user
from core.engine.core.db import pool
from core.engine.product.living_graph import PROJECTION_VERSION, LivingProductGraphService
from core.engine.product.living_graph_store import SurrealLivingProductGraphStore

router = APIRouter(tags=["product"])
logger = logging.getLogger(__name__)

_PRODUCT_ID = re.compile(r"product:[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")


def _failure(code: str, message: str, recovery: str, **metadata: object) -> dict[str, object]:
    return {"code": code, "message": message, "recovery": recovery, **metadata}


@router.get("/product/landscape")
async def get_product_landscape(
    projection_version: str = Query(default=PROJECTION_VERSION, max_length=128),
    user: dict = Depends(get_current_user),
):
    """Inspect the authenticated product's deterministic, read-only graph projection."""
    if projection_version != PROJECTION_VERSION:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_failure(
                "unsupported_projection_version",
                "The requested Living Product Graph projection version is not supported.",
                f"Retry with projection_version={PROJECTION_VERSION}.",
                requested=projection_version,
                supported=[PROJECTION_VERSION],
            ),
        )

    product_id = str(user.get("product", ""))
    if not _PRODUCT_ID.fullmatch(product_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_failure(
                "malformed_product_identity",
                "The authenticated product identity is not a canonical product:<slug> identifier.",
                "Authenticate again with a token scoped to an existing product.",
            ),
        )

    try:
        service = LivingProductGraphService(SurrealLivingProductGraphStore(pool))
        return await service.snapshot(product_id)
    except Exception:
        logger.error("Living Product Graph projection failed for the authenticated product")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_failure(
                "landscape_temporarily_unavailable",
                "The Living Product Graph could not be inspected safely.",
                "Run `ace doctor`, restore the database if needed, and retry the same read.",
            ),
        ) from None
