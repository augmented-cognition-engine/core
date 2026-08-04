"""Provider-free TP3 evaluation against the frozen TP0 corpus."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from core.engine.candidates import (
    ALL_CANDIDATE_SIGNALS,
    CandidateIndexSnapshotV1,
    CandidateReceiptV1,
    CandidateRecordV1,
    CandidateRequestV1,
    CandidateSignal,
    DeterministicCandidateFinder,
    default_candidate_index_versions,
)
from core.engine.grounded_state.contracts import FrozenContract, canonical_hash, stable_id
from core.engine.grounded_state.corpus import (
    RelationshipClassification,
    TemporalReferenceCaseV1,
    TemporalReferenceCorpusV1,
)

TP3_CANDIDATE_EVALUATION_CONFIG_VERSION = "ace.grounded-state.tp3-candidate-evaluation-config/v1"
TP3_CANDIDATE_EVALUATION_RESULT_VERSION = "ace.grounded-state.tp3-candidate-evaluation-result/v1"

ROOT = Path(__file__).parents[3]
DEFAULT_CORPUS = ROOT / "tests/fixtures/grounded_state/temporal_reference_candidate_v1.json"
DEFAULT_CONFIG = ROOT / "evaluations/fixtures/state_engine_tp3_candidate_retrieval_v1.json"

_NEGATIVE_RELATIONSHIPS = {
    RelationshipClassification.UNRELATED,
    RelationshipClassification.CROSS_PRODUCT_ISOLATED,
}


class TP3ProviderBudgetV1(FrozenContract):
    model_calls: Literal[0] = 0
    input_tokens: Literal[0] = 0
    output_tokens: Literal[0] = 0
    estimated_cost_usd: Literal[0.0] = 0.0


class TP3CandidateEvaluationConfigV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.tp3-candidate-evaluation-config/v1"] = (
        TP3_CANDIDATE_EVALUATION_CONFIG_VERSION
    )
    corpus_contract_version: str
    corpus_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    evaluation_seed: int
    candidate_k: int = Field(ge=1, le=50)
    minimum_gold_neighbor_recall: float = Field(ge=0, le=1)
    negative_control_k: int = Field(ge=1, le=50)
    maximum_false_association_rate: float = Field(ge=0, le=1)
    maximum_records: int = Field(ge=1, le=200)
    maximum_candidates_scored_per_query: int = Field(ge=1, le=200)
    signals: dict[str, str]
    required_ablations: tuple[Literal["without_vector", "without_entity", "without_temporal"], ...]
    provider_budget: TP3ProviderBudgetV1
    notes: tuple[str, ...]

    @field_validator("signals")
    @classmethod
    def validate_signals(cls, value: dict[str, str]) -> dict[str, str]:
        expected = {signal.value for signal in ALL_CANDIDATE_SIGNALS}
        if set(value) != expected:
            raise ValueError("TP3 evaluation config must version every candidate signal")
        return dict(sorted(value.items()))

    @field_validator("required_ablations", mode="before")
    @classmethod
    def normalize_ablations(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("required_ablations must be a list")
        return tuple(value)

    @field_validator("notes", mode="before")
    @classmethod
    def normalize_notes(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("notes must be a list")
        notes = tuple(str(item) for item in value)
        if not notes or any(not item.strip() or len(item) > 1_000 for item in notes):
            raise ValueError("notes must contain bounded non-empty statements")
        return notes

    @model_validator(mode="after")
    def validate_limits(self) -> Self:
        if self.candidate_k > self.maximum_candidates_scored_per_query:
            raise ValueError("candidate_k cannot exceed the per-query score bound")
        if self.negative_control_k > self.maximum_candidates_scored_per_query:
            raise ValueError("negative_control_k cannot exceed the per-query score bound")
        required = {"without_vector", "without_entity", "without_temporal"}
        if set(self.required_ablations) != required:
            raise ValueError("TP3 config must freeze vector, entity, and temporal ablations")
        return self

    def config_hash(self) -> str:
        return canonical_hash(self)


class CandidateEvaluationQueryV1(FrozenContract):
    case_key: str
    query_input_key: str
    expected_input_key: str
    query_record_id: str
    expected_record_id: str
    receipt_id: str
    found: bool
    rank: int | None = Field(default=None, ge=1, le=50)
    expected_score: float | None = Field(default=None, ge=0, le=1)
    signal_scores: dict[str, float] = Field(default_factory=dict)


class CandidateAblationResultV1(FrozenContract):
    name: Literal["without_vector", "without_entity", "without_temporal"]
    removed_signal: CandidateSignal
    gold_neighbor_queries: int = Field(ge=0)
    gold_neighbors_found: int = Field(ge=0)
    recall: float = Field(ge=0, le=1)
    recall_delta: float = Field(ge=-1, le=1)
    mean_reciprocal_rank: float = Field(ge=0, le=1)
    mean_reciprocal_rank_delta: float = Field(ge=-1, le=1)
    removed_signal_mean_contribution: float = Field(ge=0, le=1)


class TP3CandidateEvaluationResultV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.tp3-candidate-evaluation-result/v1"] = (
        TP3_CANDIDATE_EVALUATION_RESULT_VERSION
    )
    config_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    corpus_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    snapshot_id: str
    records_indexed: int = Field(ge=0, le=200)
    gold_neighbor_queries: int = Field(ge=0)
    gold_neighbors_found: int = Field(ge=0)
    candidate_recall: float = Field(ge=0, le=1)
    mean_reciprocal_rank: float = Field(ge=0, le=1)
    recall_target: float = Field(ge=0, le=1)
    candidate_k: int = Field(ge=1, le=50)
    negative_control_queries: int = Field(ge=0)
    false_associations: int = Field(ge=0)
    false_association_rate: float = Field(ge=0, le=1)
    false_association_ceiling: float = Field(ge=0, le=1)
    negative_control_k: int = Field(ge=1, le=50)
    query_results: tuple[CandidateEvaluationQueryV1, ...]
    ablations: tuple[CandidateAblationResultV1, ...]
    unavailable_index_receipt: CandidateReceiptV1
    deterministic_replay: bool
    primary_model_calls: Literal[0] = 0
    input_tokens: Literal[0] = 0
    output_tokens: Literal[0] = 0
    estimated_cost_usd: Literal[0.0] = 0.0
    recall_target_met: bool
    false_association_target_met: bool
    passed: bool
    outcome_hash: str | None = None

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        expected_recall = self.gold_neighbors_found / self.gold_neighbor_queries if self.gold_neighbor_queries else 0
        expected_false_rate = (
            self.false_associations / self.negative_control_queries if self.negative_control_queries else 0
        )
        if abs(self.candidate_recall - expected_recall) > 1e-9:
            raise ValueError("candidate recall must reconcile query counts")
        if abs(self.false_association_rate - expected_false_rate) > 1e-9:
            raise ValueError("false-association rate must reconcile query counts")
        if self.recall_target_met != (self.candidate_recall >= self.recall_target):
            raise ValueError("recall target disposition is inconsistent")
        if self.false_association_target_met != (self.false_association_rate <= self.false_association_ceiling):
            raise ValueError("false-association target disposition is inconsistent")
        if self.passed != (self.recall_target_met and self.false_association_target_met and self.deterministic_replay):
            raise ValueError("overall TP3 disposition is inconsistent")
        material = self.model_dump(mode="json", exclude={"outcome_hash"})
        expected_hash = canonical_hash(material)
        if self.outcome_hash is not None and self.outcome_hash != expected_hash:
            raise ValueError("outcome_hash does not match material TP3 result")
        object.__setattr__(self, "outcome_hash", expected_hash)
        return self


def load_tp3_config(path: str | Path = DEFAULT_CONFIG) -> TP3CandidateEvaluationConfigV1:
    return TP3CandidateEvaluationConfigV1.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _occurrence_id(case_key: str, input_key: str, evidence_id: str) -> str:
    return stable_id(
        "tp3_evidence_occurrence",
        {"case_key": case_key, "input_key": input_key, "evidence_id": evidence_id},
    )


def _candidate_record(case: TemporalReferenceCaseV1, input_key: str) -> CandidateRecordV1:
    evidence = next(item.record for item in case.evidence if item.input_key == input_key)
    content = evidence.content or " ".join(part for part in (evidence.external_id, *evidence.raw_mentions) if part)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    graph = tuple(sorted({evidence.source_id, *evidence.entity_refs, *evidence.supersedes}))
    return CandidateRecordV1(
        record_id=_occurrence_id(case.case_key, input_key, evidence.evidence_id()),
        product_id=evidence.product_id,
        record_kind=evidence.kind.value,
        content_hash=digest,
        content=content,
        entity_ids=evidence.entity_refs,
        temporal=evidence.temporal,
        source_id=evidence.source_id,
        publisher_id=evidence.source_id,
        graph_neighbor_ids=graph,
        facets=(case.primary_category.value, evidence.kind.value),
    )


def _pair_disposition(case: TemporalReferenceCaseV1) -> Literal["gold", "negative"] | None:
    if len(case.evidence) != 2:
        return None
    classifications = {relationship.classification for relationship in case.expected.relationships}
    if classifications & _NEGATIVE_RELATIONSHIPS:
        return "negative"
    keys = {item.input_key for item in case.evidence}
    if any(keys <= set(relationship.supporting_evidence_keys) for relationship in case.expected.relationships):
        return "gold"
    return None


def _build_snapshot(
    corpus: TemporalReferenceCorpusV1,
    *,
    available_signals: tuple[CandidateSignal, ...] = ALL_CANDIDATE_SIGNALS,
) -> tuple[CandidateIndexSnapshotV1, dict[tuple[str, str], CandidateRecordV1]]:
    occurrences: dict[tuple[str, str], CandidateRecordV1] = {}
    for case in corpus.cases:
        for evidence in case.evidence:
            occurrences[(case.case_key, evidence.input_key)] = _candidate_record(case, evidence.input_key)
    versions = default_candidate_index_versions()
    versions["tp0_corpus"] = corpus.corpus_hash()
    snapshot = CandidateIndexSnapshotV1(
        records=tuple(occurrences.values()),
        available_signals=available_signals,
        index_versions=versions,
    )
    return snapshot, occurrences


async def _evaluate_queries(
    *,
    corpus: TemporalReferenceCorpusV1,
    config: TP3CandidateEvaluationConfigV1,
    snapshot: CandidateIndexSnapshotV1,
    occurrences: dict[tuple[str, str], CandidateRecordV1],
    enabled_signals: tuple[CandidateSignal, ...],
    k: int,
    disposition: Literal["gold", "negative"],
) -> tuple[CandidateEvaluationQueryV1, ...]:
    finder = DeterministicCandidateFinder(snapshot)
    results: list[CandidateEvaluationQueryV1] = []
    for case in corpus.cases:
        if _pair_disposition(case) != disposition:
            continue
        left_key, right_key = (item.input_key for item in case.evidence)
        for query_key, expected_key in ((left_key, right_key), (right_key, left_key)):
            query = occurrences[(case.case_key, query_key)]
            expected = occurrences[(case.case_key, expected_key)]
            request = CandidateRequestV1.from_record(
                query,
                enabled_signals=enabled_signals,
                k=k,
                max_candidates=config.maximum_candidates_scored_per_query,
            )
            receipt = await finder.find_candidates(request)
            matched = next(
                (item for item in receipt.candidates if item.record_id == expected.record_id),
                None,
            )
            results.append(
                CandidateEvaluationQueryV1(
                    case_key=case.case_key,
                    query_input_key=query_key,
                    expected_input_key=expected_key,
                    query_record_id=query.record_id,
                    expected_record_id=expected.record_id,
                    receipt_id=str(receipt.receipt_id),
                    found=matched is not None,
                    rank=matched.rank if matched else None,
                    expected_score=matched.score if matched else None,
                    signal_scores=(
                        {part.signal.value: part.score for part in matched.contributions} if matched else {}
                    ),
                )
            )
    return tuple(results)


async def evaluate_tp3_candidate_retrieval(
    corpus_payload: dict[str, Any],
    config_payload: dict[str, Any],
) -> TP3CandidateEvaluationResultV1:
    corpus = TemporalReferenceCorpusV1.model_validate(corpus_payload)
    config = TP3CandidateEvaluationConfigV1.model_validate(config_payload)
    if corpus.corpus_hash() != config.corpus_hash:
        raise ValueError("TP3 evaluation config is bound to a different frozen corpus")
    snapshot, occurrences = _build_snapshot(corpus)
    if len(snapshot.records) > config.maximum_records:
        raise ValueError("TP3 corpus exceeds the frozen evaluation record bound")

    gold = await _evaluate_queries(
        corpus=corpus,
        config=config,
        snapshot=snapshot,
        occurrences=occurrences,
        enabled_signals=ALL_CANDIDATE_SIGNALS,
        k=config.candidate_k,
        disposition="gold",
    )
    negative = await _evaluate_queries(
        corpus=corpus,
        config=config,
        snapshot=snapshot,
        occurrences=occurrences,
        enabled_signals=ALL_CANDIDATE_SIGNALS,
        k=config.negative_control_k,
        disposition="negative",
    )
    gold_found = sum(item.found for item in gold)
    false_associations = sum(item.found for item in negative)
    recall = gold_found / len(gold) if gold else 0.0
    mean_reciprocal_rank = sum(1 / item.rank for item in gold if item.rank is not None) / len(gold) if gold else 0.0
    false_rate = false_associations / len(negative) if negative else 0.0

    ablation_signal = {
        "without_vector": CandidateSignal.VECTOR,
        "without_entity": CandidateSignal.ENTITY,
        "without_temporal": CandidateSignal.TEMPORAL,
    }
    ablations: list[CandidateAblationResultV1] = []
    for name in config.required_ablations:
        removed = ablation_signal[name]
        enabled = tuple(signal for signal in ALL_CANDIDATE_SIGNALS if signal is not removed)
        ablated = await _evaluate_queries(
            corpus=corpus,
            config=config,
            snapshot=snapshot,
            occurrences=occurrences,
            enabled_signals=enabled,
            k=config.candidate_k,
            disposition="gold",
        )
        found = sum(item.found for item in ablated)
        ablated_recall = found / len(ablated) if ablated else 0.0
        ablated_mrr = sum(1 / item.rank for item in ablated if item.rank is not None) / len(ablated) if ablated else 0.0
        ablations.append(
            CandidateAblationResultV1(
                name=name,
                removed_signal=removed,
                gold_neighbor_queries=len(ablated),
                gold_neighbors_found=found,
                recall=ablated_recall,
                recall_delta=ablated_recall - recall,
                mean_reciprocal_rank=ablated_mrr,
                mean_reciprocal_rank_delta=ablated_mrr - mean_reciprocal_rank,
                removed_signal_mean_contribution=(
                    sum(item.signal_scores.get(removed.value, 0.0) for item in gold) / len(gold) if gold else 0.0
                ),
            )
        )

    first_gold = gold[0]
    first_record = next(record for record in snapshot.records if record.record_id == first_gold.query_record_id)
    fallback_snapshot, _ = _build_snapshot(
        corpus,
        available_signals=tuple(signal for signal in ALL_CANDIDATE_SIGNALS if signal is not CandidateSignal.VECTOR),
    )
    fallback_request = CandidateRequestV1.from_record(
        first_record,
        enabled_signals=ALL_CANDIDATE_SIGNALS,
        k=config.candidate_k,
        max_candidates=config.maximum_candidates_scored_per_query,
    )
    fallback_receipt = await DeterministicCandidateFinder(fallback_snapshot).find_candidates(fallback_request)
    finder = DeterministicCandidateFinder(snapshot)
    first_request = CandidateRequestV1.from_record(
        first_record,
        enabled_signals=ALL_CANDIDATE_SIGNALS,
        k=config.candidate_k,
        max_candidates=config.maximum_candidates_scored_per_query,
    )
    deterministic_replay = await finder.find_candidates(first_request) == await finder.find_candidates(first_request)

    recall_met = recall >= config.minimum_gold_neighbor_recall
    false_met = false_rate <= config.maximum_false_association_rate
    return TP3CandidateEvaluationResultV1(
        config_hash=config.config_hash(),
        corpus_hash=corpus.corpus_hash(),
        snapshot_id=str(snapshot.snapshot_id),
        records_indexed=len(snapshot.records),
        gold_neighbor_queries=len(gold),
        gold_neighbors_found=gold_found,
        candidate_recall=recall,
        mean_reciprocal_rank=mean_reciprocal_rank,
        recall_target=config.minimum_gold_neighbor_recall,
        candidate_k=config.candidate_k,
        negative_control_queries=len(negative),
        false_associations=false_associations,
        false_association_rate=false_rate,
        false_association_ceiling=config.maximum_false_association_rate,
        negative_control_k=config.negative_control_k,
        query_results=tuple((*gold, *negative)),
        ablations=tuple(ablations),
        unavailable_index_receipt=fallback_receipt,
        deterministic_replay=deterministic_replay,
        recall_target_met=recall_met,
        false_association_target_met=false_met,
        passed=recall_met and false_met and deterministic_replay,
    )


async def evaluate_tp3_files(
    corpus_path: str | Path = DEFAULT_CORPUS,
    config_path: str | Path = DEFAULT_CONFIG,
) -> TP3CandidateEvaluationResultV1:
    corpus = json.loads(Path(corpus_path).read_text(encoding="utf-8"))
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    return await evaluate_tp3_candidate_retrieval(corpus, config)


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()
    result = asyncio.run(evaluate_tp3_files(args.corpus, args.config))
    print(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))


if __name__ == "__main__":
    _main()
