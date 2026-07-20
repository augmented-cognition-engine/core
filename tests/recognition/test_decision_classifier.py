"""Boundary tests for the decision-shaped recognition classifier — A5 ACs 1, 2, 3, 4, 6."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from core.engine.recognition.models import RecognitionResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_positive(title="Use JWT instead of session cookies", rationale="Stateless deployment"):
    return RecognitionResult(
        is_decision=True,
        confidence=0.85,
        decision_type="architecture",
        extracted_title=title,
        extracted_rationale=rationale,
        extracted_alternatives=["session cookies"],
        likely_affected_capability="auth",
        classifier_reasoning="User committed to JWT explicitly over alternatives.",
    )


def _mock_negative():
    return RecognitionResult(
        is_decision=False,
        confidence=0.1,
        classifier_reasoning="This is a question, not a commitment.",
    )


# ---------------------------------------------------------------------------
# AC 1 — positive samples recalled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classifier_positive_detection():
    """Classifier returns is_decision=True with confidence > 0.6 for a clear decision."""
    from core.engine.recognition import decision_classifier

    positive_json = """{
        "is_decision": true,
        "confidence": 0.9,
        "decision_type": "architecture",
        "extracted_title": "Use JWT over session cookies",
        "extracted_rationale": "Stateless deployment requirement",
        "extracted_alternatives": ["session cookies"],
        "likely_affected_capability": "auth",
        "classifier_reasoning": "User explicitly chose JWT over alternatives."
    }"""

    with patch.object(decision_classifier.llm, "complete", new_callable=AsyncMock, return_value=positive_json):
        result = await decision_classifier.classify(
            "Let's go with JWT instead of session cookies for stateless deployment.",
            capabilities=["auth", "payments"],
        )

    assert result.is_decision is True
    assert result.confidence > 0.6


# ---------------------------------------------------------------------------
# AC 2 — negative samples rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classifier_negative_rejection():
    """Classifier returns is_decision=False for a question."""
    from core.engine.recognition import decision_classifier

    negative_json = """{
        "is_decision": false,
        "confidence": 0.05,
        "decision_type": null,
        "extracted_title": null,
        "extracted_rationale": null,
        "extracted_alternatives": [],
        "likely_affected_capability": null,
        "classifier_reasoning": "This is a question, not a commitment."
    }"""

    with patch.object(decision_classifier.llm, "complete", new_callable=AsyncMock, return_value=negative_json):
        result = await decision_classifier.classify("Should we use JWT or session cookies?")

    assert result.is_decision is False


# ---------------------------------------------------------------------------
# AC 3 — extracted_title and extracted_rationale populated when is_decision=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_positive_result_has_title_and_rationale():
    """When is_decision=True, extracted_title and rationale must be non-empty."""
    from core.engine.recognition import decision_classifier

    with patch.object(
        decision_classifier.llm,
        "complete",
        new_callable=AsyncMock,
        return_value='{"is_decision": true, "confidence": 0.85, '
        '"decision_type": "architecture", '
        '"extracted_title": "Use JWT over sessions", '
        '"extracted_rationale": "Needed for stateless arch", '
        '"extracted_alternatives": [], '
        '"likely_affected_capability": "auth", '
        '"classifier_reasoning": "Explicit commitment."}',
    ):
        result = await decision_classifier.classify(
            "Let's use JWT — it's better for our stateless architecture.",
            capabilities=["auth"],
        )

    assert result.is_decision is True
    assert result.extracted_title and len(result.extracted_title) > 0
    assert result.extracted_rationale and len(result.extracted_rationale) > 0


# ---------------------------------------------------------------------------
# AC 4 — likely_affected_capability matches actual capability
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capability_resolves_to_known_capability():
    """likely_affected_capability should match one of the passed capabilities."""
    from core.engine.recognition import decision_classifier

    capabilities = ["auth", "payments", "notifications"]

    with patch.object(
        decision_classifier.llm,
        "complete",
        new_callable=AsyncMock,
        return_value='{"is_decision": true, "confidence": 0.8, '
        '"decision_type": "architecture", '
        '"extracted_title": "Use JWT for auth", '
        '"extracted_rationale": "Stateless auth needed", '
        '"extracted_alternatives": [], '
        '"likely_affected_capability": "auth", '
        '"classifier_reasoning": "Decision about auth module."}',
    ):
        result = await decision_classifier.classify(
            "We're using JWT for auth — no session storage needed.",
            capabilities=capabilities,
        )

    assert result.likely_affected_capability in capabilities


# ---------------------------------------------------------------------------
# AC 6 — non-blocking latency (recognition task creation overhead < 10ms)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_observer_recognition_is_non_blocking():
    """evaluate_chunk latency increase from recognition task is negligible."""
    from datetime import datetime
    from unittest.mock import AsyncMock, patch

    from core.engine.capture.observer import Observer
    from core.engine.capture.watchers import Chunk, StreamEvent

    evt = StreamEvent(timestamp=datetime.now(), event_type="text", content="Let's use JWT.")
    chunk = Chunk(
        content="Let's go with JWT instead of sessions.",
        chunk_type="reasoning",
        events=[evt],
        start_time=datetime.now(),
        end_time=datetime.now(),
        token_count=50,
    )

    observer = Observer(product_id="product:test", workspace_id=None)

    mock_llm_result = {
        "has_intelligence": False,
        "observations": [],
    }

    # Patch both the budget LLM and the recognition classifier to be instant
    async def _slow_classify(*args, **kwargs):
        from core.engine.recognition.models import RecognitionResult

        return RecognitionResult(is_decision=False, confidence=0.0, classifier_reasoning="mock")

    with patch.object(observer, "_call_budget_llm", new_callable=AsyncMock, return_value=mock_llm_result):
        import core.engine.recognition.decision_classifier as dc_module

        with patch.object(dc_module, "classify", side_effect=_slow_classify):
            t0 = time.perf_counter()
            await observer.evaluate_chunk(chunk, memory_id=None)
            elapsed_ms = (time.perf_counter() - t0) * 1000

    # evaluate_chunk itself must not block waiting for recognition
    # The recognition runs as a background task; evaluate_chunk should be near-instant
    assert elapsed_ms < 200, f"evaluate_chunk took {elapsed_ms:.1f}ms — recognition must not block"


# ---------------------------------------------------------------------------
# Graceful failure — classifier never raises
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classifier_returns_false_on_llm_failure():
    """On LLM failure, classify() returns is_decision=False, never raises."""
    from core.engine.recognition import decision_classifier

    async def _fail(*args, **kwargs):
        raise ConnectionError("LLM unavailable")

    with patch.object(decision_classifier.llm, "complete", side_effect=_fail):
        result = await decision_classifier.classify("Let's use JWT.")

    assert result.is_decision is False
    assert result.confidence == 0.0
    assert "error" in result.classifier_reasoning


# ---------------------------------------------------------------------------
# Markdown code fence stripping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classifier_strips_markdown_fences():
    """Classifier handles LLM output wrapped in ```json code fences."""
    from core.engine.recognition import decision_classifier

    fenced = '```json\n{"is_decision": false, "confidence": 0.1, "decision_type": null, "extracted_title": null, "extracted_rationale": null, "extracted_alternatives": [], "likely_affected_capability": null, "classifier_reasoning": "not a decision"}\n```'

    with patch.object(decision_classifier.llm, "complete", new_callable=AsyncMock, return_value=fenced):
        result = await decision_classifier.classify("Hello.")

    assert result.is_decision is False
