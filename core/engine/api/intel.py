# engine/api/intel.py
import re

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_rows, pool
from core.engine.intelligence.maturation import calculate_maturation
from core.engine.orchestrator.loader import load_intelligence
from core.engine.product.correction_receipts import effective_correction_lifecycle

router = APIRouter(prefix="/intel", tags=["intelligence"])


def _bounded_public_content(value: object) -> str:
    text = str(value or "")
    text = re.sub(
        r"(?i)\b(bearer|api[_-]?key|token|password|secret)\b\s*[:=]?\s*[^\s,;]+",
        r"\1=<redacted>",
        text,
    )
    return text[:2_000]


def _record_text(value: object) -> str | None:
    return str(value)[:200] if value is not None else None


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
                    """SELECT id, content, observation_type, confidence, source, created_at,
                              source_surface, actor_ref, actor_class, content_hash, lifecycle_state,
                              correction_contract_version, affected_decision, affected_task,
                              supersedes_correction, invalidates_correction, contests_correction,
                              expires_at
                       FROM observation
                       WHERE product = <record>$product
                         AND (domain_hint = $domain OR discipline_hint = $domain OR domain_path = $domain)
                       ORDER BY created_at DESC
                       LIMIT 50""",
                    {"product": product, "domain": domain_path},
                )
            )
        captured = []
        for row in rows:
            item = {
                "id": str(row.get("id", "")),
                "content": _bounded_public_content(row.get("content")),
                "insight_type": row.get("observation_type", ""),
                "confidence": row.get("confidence", 0.7),
                "created_at": row.get("created_at"),
                "source": row.get("source") or "observation",
            }
            if row.get("observation_type") == "correction":
                stored_version = row.get("correction_contract_version")
                contract_compatible = stored_version in {None, "correction-v1"}
                version_current = stored_version == "correction-v1"
                provenance_fields = {
                    "source_surface": row.get("source_surface"),
                    "actor": row.get("actor_ref"),
                    "actor_class": row.get("actor_class"),
                    "content_hash": row.get("content_hash"),
                    "recorded_at": row.get("created_at"),
                }
                missing_provenance = [name for name, value in provenance_fields.items() if value is None or value == ""]
                if not version_current:
                    missing_provenance.insert(0, "contract_version")
                stored_lifecycle = row.get("lifecycle_state") if contract_compatible else None
                item.update(
                    {
                        "contract_version": "correction-v1",
                        "compatibility": {
                            "state": "complete" if version_current else "degraded",
                            "reason": (
                                None
                                if version_current
                                else (
                                    "legacy_missing_contract_version"
                                    if stored_version is None
                                    else "unsupported_stored_contract_version"
                                )
                            ),
                            "stored_contract_version": _record_text(stored_version),
                        },
                        "correction_id": str(row.get("id", "")),
                        "product_id": str(product),
                        "lifecycle_state": (
                            effective_correction_lifecycle(stored_lifecycle, row.get("expires_at"))
                            if contract_compatible
                            else None
                        ),
                        "stored_lifecycle_state": stored_lifecycle,
                        "expires_at": row.get("expires_at") if contract_compatible else None,
                        "content_hash": row.get("content_hash") if contract_compatible else None,
                        "relationship": {
                            "affected_decision_id": (
                                _record_text(row.get("affected_decision")) if contract_compatible else None
                            ),
                            "affected_task_id": _record_text(row.get("affected_task")) if contract_compatible else None,
                            "supersedes_correction_id": (
                                _record_text(row.get("supersedes_correction")) if contract_compatible else None
                            ),
                            "invalidates_correction_id": (
                                _record_text(row.get("invalidates_correction")) if contract_compatible else None
                            ),
                            "contests_correction_id": (
                                _record_text(row.get("contests_correction")) if contract_compatible else None
                            ),
                        },
                        "provenance": {
                            "source_surface": row.get("source_surface"),
                            "actor": _record_text(row.get("actor_ref")),
                            "actor_class": row.get("actor_class"),
                            "recorded_at": row.get("created_at"),
                            "completeness": "complete" if not missing_provenance else "incomplete",
                            "missing_fields": missing_provenance,
                        },
                    }
                )
            captured.append(item)
        return captured
    except Exception:
        return []


class IntelContextResponse(BaseModel):
    domain_path: str
    insights: list[dict] = []
    corrections: list[dict] = []
    preferences: list[dict] = []
    maturation_level: str = "nascent"
    maturation: dict = Field(default_factory=dict)
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
    captured_corrections = [item for item in captured if item.get("insight_type") == "correction"]
    correction_content = {item.get("content") for item in captured_corrections}
    corrections = captured_corrections + [
        item
        for item in insights
        if item.get("insight_type") == "correction" and item.get("content") not in correction_content
    ]
    seen = {(item.get("content"), item.get("insight_type")) for item in insights}
    merged = insights + [
        item
        for item in captured
        if item.get("insight_type") != "correction" and (item.get("content"), item.get("insight_type")) not in seen
    ]
    preferences = [i for i in merged if i.get("insight_type") == "preference"]
    general = [i for i in merged if i.get("insight_type") not in ("correction", "preference")]

    # A flat topic is a discipline. Dotted paths progressively identify deeper
    # specialty nodes; `domain` was the pre-v54 name and is no longer accepted
    # by calculate_maturation().
    parts = domain_path.split(".")
    if len(parts) >= 2:
        node_type = "specialty"
    else:
        node_type = "discipline"

    try:
        maturation = await calculate_maturation(node_type, domain_path, product)
        maturation_level = maturation.get("phase_name", "nascent")
        maturation_state = {"state": "complete", "reason": None}
    except Exception:
        maturation_level = "nascent"
        maturation_state = {"state": "degraded", "reason": "maturation_unavailable"}

    return {
        "domain_path": domain_path,
        "insights": general,
        "corrections": corrections,
        "preferences": preferences,
        "maturation_level": maturation_level,
        "maturation": maturation_state,
        "framework_recommendation": None,
        "total_count": len(general) + len(corrections) + len(preferences),
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
