# engine/api/intel.py
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_rows, pool
from core.engine.intelligence.maturation import calculate_maturation
from core.engine.orchestrator.loader import load_intelligence

router = APIRouter(prefix="/intel", tags=["intelligence"])


async def _load_captured_observations(domain_path: str, product: str) -> list[dict]:
    """Surface durable thin-client captures even before/without synthesis.

    Synthesis enriches observations into insights, but an explicit human
    correction must remain retrievable if no specialty exists or synthesis
    chooses not to emit a new insight.
    """
    try:
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    """SELECT id, content, observation_type, confidence, source, created_at
                       FROM observation
                       WHERE product = <record>$product
                         AND (domain_hint = $domain OR discipline_hint = $domain OR domain_path = $domain)
                       ORDER BY created_at DESC
                       LIMIT 50""",
                    {"product": product, "domain": domain_path},
                )
            )
        return [
            {
                "id": str(row.get("id", "")),
                "content": row.get("content", ""),
                "insight_type": row.get("observation_type", ""),
                "confidence": row.get("confidence", 0.7),
                "created_at": row.get("created_at"),
                "source": row.get("source") or "observation",
            }
            for row in rows
        ]
    except Exception:
        return []


class IntelContextResponse(BaseModel):
    domain_path: str
    insights: list[dict] = []
    corrections: list[dict] = []
    preferences: list[dict] = []
    maturation_level: str = "nascent"
    framework_recommendation: str | None = None
    total_count: int = 0


class IntelSearchResponse(BaseModel):
    query: str
    results: list[dict] = []
    count: int = 0


@router.get("/context", response_model=IntelContextResponse)
async def get_intel_context(
    q: str = Query(..., description="Topic or domain path"),
    product: str = Query(..., description="Organization ID"),
    user: dict = Depends(get_current_user),
):
    """Load intelligence context for a topic. Returns partitioned insights + maturation."""
    product = user.get("product", product)
    domain_path = q.replace(" ", "_").lower()

    snapshot = await load_intelligence(domain_path, product, mode="reactive")

    insights = list(snapshot.get("insights", []))
    captured = await _load_captured_observations(domain_path, product)
    seen = {(item.get("content"), item.get("insight_type")) for item in insights}
    insights.extend(item for item in captured if (item.get("content"), item.get("insight_type")) not in seen)
    corrections = [i for i in insights if i.get("insight_type") == "correction"]
    preferences = [i for i in insights if i.get("insight_type") == "preference"]
    general = [i for i in insights if i.get("insight_type") not in ("correction", "preference")]

    # A flat topic is a discipline. Dotted paths progressively identify deeper
    # specialty nodes; `domain` was the pre-v54 name and is no longer accepted
    # by calculate_maturation().
    parts = domain_path.split(".")
    if len(parts) >= 2:
        node_type = "specialty"
    else:
        node_type = "discipline"

    maturation = await calculate_maturation(node_type, domain_path, product)
    maturation_level = maturation.get("phase_name", "nascent")

    return {
        "domain_path": domain_path,
        "insights": general,
        "corrections": corrections,
        "preferences": preferences,
        "maturation_level": maturation_level,
        "framework_recommendation": None,
        "total_count": len(insights),
    }


@router.get("/search", response_model=IntelSearchResponse)
async def search_intel(
    q: str = Query(..., description="Search query"),
    product: str = Query(..., description="Organization ID"),
    user: dict = Depends(get_current_user),
):
    product = user.get("product", product)
    async with pool.connection() as db:
        results = await db.query(
            """
            SELECT id, content, confidence, tier, insight_type, domain_hint, created_at
            FROM insight
            WHERE product = <record>$product
              AND status = 'active'
              AND content CONTAINS $q
            ORDER BY confidence DESC
            LIMIT 20
            """,
            {"product": product, "q": q},
        )
        rows = parse_rows(results)

    # Serialize RecordID objects to strings for JSON response
    for row in rows:
        if "id" in row:
            row["id"] = str(row["id"])

    return {"query": q, "results": rows, "count": len(rows)}


@router.get("/specialties")
async def list_specialties(
    product: str = Query(..., description="Organization ID"),
    user: dict = Depends(get_current_user),
):
    """List all specialties with their discipline, perspective, and insight counts."""
    product = user.get("product", product)
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT id, slug, name, description, perspective,
                          discipline.slug AS discipline,
                          priority, status, insight_count, bootstrapped
                   FROM specialty
                   WHERE product = <record>$product OR org = <record>product:platform
                   ORDER BY priority ASC, insight_count DESC""",
                {"product": product},
            )
        )
    return {"specialties": rows, "count": len(rows)}


@router.get("/{domain_path:path}/maturation")
async def get_maturation(
    domain_path: str,
    product: str = Query(..., description="Organization ID"),
    user: dict = Depends(get_current_user),
):
    from core.engine.intelligence.maturation import calculate_maturation

    # Resolve discipline/domain_path to the current maturation node types.
    parts = domain_path.split(".")
    if len(parts) >= 2:
        node_type = "specialty"
    else:
        node_type = "discipline"

    product = user.get("product", product)
    result = await calculate_maturation(node_type, domain_path, product)
    return result


@router.get("/{domain_path:path}")
async def get_intel(
    domain_path: str,
    product: str = Query(..., description="Organization ID"),
    user: dict = Depends(get_current_user),
):
    product = user.get("product", product)
    snapshot = await load_intelligence(domain_path, product)
    return snapshot
