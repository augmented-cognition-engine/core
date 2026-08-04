"""TP1A provider-free contract, durability, isolation, retry, and health proofs."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from core.engine.capture.lifecycle import (
    MAX_PROCESSING_ATTEMPTS,
    OutcomeProductScopeError,
    OutcomeReplayConflict,
    load_outcome_receipt,
    observation_outcome_health,
    persist_outcome_receipt,
    process_observation_attempt,
)
from core.engine.capture.outcomes import (
    SYNTHESIS_POLICY_VERSION,
    SYNTHESIS_PROCESSOR_VERSION,
    SYNTHESIS_SCHEMA_VERSION,
    FailureCategory,
    ObservationSynthesisOutcomeV1,
    ProcessingState,
    SuccessfulDisposition,
    SynthesisFailureV1,
    SynthesisOutcomeReceiptV1,
    SynthesisProvenanceV1,
    build_attempt_id,
    build_receipt_id,
)
from core.engine.core.db import parse_one


def _suffix() -> str:
    return uuid.uuid4().hex[:16]


def _receipt(
    *,
    product_id: str,
    observation_id: str,
    outcome: ObservationSynthesisOutcomeV1,
    material_hash: str = "a" * 64,
) -> SynthesisOutcomeReceiptV1:
    now = datetime.now(timezone.utc)
    attempt_id = build_attempt_id(
        product_id=product_id,
        observation_id=observation_id,
        attempt_count=1,
        route="test",
    )
    return SynthesisOutcomeReceiptV1(
        receipt_id=build_receipt_id(product_id=product_id, attempt_id=attempt_id),
        product_id=product_id,
        observation_id=observation_id,
        attempt_id=attempt_id,
        attempt_count=1,
        processing_state=ProcessingState.SUCCEEDED,
        outcome=outcome,
        retryable=False,
        processor_version=SYNTHESIS_PROCESSOR_VERSION,
        policy_version=SYNTHESIS_POLICY_VERSION,
        schema_version=SYNTHESIS_SCHEMA_VERSION,
        material_hash=material_hash,
        started_at=now,
        completed_at=now,
        provenance=SynthesisProvenanceV1(route="test"),
        explainable_terminal=True,
    )


@pytest.mark.parametrize(
    ("disposition", "field"),
    [
        (SuccessfulDisposition.INSIGHT_CREATED, "created_insight_refs"),
        (SuccessfulDisposition.INSIGHT_UPDATED, "updated_insight_refs"),
        (SuccessfulDisposition.INSIGHT_MERGED, "merged_insight_refs"),
        (SuccessfulDisposition.CONFLICT_PRESERVED, "conflicting_insight_refs"),
    ],
)
def test_insight_dispositions_require_corresponding_references(disposition, field):
    with pytest.raises(ValidationError):
        ObservationSynthesisOutcomeV1(
            observation_id="observation:test",
            disposition=disposition,
            conflict_record_refs=("conflict:test",) if disposition is SuccessfulDisposition.CONFLICT_PRESERVED else (),
        )

    payload = {field: ("insight:test",)}
    if disposition is SuccessfulDisposition.CONFLICT_PRESERVED:
        payload["conflict_record_refs"] = ("conflict:test",)
    validated = ObservationSynthesisOutcomeV1(
        observation_id="observation:test",
        disposition=disposition,
        **payload,
    )
    assert getattr(validated, field) == ("insight:test",)


def test_skipped_requires_a_reason():
    with pytest.raises(ValidationError):
        ObservationSynthesisOutcomeV1(
            observation_id="observation:test",
            disposition=SuccessfulDisposition.SKIPPED,
        )
    outcome = ObservationSynthesisOutcomeV1(
        observation_id="observation:test",
        disposition=SuccessfulDisposition.SKIPPED,
        reason="below durable intelligence threshold",
    )
    assert outcome.reason == "below durable intelligence threshold"


async def _seed_observation(db_pool, *, product_id: str, observation_id: str, **extra) -> dict:
    fields = {
        "product": product_id,
        "content": extra.pop("content", "TP1A lifecycle observation"),
        "observation_type": extra.pop("observation_type", "pattern"),
        "confidence": extra.pop("confidence", 0.8),
        "status": extra.pop("status", "pending"),
        "created_at": extra.pop("created_at", datetime.now(timezone.utc)),
        **extra,
    }
    async with db_pool.connection() as db:
        row = parse_one(
            await db.query(
                """
                CREATE ONLY <record>$id SET
                    product = <record>$product,
                    content = $content,
                    observation_type = $observation_type,
                    confidence = $confidence,
                    domain_path = 'testing',
                    discipline_hint = 'testing',
                    source = 'test',
                    status = $status,
                    processing_attempt_count = $processing_attempt_count,
                    created_at = $created_at
                """,
                {
                    "id": observation_id,
                    "product": product_id,
                    "content": fields["content"],
                    "observation_type": fields["observation_type"],
                    "confidence": fields["confidence"],
                    "status": fields["status"],
                    "processing_attempt_count": fields.get("processing_attempt_count"),
                    "created_at": fields["created_at"],
                },
            )
        )
    assert row
    return row


async def _seed_insight(db_pool, *, product_id: str, insight_id: str) -> None:
    async with db_pool.connection() as db:
        await db.query(
            """
            CREATE ONLY <record>$id SET
                product = <record>$product,
                content = 'TP1A referenced insight',
                insight_type = 'fact', tier = 'domain', clearance = 'open',
                confidence = 0.8, source_domain = 'testing', domain_path = 'testing',
                tags = [], status = 'active', created_at = time::now(),
                updated_at = time::now(), last_confirmed = time::now()
            """,
            {"id": insight_id, "product": product_id},
        )


class _OutcomeSynthesizer:
    outcome_builder = None

    def __init__(self, **_kwargs):
        self._db_pool = None
        self._attempt_id = None

    async def add_observation(self, observation):
        outcome = self.outcome_builder(observation)
        return {
            "new_insights": int(outcome.disposition is SuccessfulDisposition.INSIGHT_CREATED),
            "updates": int(outcome.disposition is SuccessfulDisposition.INSIGHT_UPDATED),
            "conflicts": int(outcome.disposition is SuccessfulDisposition.CONFLICT_PRESERVED),
            "skipped": int(outcome.disposition is SuccessfulDisposition.SKIPPED),
            "outcomes": [outcome.model_dump(mode="json")],
        }

    async def flush(self):
        return {"new_insights": 0, "updates": 0, "conflicts": 0, "skipped": 0, "outcomes": []}


class _FailingSynthesizer:
    def __init__(self, **_kwargs):
        self._db_pool = None
        self._attempt_id = None

    async def add_observation(self, _observation):
        raise RuntimeError("provider temporarily unavailable")

    async def flush(self):
        raise AssertionError("flush is unreachable after add failure")


@pytest.mark.asyncio
@pytest.mark.parametrize("disposition", list(SuccessfulDisposition))
async def test_each_successful_disposition_has_a_durable_receipt(db_pool, disposition):
    token = _suffix()
    product_id = "product:test"
    observation_id = f"observation:tp1a_{token}"
    insight_id = f"insight:tp1a_{token}"
    conflict_id = f"conflict:tp1a_{token}"
    observation = await _seed_observation(db_pool, product_id=product_id, observation_id=observation_id)
    if disposition is not SuccessfulDisposition.SKIPPED:
        await _seed_insight(db_pool, product_id=product_id, insight_id=insight_id)
    if disposition is SuccessfulDisposition.CONFLICT_PRESERVED:
        async with db_pool.connection() as db:
            await db.query(
                """
                CREATE ONLY <record>$id SET product = <record>$product,
                    insight_a = <record>$insight, explanation = 'preserved contradiction',
                    status = 'pending', created_at = time::now()
                """,
                {"id": conflict_id, "product": product_id, "insight": insight_id},
            )

    def build(obs):
        kwargs = {}
        if disposition is SuccessfulDisposition.INSIGHT_CREATED:
            kwargs["created_insight_refs"] = (insight_id,)
        elif disposition is SuccessfulDisposition.INSIGHT_UPDATED:
            kwargs["updated_insight_refs"] = (insight_id,)
        elif disposition is SuccessfulDisposition.INSIGHT_MERGED:
            kwargs["merged_insight_refs"] = (insight_id,)
        elif disposition is SuccessfulDisposition.CONFLICT_PRESERVED:
            kwargs["conflicting_insight_refs"] = (insight_id,)
            kwargs["conflict_record_refs"] = (conflict_id,)
        else:
            kwargs["reason"] = "intentionally below the durable-intelligence threshold"
        return ObservationSynthesisOutcomeV1(
            observation_id=str(obs["id"]),
            disposition=disposition,
            **kwargs,
        )

    _OutcomeSynthesizer.outcome_builder = staticmethod(build)
    receipt = await process_observation_attempt(
        observation,
        db_pool=db_pool,
        route="test",
        synthesizer_factory=_OutcomeSynthesizer,
    )
    assert receipt.processing_state is ProcessingState.SUCCEEDED
    assert receipt.outcome and receipt.outcome.disposition is disposition
    loaded = await load_outcome_receipt(db_pool, receipt_id=receipt.receipt_id, product_id=product_id)
    assert loaded == receipt
    async with db_pool.connection() as db:
        stored_observation = parse_one(
            await db.query(
                "SELECT status, processing_state, outcome_receipt FROM ONLY <record>$id WHERE product = <record>$product",
                {"id": observation_id, "product": product_id},
            )
        )
    assert stored_observation["status"] == "processed"
    assert stored_observation["processing_state"] == "succeeded"
    assert str(stored_observation["outcome_receipt"]) == receipt.receipt_id


@pytest.mark.asyncio
async def test_exception_is_retryable_and_never_marks_processed(db_pool):
    observation_id = f"observation:tp1a_{_suffix()}"
    observation = await _seed_observation(db_pool, product_id="product:test", observation_id=observation_id)
    receipt = await process_observation_attempt(
        observation,
        db_pool=db_pool,
        route="test",
        synthesizer_factory=_FailingSynthesizer,
    )
    assert receipt.processing_state is ProcessingState.RETRYABLE_FAILED
    assert receipt.retryable is True
    assert receipt.next_retry_at is not None
    async with db_pool.connection() as db:
        stored = parse_one(
            await db.query(
                "SELECT status, processing_state FROM ONLY <record>$id WHERE product = product:test",
                {"id": observation_id},
            )
        )
    assert stored == {"status": "pending", "processing_state": "retryable_failed"}


@pytest.mark.asyncio
async def test_retry_exhaustion_creates_durable_dead_letter(db_pool):
    observation_id = f"observation:tp1a_{_suffix()}"
    observation = await _seed_observation(
        db_pool,
        product_id="product:test",
        observation_id=observation_id,
        processing_attempt_count=MAX_PROCESSING_ATTEMPTS - 1,
    )
    receipt = await process_observation_attempt(
        observation,
        db_pool=db_pool,
        route="test",
        synthesizer_factory=_FailingSynthesizer,
    )
    assert receipt.processing_state is ProcessingState.DEAD_LETTER
    assert receipt.retryable is False
    assert receipt.next_retry_at is None
    loaded = await load_outcome_receipt(db_pool, receipt_id=receipt.receipt_id, product_id="product:test")
    assert loaded and loaded.processing_state is ProcessingState.DEAD_LETTER


@pytest.mark.asyncio
async def test_exact_replay_is_idempotent_and_conflicting_replay_fails_closed(db_pool):
    token = _suffix()
    observation_id = f"observation:tp1a_{token}"
    insight_id = f"insight:tp1a_{token}"
    await _seed_observation(db_pool, product_id="product:test", observation_id=observation_id)
    await _seed_insight(db_pool, product_id="product:test", insight_id=insight_id)
    outcome = ObservationSynthesisOutcomeV1(
        observation_id=observation_id,
        disposition=SuccessfulDisposition.INSIGHT_CREATED,
        created_insight_refs=(insight_id,),
    )
    receipt = _receipt(product_id="product:test", observation_id=observation_id, outcome=outcome)
    first = await persist_outcome_receipt(db_pool, receipt)
    replay = await persist_outcome_receipt(db_pool, receipt)
    assert replay == first
    conflicting = _receipt(
        product_id="product:test",
        observation_id=observation_id,
        outcome=ObservationSynthesisOutcomeV1(
            observation_id=observation_id,
            disposition=SuccessfulDisposition.SKIPPED,
            reason="changed history",
        ),
    )
    with pytest.raises(OutcomeReplayConflict):
        await persist_outcome_receipt(db_pool, conflicting)


@pytest.mark.asyncio
async def test_exact_processing_replay_creates_one_receipt_and_one_insight(db_pool):
    token = _suffix()
    observation_id = f"observation:tp1a_{token}"
    content = f"TP1A deterministic synthesis {token}"
    observation = await _seed_observation(
        db_pool,
        product_id="product:test",
        observation_id=observation_id,
        content=content,
    )
    synthesis = {
        "new_insights": [
            {
                "content": f"Durable insight for {token}",
                "tier": "domain",
                "discipline": "testing",
                "insight_type": "fact",
                "confidence": 0.8,
                "source_observations": [0],
            }
        ],
        "updates": [],
        "conflicts": [],
        "skipped": [],
    }

    class _NoopEmbedder:
        dimensions = 0

    with (
        patch(
            "core.engine.capture.synthesizer.Synthesizer._call_primary_llm",
            new=AsyncMock(return_value=synthesis),
        ) as call_llm,
        patch("core.engine.capture.synthesizer.get_embedder", return_value=_NoopEmbedder()),
    ):
        first = await process_observation_attempt(observation, db_pool=db_pool, route="test")
        replay = await process_observation_attempt(observation, db_pool=db_pool, route="test")

    assert first == replay
    assert call_llm.await_count == 1
    assert first.outcome and len(first.outcome.created_insight_refs) == 1
    async with db_pool.connection() as db:
        receipts = parse_one(
            await db.query(
                "SELECT count() AS n FROM synthesis_outcome_receipt WHERE product = product:test AND observation = <record>$observation GROUP ALL",
                {"observation": observation_id},
            )
        )
        insights = parse_one(
            await db.query(
                "SELECT count() AS n FROM insight WHERE product = product:test AND content = $content GROUP ALL",
                {"content": f"Durable insight for {token}"},
            )
        )
    assert receipts["n"] == 1
    assert insights["n"] == 1

    changed = dict(observation)
    changed["content"] = f"changed {content}"
    with pytest.raises(OutcomeReplayConflict):
        await process_observation_attempt(changed, db_pool=db_pool, route="test")


@pytest.mark.asyncio
async def test_receipt_references_and_reads_are_product_isolated(db_pool):
    token = _suffix()
    product_a = "product:test"
    product_b = f"product:tp1a_{token}"
    observation_id = f"observation:tp1a_{token}"
    insight_id = f"insight:tp1a_{token}"
    async with db_pool.connection() as db:
        await db.query(
            "UPSERT <record>$id SET name = 'TP1A B', tenant = tenant:test, settings = {}",
            {"id": product_b},
        )
    await _seed_observation(db_pool, product_id=product_a, observation_id=observation_id)
    await _seed_insight(db_pool, product_id=product_a, insight_id=insight_id)
    forged = _receipt(
        product_id=product_b,
        observation_id=observation_id,
        outcome=ObservationSynthesisOutcomeV1(
            observation_id=observation_id,
            disposition=SuccessfulDisposition.INSIGHT_CREATED,
            created_insight_refs=(insight_id,),
        ),
    )
    with pytest.raises(OutcomeProductScopeError):
        await persist_outcome_receipt(db_pool, forged)

    valid = _receipt(
        product_id=product_a,
        observation_id=observation_id,
        outcome=ObservationSynthesisOutcomeV1(
            observation_id=observation_id,
            disposition=SuccessfulDisposition.INSIGHT_CREATED,
            created_insight_refs=(insight_id,),
        ),
    )
    await persist_outcome_receipt(db_pool, valid)
    assert await load_outcome_receipt(db_pool, receipt_id=valid.receipt_id, product_id=product_b) is None

    forged_observation = {
        "id": observation_id,
        "product": product_b,
        "content": "cross-product retry",
        "observation_type": "fact",
        "confidence": 0.8,
    }
    with pytest.raises(OutcomeProductScopeError):
        await process_observation_attempt(
            forged_observation,
            db_pool=db_pool,
            route="test",
            synthesizer_factory=_FailingSynthesizer,
        )


@pytest.mark.asyncio
async def test_health_reports_legacy_gap_and_cannot_remain_green(db_pool):
    token = _suffix()
    product_id = f"product:tp1a_health_{token}"
    async with db_pool.connection() as db:
        await db.query(
            "UPSERT <record>$id SET name = 'TP1A health', tenant = tenant:test, settings = {}",
            {"id": product_id},
        )
    await _seed_observation(
        db_pool,
        product_id=product_id,
        observation_id=f"observation:tp1a_legacy_{token}",
        status="processed",
    )
    await _seed_observation(
        db_pool,
        product_id=product_id,
        observation_id=f"observation:tp1a_pending_{token}",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=20),
    )
    health = await observation_outcome_health(db_pool, product_id=product_id)
    assert health["legacy_unexplained_count"] == 1
    assert health["pending_count"] == 1
    assert health["oldest_pending_age_seconds"] >= 1_100
    assert health["status"] == "degraded"
    assert {"legacy_unexplained", "oldest_pending_age"} <= set(health["policy_breaches"])


def test_failure_receipt_shape_separates_processing_from_disposition():
    now = datetime.now(timezone.utc)
    attempt_id = build_attempt_id(
        product_id="product:test",
        observation_id="observation:test",
        attempt_count=1,
        route="test",
    )
    receipt = SynthesisOutcomeReceiptV1(
        receipt_id=build_receipt_id(product_id="product:test", attempt_id=attempt_id),
        product_id="product:test",
        observation_id="observation:test",
        attempt_id=attempt_id,
        attempt_count=1,
        processing_state=ProcessingState.RETRYABLE_FAILED,
        failure=SynthesisFailureV1(
            category=FailureCategory.PROVIDER,
            code="provider_error",
            error_type="TimeoutError",
            message="provider unavailable",
        ),
        retryable=True,
        next_retry_at=now + timedelta(seconds=5),
        processor_version=SYNTHESIS_PROCESSOR_VERSION,
        policy_version=SYNTHESIS_POLICY_VERSION,
        schema_version=SYNTHESIS_SCHEMA_VERSION,
        material_hash="b" * 64,
        started_at=now,
        completed_at=now,
        provenance=SynthesisProvenanceV1(route="test"),
        explainable_terminal=True,
    )
    assert receipt.outcome is None
    assert receipt.processing_state is ProcessingState.RETRYABLE_FAILED
