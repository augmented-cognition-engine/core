"""Governed-cognition proposal, inspection, and human review API."""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.engine.cognition import composer as composer_module
from core.engine.cognition.catalog import build_default_catalog
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
from core.engine.cognition.discovery import DurableCognitionDiscovery
from core.engine.cognition.governance import (
    ActorClass,
    CognitionProposalV1,
    ProposalSourceV1,
    ReviewActorV1,
    ReviewDisposition,
    build_semantic_diff,
)
from core.engine.cognition.governance_persistence import (
    CognitionGovernanceStore,
    CognitionPersistenceError,
    CognitionScopeError,
    DurableCognitionGovernanceService,
)
from core.engine.cognition.legacy_adapters import meta_skill_from_body
from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_one, parse_record_id, pool

router = APIRouter(prefix="/cognition", tags=["cognition"])


class TeachFromTaskRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=240)
    stable_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
    name: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=2_000)
    intent: str = Field(min_length=1, max_length=2_000)
    base_recipe_slug: str = Field(default="coding_intelligence", min_length=1, max_length=240)
    draft_body: dict[str, Any] | None = None


class ReviewRequest(BaseModel):
    review_request_id: str = Field(min_length=1, max_length=240)
    disposition: Literal["approve", "reject", "request_changes"]
    rationale: str = Field(min_length=1, max_length=4_000)
    expected_head_generation: int = Field(default=0, ge=0)


class LifecycleRequest(BaseModel):
    review_request_id: str = Field(min_length=1, max_length=240)
    action: Literal["rollback", "reactivate", "disable", "expire", "retire"]
    rationale: str = Field(min_length=1, max_length=4_000)
    expected_head_generation: int = Field(ge=1)
    target_revision_id: str | None = Field(default=None, max_length=240)
    expires_at: datetime | None = None


def _product(user: dict[str, Any]) -> str:
    product_id = str(user.get("product") or "")
    if not product_id.startswith("product:"):
        raise HTTPException(status_code=403, detail={"code": "product_scope_required"})
    return product_id


def _actor(user: dict[str, Any], *, proposal: bool = False) -> ReviewActorV1:
    raw_authorities = user.get("authorities")
    authorities = tuple(sorted({str(item) for item in raw_authorities})) if isinstance(raw_authorities, list) else ()
    if proposal:
        authorities = ()
    return ReviewActorV1(
        actor_id=str(user.get("sub") or "user:unknown"),
        actor_class=ActorClass.HUMAN,
        authorities=authorities,
    )


@router.post("/proposals/from-task", status_code=201)
async def teach_from_task(
    body: TeachFromTaskRequest,
    user: dict[str, Any] = Depends(get_current_user),
):
    product_id = _product(user)
    async with pool.connection() as db:
        task = parse_one(
            await db.query(
                "SELECT id, product, description, output, decision_receipt, "
                "deliberation_receipt, intelligence_use_receipt "
                "FROM ONLY <record>$task WHERE product = $product LIMIT 1",
                {"task": parse_record_id(body.task_id), "product": parse_record_id(product_id)},
            )
        )
    if not task:
        raise HTTPException(status_code=404, detail={"code": "task_not_found"})

    catalog = build_default_catalog(core_yaml=composer_module._RECIPE_YAML)
    if catalog.recipe(body.stable_key) is not None:
        raise HTTPException(status_code=409, detail={"code": "cognition_identity_conflict"})
    template = catalog.recipe_revision(body.base_recipe_slug)
    if template is None:
        raise HTTPException(status_code=422, detail={"code": "base_recipe_unavailable"})
    draft = copy.deepcopy(body.draft_body if body.draft_body is not None else template.body)
    draft.update({"slug": body.stable_key, "name": body.name, "description": body.description})
    try:
        meta_skill_from_body(draft)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "malformed_cognition", "reason": type(exc).__name__},
        ) from exc

    identity = CognitionIdentityV1(
        cognition_type=CognitionType.RECIPE,
        owner=CognitionOwnerV1(
            kind=OwnerKind.PRODUCT,
            namespace=product_id,
            provenance=f"task-teach:{body.task_id}",
        ),
        stable_key=body.stable_key,
    )
    source_payload = {
        "id": str(task.get("id") or body.task_id),
        "product": str(task.get("product") or product_id),
        "description": task.get("description"),
        "output": task.get("output"),
        "decision_receipt": task.get("decision_receipt"),
        "deliberation_receipt": task.get("deliberation_receipt"),
        "intelligence_use_receipt": task.get("intelligence_use_receipt"),
    }
    proposal = CognitionProposalV1(
        target_identity=identity,
        scope=CognitionScopeV1(kind=ScopeKind.PRODUCT, product_id=product_id),
        intent=body.intent,
        sources=(
            ProposalSourceV1(
                source_id=str(task.get("id") or body.task_id),
                source_kind="task",
                content_hash=canonical_hash(source_payload),
                relation="taught_from",
            ),
        ),
        body_schema_version=RECIPE_BODY_VERSION,
        draft_body=draft,
        dependencies=template.dependencies,
        created_by=_actor(user, proposal=True),
    )
    service = DurableCognitionGovernanceService(CognitionGovernanceStore(pool))
    stored = await service.propose(proposal)
    diff = build_semantic_diff(stored, base_revision=None)
    return {"proposal": stored, "semantic_diff": diff, "selectable": False}


@router.get("/proposals/{proposal_id}")
async def get_proposal(proposal_id: str, user: dict[str, Any] = Depends(get_current_user)):
    product_id = _product(user)
    store = CognitionGovernanceStore(pool)
    proposal = await store.load_proposal(proposal_id, product_id=product_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail={"code": "proposal_not_found"})
    state = await store.load_proposal_state(proposal_id, product_id=product_id)
    return {"proposal": proposal, "state": state, "selectable": False}


@router.get("/proposals/{proposal_id}/diff")
async def get_proposal_diff(proposal_id: str, user: dict[str, Any] = Depends(get_current_user)):
    product_id = _product(user)
    store = CognitionGovernanceStore(pool)
    proposal = await store.load_proposal(proposal_id, product_id=product_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail={"code": "proposal_not_found"})
    base = await store.load_revision(proposal.base_revision_id) if proposal.base_revision_id else None
    return build_semantic_diff(proposal, base_revision=base)


@router.post("/proposals/{proposal_id}/review")
async def review_proposal(
    proposal_id: str,
    body: ReviewRequest,
    user: dict[str, Any] = Depends(get_current_user),
):
    product_id = _product(user)
    service = DurableCognitionGovernanceService(CognitionGovernanceStore(pool))
    try:
        receipt = await service.review(
            proposal_id=proposal_id,
            product_id=product_id,
            review_request_id=body.review_request_id,
            actor=_actor(user),
            disposition=ReviewDisposition(body.disposition),
            rationale=body.rationale,
            expected_head_generation=body.expected_head_generation,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"code": "human_authority_required"}) from exc
    except CognitionScopeError as exc:
        raise HTTPException(status_code=404, detail={"code": "proposal_not_found"}) from exc
    except CognitionPersistenceError as exc:
        raise HTTPException(status_code=409, detail={"code": str(exc).split(":", 1)[0]}) from exc
    return {"review_receipt": receipt}


@router.get("/revisions/{revision_id}")
async def get_revision(revision_id: str, user: dict[str, Any] = Depends(get_current_user)):
    _product(user)
    revision = await CognitionGovernanceStore(pool).load_revision(revision_id)
    if revision is None or revision.identity.owner.namespace != str(user.get("product")):
        raise HTTPException(status_code=404, detail={"code": "revision_not_found"})
    return revision


@router.get("/heads/{head_id}")
async def get_head(head_id: str, user: dict[str, Any] = Depends(get_current_user)):
    product_id = _product(user)
    head = await CognitionGovernanceStore(pool).load_head(head_id)
    if head is None or head.scope.product_id != product_id:
        raise HTTPException(status_code=404, detail={"code": "head_not_found"})
    return head


@router.post("/heads/{head_id}/lifecycle")
async def transition_head(
    head_id: str,
    body: LifecycleRequest,
    user: dict[str, Any] = Depends(get_current_user),
):
    from core.engine.cognition.lifecycle import CognitionLifecycleService, LifecycleAction

    product_id = _product(user)
    try:
        receipt = await CognitionLifecycleService(pool).transition(
            head_id=head_id,
            product_id=product_id,
            review_request_id=body.review_request_id,
            actor=_actor(user),
            action=LifecycleAction(body.action),
            rationale=body.rationale,
            expected_generation=body.expected_head_generation,
            target_revision_id=body.target_revision_id,
            expires_at=body.expires_at,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"code": "human_authority_required"}) from exc
    except CognitionScopeError as exc:
        raise HTTPException(status_code=404, detail={"code": "head_not_found"}) from exc
    except CognitionPersistenceError as exc:
        raise HTTPException(status_code=409, detail={"code": str(exc).split(":", 1)[0]}) from exc
    return {"lifecycle_receipt": receipt}


@router.get("/selections/{receipt_id}")
async def get_selection_receipt(receipt_id: str, user: dict[str, Any] = Depends(get_current_user)):
    product_id = _product(user)
    receipt = await DurableCognitionDiscovery(pool).load_selection(receipt_id, product_id=product_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail={"code": "selection_receipt_not_found"})
    return receipt


@router.get("/uses/{receipt_id}")
async def get_use_receipt(receipt_id: str, user: dict[str, Any] = Depends(get_current_user)):
    product_id = _product(user)
    receipt = await DurableCognitionDiscovery(pool).load_use(receipt_id, product_id=product_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail={"code": "use_receipt_not_found"})
    return receipt
