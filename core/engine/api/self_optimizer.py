"""Deprecated self-optimizer facade over canonical cognition governance."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from core.engine.api.skills import JobRequest, SkillCreateRequest, _body_from_request, _dependencies
from core.engine.cognition.contracts import (
    RECIPE_BODY_VERSION,
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
    ReviewDisposition,
)
from core.engine.cognition.governance_persistence import (
    CognitionGovernanceStore,
    CognitionPersistenceError,
    DurableCognitionGovernanceService,
)
from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_rows, pool

router = APIRouter(prefix="/self-optimizer", tags=["self-optimizer"])

_LEGACY_PROPOSAL_TABLE = "self_optimizer_proposal"
_LEGACY_PROPOSAL_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-") or "proposal"


def _deprecate(response: Response) -> None:
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</cognition/proposals/from-task>; rel="successor-version"'


def _product(user: dict[str, Any], requested: str) -> str:
    product_id = str(user.get("product") or "")
    if not product_id.startswith("product:") or requested != product_id:
        raise HTTPException(status_code=403, detail={"code": "foreign_product_scope"})
    return product_id


def _legacy_proposal_key(proposal_id: str) -> str:
    table, separator, record_key = proposal_id.partition(":")
    if (
        not separator
        or table != _LEGACY_PROPOSAL_TABLE
        or _LEGACY_PROPOSAL_KEY.fullmatch(record_key) is None
    ):
        raise HTTPException(status_code=404, detail="Proposal not found")
    return record_key


def _review_actor(user: dict[str, Any]) -> ReviewActorV1:
    authorities = user.get("authorities")
    return ReviewActorV1(
        actor_id=str(user.get("sub") or "user:unknown"),
        actor_class=ActorClass.HUMAN,
        authorities=tuple(sorted(str(item) for item in authorities)) if isinstance(authorities, list) else (),
    )


def _canonical_proposal(legacy: dict[str, Any], product_id: str, actor: ReviewActorV1) -> CognitionProposalV1:
    proposal_type = str(legacy.get("type") or "")
    if proposal_type not in {"skill", "framework"}:
        raise HTTPException(status_code=422, detail=f"Unsupported proposal type: {proposal_type!r}")
    name = str(legacy.get("name") or "Untitled")
    slug = _slugify(name)
    draft = legacy.get("draft") if isinstance(legacy.get("draft"), dict) else {}
    if proposal_type == "skill":
        raw_jobs = draft.get("jobs") if isinstance(draft.get("jobs"), list) else []
        if not raw_jobs:
            raise HTTPException(status_code=422, detail={"code": "malformed_legacy_skill_proposal"})
        try:
            skill_request = SkillCreateRequest(
                slug=slug,
                name=name,
                description=str(legacy.get("description") or "Legacy optimizer recipe proposal."),
                domain_path=draft.get("domain_path"),
                jobs=[
                    JobRequest(
                        name=str(item.get("name") or f"job-{index + 1}"),
                        archetype=str(item.get("archetype") or "executor"),
                        mode=str(item.get("mode") or "procedural"),
                        frameworks=list(item.get("frameworks") or []),
                        output_format=str(item.get("output_format") or "prose"),
                        description=str(item.get("description") or ""),
                    )
                    for index, item in enumerate(raw_jobs)
                    if isinstance(item, dict)
                ],
                activation_signals=list(draft.get("activation_signals") or []),
            )
        except Exception as exc:
            raise HTTPException(status_code=422, detail={"code": "malformed_legacy_skill_proposal"}) from exc
        cognition_type = CognitionType.RECIPE
        body_schema_version = RECIPE_BODY_VERSION
        canonical_body = _body_from_request(skill_request)
        dependencies = _dependencies(skill_request)
    else:
        cognition_type = CognitionType.FRAMEWORK
        body_schema_version = "ace.cognition.framework/v1"
        canonical_body = {
            "slug": slug,
            "name": name,
            "description": str(legacy.get("description") or ""),
            "family": str(draft.get("family") or "custom"),
            "system_prompt": str(draft.get("system_prompt") or ""),
            "activation_signals": list(draft.get("activation_signals") or []),
            "archetype_affinity": dict(draft.get("archetype_affinity") or {}),
            "mode_affinity": dict(draft.get("mode_affinity") or {}),
            "composability": dict(draft.get("composability") or {}),
        }
        dependencies = ()
    identity = CognitionIdentityV1(
        cognition_type=cognition_type,
        owner=CognitionOwnerV1(
            kind=OwnerKind.PRODUCT,
            namespace=product_id,
            provenance=f"legacy-self-optimizer:{legacy.get('id')}",
        ),
        stable_key=slug,
    )
    return CognitionProposalV1(
        target_identity=identity,
        scope=CognitionScopeV1(kind=ScopeKind.PRODUCT, product_id=product_id),
        intent="Legacy self-optimizer proposal translated for explicit human cognition review.",
        sources=(
            ProposalSourceV1(
                source_id=str(legacy.get("id") or f"self_optimizer_proposal:{slug}"),
                source_kind="legacy_self_optimizer_proposal",
                content_hash=canonical_hash(legacy),
                relation="legacy_proposal",
            ),
        ),
        body_schema_version=body_schema_version,
        draft_body=canonical_body,
        dependencies=dependencies,
        created_by=actor.model_copy(update={"authorities": ()}),
    )


async def _legacy_proposal(proposal_id: str, product_id: str) -> dict[str, Any]:
    record_key = _legacy_proposal_key(proposal_id)
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT * FROM ONLY type::record('self_optimizer_proposal', $record_key)",
                {"record_key": record_key},
            )
        )
    if not rows:
        raise HTTPException(status_code=404, detail="Proposal not found")
    proposal = rows[0]
    if str(proposal.get("product")) != product_id:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal


async def _project_legacy_state(
    proposal_id: str,
    *,
    status: str,
    canonical_proposal_id: str,
    canonical_review_id: str,
) -> str:
    record_key = _legacy_proposal_key(proposal_id)
    try:
        async with pool.connection() as db:
            await db.query(
                "UPDATE ONLY type::record('self_optimizer_proposal', $record_key) "
                "SET status = $status, canonical_proposal_id = $canonical_proposal_id, "
                "canonical_review_id = $canonical_review_id, reviewed_at = time::now()",
                {
                    "record_key": record_key,
                    "status": status,
                    "canonical_proposal_id": canonical_proposal_id,
                    "canonical_review_id": canonical_review_id,
                },
            )
        return "updated"
    except Exception:
        return "unavailable"


@router.get("/proposals")
async def list_proposals(
    response: Response,
    product: str = Query(default="product:default"),
    status: str | None = Query(default=None),
    type: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
):
    _deprecate(response)
    product_id = _product(user, product)
    clauses = ["product = <record>$product"]
    params: dict[str, Any] = {"product": product_id, "status": status, "type": type}
    if status:
        clauses.append("status = $status")
    if type:
        clauses.append("type = $type")
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                f"SELECT * FROM self_optimizer_proposal WHERE {' AND '.join(clauses)} ORDER BY created_at DESC",
                params,
            )
        )
    return {"proposals": rows}


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: str,
    response: Response,
    product: str = Query(default="product:default"),
    user: dict = Depends(get_current_user),
):
    _deprecate(response)
    product_id = _product(user, product)
    actor = _review_actor(user)
    if "cognition-review" not in actor.authorities:
        raise HTTPException(status_code=403, detail={"code": "human_authority_required"})
    legacy = await _legacy_proposal(proposal_id, product_id)
    if legacy.get("status") == "approved":
        raise HTTPException(status_code=409, detail="Proposal is already approved")
    if legacy.get("status") == "dismissed":
        raise HTTPException(status_code=409, detail="Cannot approve a dismissed proposal")
    canonical = _canonical_proposal(legacy, product_id, actor)
    service = DurableCognitionGovernanceService(CognitionGovernanceStore(pool))
    try:
        await service.propose(canonical)
        review = await service.review(
            proposal_id=str(canonical.proposal_id),
            product_id=product_id,
            review_request_id=f"legacy-approve:{proposal_id}",
            actor=actor,
            disposition=ReviewDisposition.APPROVE,
            rationale="Explicit human approval through the deprecated self-optimizer facade.",
            expected_head_generation=0,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"code": "human_authority_required"}) from exc
    except CognitionPersistenceError as exc:
        raise HTTPException(status_code=409, detail={"code": str(exc).split(":", 1)[0]}) from exc
    projection = await _project_legacy_state(
        proposal_id,
        status="approved",
        canonical_proposal_id=str(canonical.proposal_id),
        canonical_review_id=str(review.receipt_id),
    )
    return {
        "proposal_id": proposal_id,
        "status": "approved",
        "type": legacy.get("type"),
        "created": {
            "cognition_id": canonical.target_identity.cognition_id,
            "revision_id": review.result_revision_id,
            "head_id": review.result_head_id,
        },
        "canonical_proposal_id": canonical.proposal_id,
        "canonical_review_id": review.receipt_id,
        "legacy_projection": projection,
    }


@router.post("/proposals/{proposal_id}/dismiss")
async def dismiss_proposal(
    proposal_id: str,
    response: Response,
    product: str = Query(default="product:default"),
    user: dict = Depends(get_current_user),
):
    _deprecate(response)
    product_id = _product(user, product)
    actor = _review_actor(user)
    if "cognition-review" not in actor.authorities:
        raise HTTPException(status_code=403, detail={"code": "human_authority_required"})
    legacy = await _legacy_proposal(proposal_id, product_id)
    if legacy.get("status") == "dismissed":
        raise HTTPException(status_code=409, detail="Proposal is already dismissed")
    canonical = _canonical_proposal(legacy, product_id, actor)
    service = DurableCognitionGovernanceService(CognitionGovernanceStore(pool))
    await service.propose(canonical)
    try:
        review = await service.review(
            proposal_id=str(canonical.proposal_id),
            product_id=product_id,
            review_request_id=f"legacy-dismiss:{proposal_id}",
            actor=actor,
            disposition=ReviewDisposition.REJECT,
            rationale="Explicit human rejection through the deprecated self-optimizer facade.",
            expected_head_generation=0,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"code": "human_authority_required"}) from exc
    projection = await _project_legacy_state(
        proposal_id,
        status="dismissed",
        canonical_proposal_id=str(canonical.proposal_id),
        canonical_review_id=str(review.receipt_id),
    )
    return {
        "proposal_id": proposal_id,
        "status": "dismissed",
        "canonical_proposal_id": canonical.proposal_id,
        "canonical_review_id": review.receipt_id,
        "legacy_projection": projection,
    }
