"""Recognition API — decision-shaped statement detection and draft management.

POST /recognition/turn         → RecognitionResult
POST /recognition/draft        → DecisionDraft
POST /recognition/{draft_id}/confirm  → dict (persisted decision)
POST /recognition/{draft_id}/dismiss  → 204
PATCH /recognition/{draft_id}        → DecisionDraft (edit before confirm)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.engine.core.auth import get_current_user
from core.engine.recognition import decision_classifier, draft_builder
from core.engine.recognition.models import DecisionDraft, RecognitionResult

logger = logging.getLogger(__name__)
router = APIRouter(tags=["recognition"])


class TurnRequest(BaseModel):
    turn_text: str
    conversation_context: str = ""
    capabilities: list[str] = []


class DraftRequest(BaseModel):
    recognition: RecognitionResult
    product_id: str


class EditRequest(BaseModel):
    title: str | None = None
    rationale: str | None = None
    alternatives: list[str] | None = None
    decision_type: str | None = None


@router.post("/recognition/turn")
async def classify_turn(
    req: TurnRequest,
    user: dict = Depends(get_current_user),
) -> RecognitionResult:
    """Classify a conversation turn for decision-shaped content."""
    return await decision_classifier.classify(
        turn_text=req.turn_text,
        conversation_context=req.conversation_context,
        capabilities=req.capabilities,
    )


@router.post("/recognition/draft")
async def create_draft(
    req: DraftRequest,
    user: dict = Depends(get_current_user),
) -> DecisionDraft:
    """Build a pre-filled DecisionDraft from a RecognitionResult."""
    return draft_builder.build(req.recognition, product_id=req.product_id)


@router.post("/recognition/{draft_id}/confirm")
async def confirm_draft(
    draft_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Persist a draft decision. Returns the created decision record."""
    draft = draft_builder.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found or expired")

    from core.engine.product.decisions import create_decision

    result = await create_decision(
        title=draft.title,
        decision_type=draft.decision_type,
        rationale=draft.rationale,
        product_id=draft.product_id,
        alternatives=draft.alternatives,
        source="recognition",
        affected_capabilities=[draft.likely_capability] if draft.likely_capability else [],
    )
    return result


@router.post("/recognition/{draft_id}/dismiss", status_code=204)
async def dismiss_draft(
    draft_id: str,
    user: dict = Depends(get_current_user),
) -> None:
    """Discard a draft without persisting."""
    from core.engine.recognition.draft_builder import _DRAFT_STORE

    _DRAFT_STORE.pop(draft_id, None)


@router.patch("/recognition/{draft_id}")
async def edit_draft(
    draft_id: str,
    req: EditRequest,
    user: dict = Depends(get_current_user),
) -> DecisionDraft:
    """Edit a draft's fields before confirming."""
    draft = draft_builder.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found or expired")

    updated = draft.model_copy(
        update={
            k: v
            for k, v in {
                "title": req.title,
                "rationale": req.rationale,
                "alternatives": req.alternatives,
                "decision_type": req.decision_type,
            }.items()
            if v is not None
        }
    )

    from core.engine.recognition.draft_builder import _draft_store_put

    _draft_store_put(draft_id, updated)
    return updated
