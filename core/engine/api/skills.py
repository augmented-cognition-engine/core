"""Deprecated skill facade over governed recipe proposals and catalog reads."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from core.engine.cognition.contracts import (
    RECIPE_BODY_VERSION,
    CognitionDependencyV1,
    CognitionHeadV1,
    CognitionIdentityV1,
    CognitionOwnerV1,
    CognitionScopeV1,
    CognitionType,
    OwnerKind,
    ScopeKind,
    canonical_hash,
)
from core.engine.cognition.governance import (
    ActorClass,
    CognitionProposalV1,
    ProposalSourceV1,
    ReviewActorV1,
)
from core.engine.cognition.governance_persistence import (
    CognitionGovernanceStore,
    DurableCognitionGovernanceService,
)
from core.engine.cognition.legacy_import import map_skill_row
from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_rows, pool

router = APIRouter(prefix="/skills", tags=["skills"])


class JobRequest(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    archetype: str = Field(min_length=1, max_length=120)
    mode: str = Field(min_length=1, max_length=120)
    frameworks: list[str] = Field(default_factory=list, max_length=64)
    output_format: str = Field(default="prose", min_length=1, max_length=240)
    description: str = Field(default="", max_length=2_000)


class SkillCreateRequest(BaseModel):
    slug: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
    name: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=2_000)
    domain_path: str | None = Field(default=None, max_length=240)
    jobs: list[JobRequest] = Field(min_length=1, max_length=64)
    activation_signals: list[str] = Field(default_factory=list, max_length=128)


class SkillUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, min_length=1, max_length=2_000)
    domain_path: str | None = Field(default=None, max_length=240)
    jobs: list[JobRequest] | None = Field(default=None, min_length=1, max_length=64)
    activation_signals: list[str] | None = Field(default=None, max_length=128)


def _deprecate(response: Response) -> None:
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</cognition/proposals/from-task>; rel="successor-version"'


def _product(user: dict[str, Any], requested: str | None = None) -> str:
    product_id = str(user.get("product") or "")
    if not product_id.startswith("product:"):
        raise HTTPException(status_code=403, detail={"code": "product_scope_required"})
    if requested is not None and requested != product_id:
        raise HTTPException(status_code=403, detail={"code": "foreign_product_scope"})
    return product_id


def _identity(product_id: str, slug: str, *, provenance: str) -> CognitionIdentityV1:
    return CognitionIdentityV1(
        cognition_type=CognitionType.RECIPE,
        owner=CognitionOwnerV1(
            kind=OwnerKind.PRODUCT,
            namespace=product_id,
            provenance=provenance,
        ),
        stable_key=slug,
    )


def _body_from_request(body: SkillCreateRequest) -> dict[str, Any]:
    depth = {
        "reactive": 1,
        "conversational": 1,
        "procedural": 2,
        "deliberative": 3,
        "reflective": 4,
        "exploratory": 4,
    }
    phases = []
    for index, job in enumerate(body.jobs):
        phases.append(
            {
                "cognitive_function": f"legacy_job_{index + 1}",
                "instruments": [{"fallback_slug": slug} for slug in job.frameworks],
                "min_depth": depth.get(job.mode, 2),
                "output_schema": job.output_format,
                "pattern": "solo",
                "must_not": [],
                "must_verify": [],
                "tools": [],
                "signature": 1.0,
            }
        )
    return {
        "slug": body.slug,
        "name": body.name,
        "description": body.description,
        "domain_intelligences": [body.domain_path] if body.domain_path else [],
        "recipe": {"phases": phases},
        "min_execution_depth": min(item["min_depth"] for item in phases),
        "activation_signals": body.activation_signals,
        "archetype_affinity": {},
        "mode_affinity": {},
        "composability": {},
    }


def _dependencies(body: SkillCreateRequest) -> tuple[CognitionDependencyV1, ...]:
    return tuple(
        CognitionDependencyV1(
            cognition_type=CognitionType.FRAMEWORK,
            stable_key=slug,
            owner_namespace="core:frameworks",
        )
        for slug in sorted({slug for job in body.jobs for slug in job.frameworks})
    )


async def _canonical(slug: str, product_id: str):
    store = CognitionGovernanceStore(pool)
    identity = _identity(product_id, slug, provenance="legacy-skill-facade")
    provisional = CognitionHeadV1(
        cognition_id=str(identity.cognition_id),
        scope=CognitionScopeV1(kind=ScopeKind.PRODUCT, product_id=product_id),
        active_revision_id="cognition_revision:lookup",
        authority_receipt_id="cognition_review:lookup",
    )
    head = await store.load_head(str(provisional.head_id))
    if head is None:
        return None, None
    revision = await store.load_revision(head.active_revision_id)
    return head, revision


def _legacy_projection(revision, head) -> dict[str, Any]:
    body = revision.body
    return {
        "id": revision.identity.cognition_id,
        "slug": revision.identity.stable_key,
        "name": body.get("name", revision.identity.stable_key),
        "description": body.get("description", ""),
        "domain_path": next(iter(body.get("domain_intelligences") or []), None),
        "tier": "custom",
        "activation_signals": body.get("activation_signals") or [],
        "jobs": [],
        "canonical_revision_id": revision.revision_id,
        "canonical_head_id": head.head_id,
        "canonical_generation": head.generation,
        "canonical_lifecycle": head.lifecycle,
        "compatibility_disposition": "canonical_projection",
    }


async def _persist_proposal(body: SkillCreateRequest, product_id: str, user: dict[str, Any], *, base=None):
    identity = _identity(product_id, body.slug, provenance="legacy-skill-facade")
    request_material = body.model_dump(mode="json")
    proposal = CognitionProposalV1(
        target_identity=identity,
        scope=CognitionScopeV1(kind=ScopeKind.PRODUCT, product_id=product_id),
        intent="Legacy /skills mutation translated to governed recipe review.",
        sources=(
            ProposalSourceV1(
                source_id=f"legacy-skill-api:{body.slug}",
                source_kind="legacy_api_request",
                content_hash=canonical_hash(request_material),
                relation="requested_change",
            ),
        ),
        base_revision_id=str(base.revision_id) if base is not None else None,
        body_schema_version=RECIPE_BODY_VERSION,
        draft_body=_body_from_request(body),
        dependencies=_dependencies(body),
        created_by=ReviewActorV1(
            actor_id=str(user.get("sub") or "user:unknown"),
            actor_class=ActorClass.HUMAN,
        ),
    )
    return await DurableCognitionGovernanceService(CognitionGovernanceStore(pool)).propose(proposal)


@router.get("")
async def list_skills(
    response: Response,
    product: str = Query(default="product:default"),
    domain_path: str | None = Query(default=None),
    tier: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
):
    _deprecate(response)
    product_id = _product(user, product)
    async with pool.connection() as db:
        where = "(product IS NONE OR product = <record>$product)"
        if domain_path:
            where += " AND domain_path = <string>$dp"
        if tier:
            where += " AND tier = <string>$tier"
        legacy = parse_rows(
            await db.query(
                f"SELECT * FROM skill WHERE {where} ORDER BY name",
                {"product": product_id, "dp": domain_path, "tier": tier},
            )
        )
        heads = parse_rows(
            await db.query(
                "SELECT id, payload FROM cognition_head WHERE scope.product_id = $product ORDER BY id",
                {"product": product_id},
            )
        )
    canonical: list[dict[str, Any]] = []
    for row in heads:
        try:
            head = CognitionHeadV1.model_validate(row.get("payload"))
            revision = await CognitionGovernanceStore(pool).load_revision(head.active_revision_id)
            if revision is not None and revision.identity.cognition_type is CognitionType.RECIPE:
                canonical.append(_legacy_projection(revision, head))
        except Exception:
            continue
    canonical_slugs = {item["slug"] for item in canonical}
    legacy = [item for item in legacy if item.get("slug") not in canonical_slugs]
    return {"skills": sorted(canonical + legacy, key=lambda item: str(item.get("name") or ""))}


@router.get("/{slug}")
async def get_skill(slug: str, response: Response, user: dict = Depends(get_current_user)):
    _deprecate(response)
    product_id = _product(user)
    head, revision = await _canonical(slug, product_id)
    if head is not None and revision is not None:
        return _legacy_projection(revision, head)
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT * FROM skill WHERE slug = <string>$slug "
                "AND (product IS NONE OR product = <record>$product) LIMIT 2",
                {"slug": slug, "product": product_id},
            )
        )
    if not rows:
        raise HTTPException(status_code=404, detail={"code": "skill_alias_not_found"})
    if len(rows) > 1:
        raise HTTPException(status_code=409, detail={"code": "skill_alias_ambiguous"})
    return {**rows[0], "compatibility_disposition": map_skill_row(rows[0]).disposition.value}


@router.post("", status_code=202)
async def create_skill(
    body: SkillCreateRequest,
    response: Response,
    product: str = Query(default="product:default"),
    user: dict = Depends(get_current_user),
):
    _deprecate(response)
    product_id = _product(user, product)
    head, _ = await _canonical(body.slug, product_id)
    if head is not None:
        raise HTTPException(status_code=409, detail={"code": "canonical_recipe_exists"})
    proposal = await _persist_proposal(body, product_id, user)
    return {
        "status": "review_required",
        "compatibility_disposition": "canonical_proposal_created",
        "proposal": proposal,
        "review_endpoint": f"/cognition/proposals/{proposal.proposal_id}/review",
    }


@router.put("/{slug}", status_code=202)
async def update_skill(
    slug: str,
    body: SkillUpdateRequest,
    response: Response,
    user: dict = Depends(get_current_user),
):
    _deprecate(response)
    product_id = _product(user)
    head, revision = await _canonical(slug, product_id)
    if head is None or revision is None:
        raise HTTPException(status_code=404, detail={"code": "canonical_skill_alias_not_found"})
    existing = revision.body
    phases = existing.get("recipe", {}).get("phases", [])
    existing_jobs = [
        JobRequest(
            name=str(item.get("cognitive_function") or f"phase-{index + 1}"),
            archetype="executor",
            mode="procedural",
            frameworks=[
                str(spec.get("slug") or spec.get("fallback_slug"))
                for spec in item.get("instruments", [])
                if spec.get("slug") or spec.get("fallback_slug")
            ],
            output_format=str(item.get("output_schema") or "prose"),
        )
        for index, item in enumerate(phases)
    ]
    merged = SkillCreateRequest(
        slug=slug,
        name=body.name or str(existing.get("name") or slug),
        description=body.description or str(existing.get("description") or "Updated recipe"),
        domain_path=(
            body.domain_path
            if body.domain_path is not None
            else next(iter(existing.get("domain_intelligences") or []), None)
        ),
        jobs=body.jobs or existing_jobs,
        activation_signals=(
            body.activation_signals
            if body.activation_signals is not None
            else list(existing.get("activation_signals") or [])
        ),
    )
    proposal = await _persist_proposal(merged, product_id, user, base=revision)
    return {
        "status": "review_required",
        "compatibility_disposition": "canonical_revision_proposal_created",
        "proposal": proposal,
        "active_generation": head.generation,
    }


@router.delete("/{slug}", status_code=202)
async def delete_skill(slug: str, response: Response, user: dict = Depends(get_current_user)):
    _deprecate(response)
    product_id = _product(user)
    head, revision = await _canonical(slug, product_id)
    if head is not None and revision is not None:
        return {
            "status": "review_required",
            "compatibility_disposition": "retirement_requires_human_lifecycle_review",
            "head_id": head.head_id,
            "expected_head_generation": head.generation,
            "lifecycle_endpoint": f"/cognition/heads/{head.head_id}/lifecycle",
            "history_preserved": True,
        }
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT * FROM skill WHERE slug = <string>$slug AND product = <record>$product LIMIT 2",
                {"slug": slug, "product": product_id},
            )
        )
    if not rows:
        raise HTTPException(status_code=404, detail={"code": "skill_alias_not_found"})
    if len(rows) > 1:
        raise HTTPException(status_code=409, detail={"code": "skill_alias_ambiguous"})
    migration = map_skill_row(rows[0])
    return {
        "status": "not_deleted",
        "compatibility_disposition": migration.disposition.value,
        "migration_receipt": migration,
        "history_preserved": True,
    }
