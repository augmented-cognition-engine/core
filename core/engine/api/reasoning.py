# engine/api/reasoning.py
"""Reasoning framework API — list frameworks, get details, view performance.

GET /frameworks — list frameworks (filter by family, tier)
GET /frameworks/{slug} — get a single framework
GET /framework-perf — performance stats per framework
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from core.engine.cognition.contracts import (
    CognitionHeadV1,
    CognitionIdentityV1,
    CognitionOwnerV1,
    CognitionScopeV1,
    CognitionType,
    OwnerKind,
    ScopeKind,
)
from core.engine.cognition.governance_persistence import CognitionGovernanceStore
from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_rows, pool

router = APIRouter(tags=["reasoning"])


def _deprecate(response: Response) -> None:
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</cognition>; rel="successor-version"'


def _product(user: dict[str, Any], requested: str | None = None) -> str:
    product_id = str(user.get("product") or "")
    if not product_id.startswith("product:"):
        raise HTTPException(status_code=403, detail={"code": "product_scope_required"})
    if requested is not None and requested != product_id:
        raise HTTPException(status_code=403, detail={"code": "foreign_product_scope"})
    return product_id


async def _canonical_framework(slug: str, product_id: str):
    identity = CognitionIdentityV1(
        cognition_type=CognitionType.FRAMEWORK,
        owner=CognitionOwnerV1(
            kind=OwnerKind.PRODUCT,
            namespace=product_id,
            provenance="legacy-framework-facade",
        ),
        stable_key=slug,
    )
    lookup = CognitionHeadV1(
        cognition_id=str(identity.cognition_id),
        scope=CognitionScopeV1(kind=ScopeKind.PRODUCT, product_id=product_id),
        active_revision_id="cognition_revision:lookup",
        authority_receipt_id="cognition_review:lookup",
    )
    store = CognitionGovernanceStore(pool)
    head = await store.load_head(str(lookup.head_id))
    if head is None:
        return None, None
    return head, await store.load_revision(head.active_revision_id)


def _project_framework(head, revision) -> dict[str, Any]:
    return {
        **revision.body,
        "id": revision.identity.cognition_id,
        "slug": revision.identity.stable_key,
        "canonical_revision_id": revision.revision_id,
        "canonical_head_id": head.head_id,
        "canonical_generation": head.generation,
        "canonical_lifecycle": head.lifecycle,
        "compatibility_disposition": "canonical_projection",
    }


@router.get("/frameworks")
async def list_frameworks(
    response: Response,
    product: str = Query(default="product:default"),
    family: str | None = Query(default=None),
    tier: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
):
    """List frameworks — built-in + org-specific."""
    _deprecate(response)
    product_id = _product(user, product)
    async with pool.connection() as db:
        where = "(product IS NONE OR product = <record>$product)"
        if family and tier:
            where += " AND family = <string>$family AND tier = <string>$tier"
        elif family:
            where += " AND family = <string>$family"
        elif tier:
            where += " AND tier = <string>$tier"
        result = await db.query(
            f"SELECT * FROM framework WHERE {where} ORDER BY family, name",
            {"product": product_id, "family": family, "tier": tier},
        )
        legacy = parse_rows(result)
        head_rows = parse_rows(
            await db.query(
                "SELECT id, payload FROM cognition_head WHERE scope.product_id = $product ORDER BY id",
                {"product": product_id},
            )
        )
    canonical = []
    for row in head_rows:
        try:
            head = CognitionHeadV1.model_validate(row.get("payload"))
            revision = await CognitionGovernanceStore(pool).load_revision(head.active_revision_id)
            if revision is not None and revision.identity.cognition_type is CognitionType.FRAMEWORK:
                item = _project_framework(head, revision)
                if (family is None or item.get("family") == family) and (
                    tier is None or item.get("tier", "custom") == tier
                ):
                    canonical.append(item)
        except Exception:
            continue
    slugs = {item["slug"] for item in canonical}
    legacy = [item for item in legacy if item.get("slug") not in slugs]
    return {"frameworks": canonical + legacy}


@router.get("/frameworks/{slug}")
async def get_framework(slug: str, response: Response, user: dict = Depends(get_current_user)):
    """Get a single framework by slug."""
    _deprecate(response)
    product_id = _product(user)
    head, revision = await _canonical_framework(slug, product_id)
    if head is not None and revision is not None:
        return _project_framework(head, revision)
    async with pool.connection() as db:
        result = await db.query(
            "SELECT * FROM framework WHERE slug = <string>$slug "
            "AND (product IS NONE OR product = <record>$product) LIMIT 2",
            {"slug": slug, "product": product_id},
        )
        rows = parse_rows(result)
    if not rows:
        raise HTTPException(status_code=404, detail="Framework not found")
    if len(rows) > 1:
        raise HTTPException(status_code=409, detail={"code": "framework_alias_ambiguous"})
    return rows[0]


@router.get("/framework-perf")
async def get_framework_perf(
    product: str = Query(default="product:default"),
    user: dict = Depends(get_current_user),
):
    """Get performance stats for frameworks."""
    product_id = _product(user, product)
    async with pool.connection() as db:
        result = await db.query(
            """
            SELECT framework, task_count, accept_rate, avg_score, last_used
            FROM framework_perf
            WHERE product = <record>$product
            ORDER BY task_count DESC
            """,
            {"product": product_id},
        )
        rows = parse_rows(result)
    return {"performance": rows}
