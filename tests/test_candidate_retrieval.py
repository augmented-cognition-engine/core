"""TP3 provider-neutral candidate contracts, scoring, and frozen evaluation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.engine.candidates import (
    ALL_CANDIDATE_SIGNALS,
    CandidateFiltersV1,
    CandidateIndexSnapshotV1,
    CandidateRecordV1,
    CandidateRequestV1,
    CandidateSignal,
    DeterministicCandidateFinder,
    default_candidate_index_versions,
)
from core.engine.grounded_state.candidate_evaluation import (
    TP3CandidateEvaluationConfigV1,
    TP3CandidateEvaluationResultV1,
    evaluate_tp3_candidate_retrieval,
)

ROOT = Path(__file__).parents[1]
CORPUS = ROOT / "tests/fixtures/grounded_state/temporal_reference_candidate_v1.json"
CONFIG = ROOT / "evaluations/fixtures/state_engine_tp3_candidate_retrieval_v1.json"
RECORDED = ROOT / "evaluations/results/state_engine_tp3_candidate_retrieval_v1.json"


def _record(
    record_id: str,
    content: str,
    *,
    product_id: str = "product:tp3-a",
    entity_ids: tuple[str, ...] = ("grounded_entity:orchid",),
    temporal: dict | None = None,
    source_id: str = "source:a",
    embedding: tuple[float, ...] = (),
) -> CandidateRecordV1:
    return CandidateRecordV1(
        record_id=record_id,
        product_id=product_id,
        record_kind="claim",
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        content=content,
        entity_ids=entity_ids,
        temporal=temporal or {"precision": "unknown"},
        source_id=source_id,
        publisher_id=source_id,
        graph_neighbor_ids=(*entity_ids, source_id),
        embedding=embedding,
    )


@pytest.mark.asyncio
async def test_candidate_receipt_is_deterministic_order_independent_and_product_scoped():
    query = _record(
        "grounded_claim:query",
        "Orchid Rail opened the northern station",
        temporal={"occurred_at": "2026-01-02T00:00:00Z", "precision": "day"},
    )
    related = _record(
        "grounded_claim:related",
        "Orchid Rail opened a station",
        temporal={"occurred_at": "2026-01-03T00:00:00Z", "precision": "day"},
        source_id="source:b",
    )
    foreign = _record(
        "grounded_claim:foreign",
        "Orchid Rail opened the northern station",
        product_id="product:tp3-b",
    )
    unrelated = _record(
        "grounded_claim:unrelated",
        "Jade Mining opened the northern station",
        entity_ids=("grounded_entity:jade",),
        source_id="source:c",
    )
    forward = CandidateIndexSnapshotV1(
        records=(query, related, foreign, unrelated),
        index_versions=default_candidate_index_versions(),
    )
    reverse = CandidateIndexSnapshotV1(
        records=tuple(reversed((query, related, foreign, unrelated))),
        index_versions=default_candidate_index_versions(),
    )
    assert forward == reverse

    request = CandidateRequestV1.from_record(query, k=10)
    first = await DeterministicCandidateFinder(forward).find_candidates(request)
    replay = await DeterministicCandidateFinder(reverse).find_candidates(request)
    assert first == replay
    assert first.primary_model_calls == 0
    assert first.product_filtered == 1
    assert first.filters == request.filters
    assert first.requested_k == request.k
    assert first.max_candidates == request.max_candidates
    assert first.index_versions == forward.index_versions
    assert [item.record_id for item in first.candidates] == [related.record_id]
    assert first.candidates[0].rank == 1


@pytest.mark.asyncio
async def test_candidate_receipt_reconciles_score_and_return_caps():
    query = _record("grounded_claim:q", "Orchid schedule", source_id="source:q")
    candidates = tuple(
        _record(
            f"grounded_claim:c-{index}",
            f"Orchid schedule update {index}",
            source_id=f"source:{index}",
        )
        for index in range(3)
    )
    snapshot = CandidateIndexSnapshotV1(
        records=(query, *candidates),
        index_versions=default_candidate_index_versions(),
    )
    request = CandidateRequestV1.from_record(query, k=1, max_candidates=2)
    receipt = await DeterministicCandidateFinder(snapshot).find_candidates(request)
    assert receipt.candidates_scored == 3
    assert receipt.score_cap_omitted == 1
    assert receipt.return_cap_omitted == 1
    assert receipt.candidates_returned == 1
    assert receipt.truncated is True
    assert receipt.records_in_snapshot == (
        receipt.product_filtered + receipt.explicit_filtered + receipt.zero_score_filtered + receipt.candidates_scored
    )


@pytest.mark.asyncio
async def test_unknown_time_is_visible_and_never_counted_as_temporal_match():
    query = _record("grounded_claim:q", "Orchid schedule", source_id="source:q")
    candidate = _record("grounded_claim:c", "Orchid schedule update", source_id="source:c")
    snapshot = CandidateIndexSnapshotV1(
        records=(query, candidate),
        index_versions=default_candidate_index_versions(),
    )
    receipt = await DeterministicCandidateFinder(snapshot).find_candidates(CandidateRequestV1.from_record(query, k=5))
    temporal = next(part for part in receipt.candidates[0].contributions if part.signal is CandidateSignal.TEMPORAL)
    assert temporal.applied is False
    assert temporal.score == 0
    assert temporal.reason == "unknown_time_not_scored"
    assert "unknown_time_not_scored" in receipt.candidates[0].degraded_reasons


@pytest.mark.asyncio
async def test_index_absence_and_explicit_filters_degrade_visibly_without_unbounded_fallback():
    query = _record("grounded_claim:q", "Orchid schedule", source_id="source:q")
    allowed = _record("grounded_claim:allowed", "Orchid schedule update", source_id="source:allowed")
    excluded = _record("grounded_claim:excluded", "Orchid schedule replay", source_id="source:excluded")
    snapshot = CandidateIndexSnapshotV1(
        records=(query, allowed, excluded),
        available_signals=tuple(signal for signal in ALL_CANDIDATE_SIGNALS if signal is not CandidateSignal.VECTOR),
        index_versions=default_candidate_index_versions(),
    )
    request = CandidateRequestV1.from_record(
        query,
        k=5,
        filters=CandidateFiltersV1(
            allowed_source_ids=("source:allowed",),
            excluded_record_ids=(excluded.record_id,),
        ),
    )
    receipt = await DeterministicCandidateFinder(snapshot).find_candidates(request)
    assert receipt.unavailable_signals == (CandidateSignal.VECTOR,)
    assert receipt.fallback_reasons == ("vector_index_unavailable",)
    assert receipt.explicit_filtered == 2
    assert [item.record_id for item in receipt.candidates] == [allowed.record_id]
    assert receipt.candidates_scored <= request.max_candidates


@pytest.mark.asyncio
async def test_empty_naked_index_returns_an_inspectable_zero_candidate_receipt():
    snapshot = CandidateIndexSnapshotV1(
        records=(),
        index_versions=default_candidate_index_versions(),
    )
    request = CandidateRequestV1(product_id="product:tp3-a", content="bounded query", k=5)
    receipt = await DeterministicCandidateFinder(snapshot).find_candidates(request)
    assert receipt.records_in_snapshot == 0
    assert receipt.candidates_scored == 0
    assert receipt.candidates_returned == 0
    assert receipt.candidates == ()
    assert receipt.primary_model_calls == 0


def test_candidate_contracts_reject_scope_hash_and_unbounded_inputs():
    with pytest.raises(ValidationError, match="product_id"):
        _record("grounded_claim:x", "x", product_id="foreign")
    with pytest.raises(ValidationError, match="content_hash"):
        CandidateRecordV1(
            record_id="grounded_claim:x",
            product_id="product:tp3-a",
            record_kind="claim",
            content_hash="0" * 64,
            content="different",
        )
    with pytest.raises(ValidationError):
        CandidateRequestV1(product_id="product:tp3-a", content="x", k=51)


@pytest.mark.asyncio
async def test_frozen_tp3_candidate_evaluation_meets_predeclared_targets_and_reports_ablations():
    corpus = json.loads(CORPUS.read_text())
    config_payload = json.loads(CONFIG.read_text())
    config = TP3CandidateEvaluationConfigV1.model_validate(config_payload)
    assert config.candidate_k == 20
    assert config.minimum_gold_neighbor_recall == 0.95
    assert config.maximum_false_association_rate == 0.1
    assert config.provider_budget.model_calls == 0

    result = await evaluate_tp3_candidate_retrieval(corpus, config_payload)
    replay = await evaluate_tp3_candidate_retrieval(corpus, config_payload)
    recorded = TP3CandidateEvaluationResultV1.model_validate_json(RECORDED.read_text())
    assert result == replay
    assert result == recorded
    assert result.passed is True
    assert result.records_indexed == 62
    assert result.gold_neighbors_found == result.gold_neighbor_queries == 38
    assert result.candidate_recall == 1.0
    assert result.false_associations == 0
    assert result.false_association_rate == 0.0
    assert result.deterministic_replay is True
    assert {item.name for item in result.ablations} == {
        "without_vector",
        "without_entity",
        "without_temporal",
    }
    assert all(item.gold_neighbor_queries == 38 for item in result.ablations)
    assert all(item.removed_signal_mean_contribution > 0 for item in result.ablations)
    assert result.unavailable_index_receipt.unavailable_signals == (CandidateSignal.VECTOR,)
    assert result.primary_model_calls == 0
    assert result.outcome_hash


@pytest.mark.asyncio
async def test_frozen_evaluation_refuses_target_or_corpus_identity_drift():
    corpus = json.loads(CORPUS.read_text())
    config = json.loads(CONFIG.read_text())
    config["corpus_hash"] = "0" * 64
    with pytest.raises(ValueError, match="different frozen corpus"):
        await evaluate_tp3_candidate_retrieval(corpus, config)
