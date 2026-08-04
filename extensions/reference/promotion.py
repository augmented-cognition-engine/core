"""Reference task action for authoritative TP7 promotion review."""

from __future__ import annotations

import json
from datetime import datetime

from pydantic import TypeAdapter

from core.engine.core.db import pool
from core.engine.extensions import (
    ContextResolution,
    ExtensionActorContext,
    ExtensionInvocationEnvelope,
    ExtensionOutcome,
    ExtensionTaskPlan,
    ResolvedContextRecord,
)
from core.engine.grounded_state.belief_contracts import ReviewAuthority
from core.engine.grounded_state.promotion import PromotionService
from core.engine.grounded_state.promotion_contracts import PromotionDisposition

OUTCOME_CONTRACT = "product.grounded-promotion-review-outcome-v1"


async def prepare_promotion_review(
    envelope: ExtensionInvocationEnvelope,
    actor: ExtensionActorContext,
) -> ExtensionTaskPlan:
    """Apply one already-authorized human disposition to an exact proposal."""
    if len(envelope.references) != 1:
        raise ValueError("promotion-review requires exactly one promotion proposal reference")
    reference = envelope.references[0]
    if reference.kind != "promotion_proposal":
        raise ValueError("promotion-review reference kind must be promotion_proposal")
    params = envelope.parameters
    reviewed_at = TypeAdapter(datetime).validate_python(params.get("reviewed_at"))
    disposition = PromotionDisposition(params.get("disposition"))
    receipt = await PromotionService(pool).review(
        proposal_id=reference.id,
        product_id=actor.product_id,
        disposition=disposition,
        authority=ReviewAuthority.HUMAN,
        reviewer_ref=actor.user_id,
        authority_scope="state-engine-promotion-review",
        rationale=str(params.get("rationale") or "Explicit authenticated promotion review."),
        reviewed_at=reviewed_at,
        expires_at=(
            TypeAdapter(datetime).validate_python(params["expires_at"])
            if params.get("expires_at") is not None
            else None
        ),
        supersedes_receipt_ids=tuple(params.get("supersedes_receipt_ids") or ()),
        invalidates_receipt_ids=tuple(params.get("invalidates_receipt_ids") or ()),
        contests_receipt_ids=tuple(params.get("contests_receipt_ids") or ()),
    )
    content = json.dumps(
        {
            "contract_version": receipt.contract_version,
            "receipt_id": receipt.receipt_id,
            "receipt_hash": receipt.receipt_hash,
            "disposition": receipt.disposition.value,
            "memory_id": receipt.memory_id,
            "beneficial_impact_supported": False,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    resolution = ContextResolution(
        reference=reference,
        status="resolved",
        resolver="ace.grounded-state.promotion-resolver/v1",
        record_version=receipt.contract_version,
        content_hash=str(receipt.receipt_hash),
        product_scope=actor.product_id,
        provenance={
            "source": "Core TP7 promotion lifecycle",
            "scope": actor.product_id,
            "integrity": "immutable_promotion_receipt_hash",
            "proposal_id": receipt.proposal_id,
            "review_id": receipt.review_id,
        },
        note="Authoritative disposition was applied before reporting; model output has no lifecycle authority.",
    )
    return ExtensionTaskPlan(
        description=(
            "Report the already-persisted promotion disposition and identifiers. Do not reinterpret, "
            "accept, reject, invalidate, supersede, or modify the authoritative receipt."
        ),
        context_resolution=[resolution],
        context_records=[
            ResolvedContextRecord(
                reference=reference,
                resolver_identity=resolution.resolver,
                record_version=receipt.contract_version,
                content_hash=str(receipt.receipt_hash),
                product_scope=actor.product_id,
                content=content,
            )
        ],
        outcome_contract=OUTCOME_CONTRACT,
    )


def project_promotion_review(output: str | None, execution: dict) -> ExtensionOutcome:
    return ExtensionOutcome(
        contract_version=OUTCOME_CONTRACT,
        data={
            "reporting_content": output,
            "execution_state": execution.get("state"),
            "record_meaning": "report_of_preexisting_authoritative_promotion_receipt",
            "model_lifecycle_authority": False,
            "beneficial_impact_supported": False,
        },
        warnings=[] if output else ["Authoritative receipt persisted, but no reporting content was returned."],
    )
