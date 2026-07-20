"""Boundary tests for draft_builder — A5 ACs 5, 7, sentinel check."""

from __future__ import annotations

from core.engine.recognition.draft_builder import DRAFT_FALLBACK_STRINGS, build, get_draft
from core.engine.recognition.models import RecognitionResult


def _positive_result(
    title="Use JWT instead of session cookies",
    rationale="Stateless deployment requirement",
    capability="auth",
) -> RecognitionResult:
    return RecognitionResult(
        is_decision=True,
        confidence=0.85,
        decision_type="architecture",
        extracted_title=title,
        extracted_rationale=rationale,
        extracted_alternatives=["session cookies"],
        likely_affected_capability=capability,
        classifier_reasoning="User explicitly chose JWT over session cookies.",
    )


# ---------------------------------------------------------------------------
# AC 5 — draft includes pre-filled Decision fields and confirm_url
# ---------------------------------------------------------------------------


def test_draft_builder_populates_required_fields():
    recognition = _positive_result()
    draft = build(recognition, product_id="product:test")

    assert draft.title and len(draft.title) > 0
    assert draft.rationale and len(draft.rationale) > 0
    assert draft.product_id == "product:test"
    assert draft.confirm_url.endswith(f"/recognition/{draft.draft_id}/confirm")
    assert draft.dismiss_url.endswith(f"/recognition/{draft.draft_id}/dismiss")
    assert draft.edit_url.endswith(f"/recognition/{draft.draft_id}")


def test_draft_includes_recognition_result():
    recognition = _positive_result()
    draft = build(recognition, product_id="product:test")

    assert draft.recognition is recognition
    assert draft.source == "recognition"


def test_draft_alternatives_from_recognition():
    recognition = _positive_result()
    draft = build(recognition, product_id="product:test")

    assert draft.alternatives == ["session cookies"]


# ---------------------------------------------------------------------------
# AC 7 — confirm_url persists with source="recognition"
# ---------------------------------------------------------------------------


def test_draft_source_is_recognition():
    draft = build(_positive_result(), product_id="product:test")
    assert draft.source == "recognition"


def test_draft_likely_capability_populated():
    draft = build(_positive_result(capability="payments"), product_id="product:test")
    assert draft.likely_capability == "payments"


# ---------------------------------------------------------------------------
# Sentinel check — rationale never contains fallback strings
# ---------------------------------------------------------------------------


def test_draft_rationale_never_fallback():
    """Sentinel: rationale must not be a placeholder string."""
    recognition = _positive_result()
    draft = build(recognition, product_id="product:test")

    assert draft.rationale not in DRAFT_FALLBACK_STRINGS, (
        f"Decision draft rationale fell back to placeholder: {draft.rationale!r}"
    )


def test_draft_rationale_fallback_inferred_gracefully():
    """When classifier returns no rationale, draft_builder infers from reasoning."""
    recognition = RecognitionResult(
        is_decision=True,
        confidence=0.7,
        decision_type="direction",
        extracted_title="Skip the cache layer",
        extracted_rationale=None,
        extracted_alternatives=[],
        likely_affected_capability=None,
        classifier_reasoning="User decided to defer the cache layer to v2.",
    )
    draft = build(recognition, product_id="product:test")

    assert draft.rationale not in DRAFT_FALLBACK_STRINGS
    assert len(draft.rationale) > 0


def test_draft_stored_and_retrievable():
    """build() stores the draft; get_draft() returns it by ID."""
    recognition = _positive_result()
    draft = build(recognition, product_id="product:test")

    retrieved = get_draft(draft.draft_id)
    assert retrieved is not None
    assert retrieved.draft_id == draft.draft_id


def test_unknown_draft_returns_none():
    assert get_draft("does-not-exist-xyz") is None


def test_draft_builder_handles_missing_title():
    """When classifier returns no title, draft_builder infers it."""
    recognition = RecognitionResult(
        is_decision=True,
        confidence=0.65,
        decision_type="convention",
        extracted_title=None,
        extracted_rationale="Consistency with Python conventions.",
        extracted_alternatives=[],
        likely_affected_capability=None,
        classifier_reasoning="Convention decision detected.",
    )
    draft = build(recognition, product_id="product:test")

    assert draft.title and len(draft.title) > 0
    assert draft.title not in DRAFT_FALLBACK_STRINGS
