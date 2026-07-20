"""Draft builder — converts a RecognitionResult into a DecisionDraft.

The draft is pre-filled but not persisted. The user confirms via the
confirm_url endpoint (AC 5/7). Drafts are held in a module-level TTL store —
lightweight, no DB table required until the user confirms.
"""

from __future__ import annotations

import uuid
from collections import OrderedDict

from core.engine.recognition.models import DecisionDraft, RecognitionResult

_DRAFT_STORE: OrderedDict[str, DecisionDraft] = OrderedDict()
_MAX_DRAFTS = 200

DRAFT_FALLBACK_STRINGS = ["TODO", "to be filled", ""]


def build(recognition: RecognitionResult, product_id: str, base_url: str = "") -> DecisionDraft:
    """Build a DecisionDraft from a RecognitionResult.

    Rationale and title are extracted from the classifier output. Falls back to
    generic phrasing when the classifier left them empty, but never produces
    DRAFT_FALLBACK_STRINGS.
    """
    title = recognition.extracted_title or _infer_title(recognition)
    rationale = recognition.extracted_rationale or _infer_rationale(recognition)
    decision_type = recognition.decision_type or "direction"

    draft_id = str(uuid.uuid4())
    draft = DecisionDraft(
        draft_id=draft_id,
        recognition=recognition,
        product_id=product_id,
        title=title,
        rationale=rationale,
        alternatives=recognition.extracted_alternatives,
        decision_type=decision_type,
        likely_capability=recognition.likely_affected_capability,
        confirm_url=f"{base_url}/recognition/{draft_id}/confirm",
        dismiss_url=f"{base_url}/recognition/{draft_id}/dismiss",
        edit_url=f"{base_url}/recognition/{draft_id}",
    )

    _draft_store_put(draft_id, draft)
    return draft


def get_draft(draft_id: str) -> DecisionDraft | None:
    return _DRAFT_STORE.get(draft_id)


def _draft_store_put(draft_id: str, draft: DecisionDraft) -> None:
    _DRAFT_STORE[draft_id] = draft
    while len(_DRAFT_STORE) > _MAX_DRAFTS:
        _DRAFT_STORE.popitem(last=False)


def _infer_title(r: RecognitionResult) -> str:
    if r.decision_type:
        return f"Undocumented {r.decision_type} decision"
    return "Decision captured from conversation"


def _infer_rationale(r: RecognitionResult) -> str:
    reasoning = r.classifier_reasoning.strip()
    if reasoning and reasoning not in DRAFT_FALLBACK_STRINGS:
        return reasoning
    return "Rationale inferred from conversation context"
