"""Frozen provider-free TP4 semantic evaluation over the TP0 corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from core.engine.grounded_state.belief_contracts import (
    AssertionReviewV1,
    BoundedEvidencePackV1,
    EpistemicAssertionProposalV1,
    EpistemicRelation,
    EvidenceEndpointKind,
    EvidencePackItemV1,
    ProjectionTargetV1,
    ReviewAuthority,
    ReviewDisposition,
    TypedEvidenceEndpointV1,
)
from core.engine.grounded_state.beliefs import build_projection, resolve_assertion
from core.engine.grounded_state.contracts import BeliefStatus, EvidenceKind, FrozenContract, canonical_hash
from core.engine.grounded_state.corpus import ReferenceCategory, TemporalReferenceCaseV1, TemporalReferenceCorpusV1

TP4_EVALUATION_CONFIG_VERSION = "ace.grounded-state.tp4-belief-evaluation-config/v1"
TP4_EVALUATION_RESULT_VERSION = "ace.grounded-state.tp4-belief-evaluation-result/v1"

ROOT = Path(__file__).parents[3]
DEFAULT_CORPUS = Path(__file__).parent / "fixtures/temporal_reference_candidate_v1.json"
DEFAULT_CONFIG = ROOT / "evaluations/fixtures/state_engine_tp4_belief_projection_v1.json"


class ExpectedTP4CaseV1(FrozenContract):
    states: tuple[Literal["supported", "contested", "provisional", "superseded", "unknown"], ...]
    relationship: str = Field(min_length=1, max_length=120)

    @field_validator("states", mode="before")
    @classmethod
    def normalize_states(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError("expected states must be a collection")
        return tuple(sorted(set(value)))


class TP4EvaluationBudgetsV1(FrozenContract):
    max_evidence_records: int = Field(ge=1, le=200)
    max_candidate_records: int = Field(ge=1, le=200)
    max_projection_entries: int = Field(ge=1, le=200)
    max_evidence_pack_chars: int = Field(ge=1, le=64_000)
    max_counterevidence_records: int = Field(ge=1, le=200)
    max_reopened_assertions: int = Field(ge=1, le=200)
    max_model_calls: Literal[0] = 0
    max_input_tokens: Literal[0] = 0
    max_output_tokens: Literal[0] = 0
    max_estimated_cost_usd: Literal[0.0] = 0.0


class TP4EvaluationThresholdsV1(FrozenContract):
    required_case_match_rate: Literal[1.0] = 1.0
    deterministic_replay_rate: Literal[1.0] = 1.0
    product_isolation_violations: Literal[0] = 0
    causal_negative_control_violations: Literal[0] = 0
    unlinked_operational_entries: Literal[0] = 0
    provider_budget_violations: Literal[0] = 0


class TP4BeliefEvaluationConfigV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.tp4-belief-evaluation-config/v1"] = TP4_EVALUATION_CONFIG_VERSION
    corpus_contract_version: str
    corpus_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    evaluation_seed: int
    ontology_version: str
    resolver_policy_version: str
    projection_policy_version: str
    assertion_policy_version: str
    inference_policy_version: str
    expected_classifications: dict[str, ExpectedTP4CaseV1]
    required_checks: tuple[str, ...]
    budgets: TP4EvaluationBudgetsV1
    thresholds: TP4EvaluationThresholdsV1
    notes: tuple[str, ...]

    @field_validator("expected_classifications")
    @classmethod
    def normalize_cases(cls, value: dict[str, ExpectedTP4CaseV1]) -> dict[str, ExpectedTP4CaseV1]:
        if len(value) < 10:
            raise ValueError("TP4 evaluation must bind the required temporal and causal cases")
        return dict(sorted(value.items()))

    @field_validator("required_checks", "notes", mode="before")
    @classmethod
    def normalize_strings(cls, value: Any, info) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError(f"{info.field_name} must be a collection")
        items = tuple(sorted(set(str(item) for item in value)))
        if not items or any(not item.strip() or len(item) > 1_000 for item in items):
            raise ValueError(f"{info.field_name} must contain bounded non-empty strings")
        return items

    def config_hash(self) -> str:
        return canonical_hash(self)


class TP4CaseResultV1(FrozenContract):
    case_key: str
    states: tuple[str, ...]
    relationship: str
    projection_hashes: tuple[str, ...] = Field(min_length=1, max_length=8)
    expected_states: tuple[str, ...]
    expected_relationship: str
    unknown_time_preserved: bool
    matched: bool
    material_hash: str | None = None

    @field_validator("states", "expected_states", "projection_hashes", mode="before")
    @classmethod
    def normalize_states(cls, value: Any, info) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError("case states must be a collection")
        normalized = tuple(sorted(set(str(item) for item in value)))
        if info.field_name == "projection_hashes" and any(
            len(item) != 64 or any(char not in "0123456789abcdef" for char in item) for item in normalized
        ):
            raise ValueError("projection hashes must be lowercase SHA-256 digests")
        return normalized

    @model_validator(mode="after")
    def derive_hash(self) -> Self:
        if self.matched != (self.states == self.expected_states and self.relationship == self.expected_relationship):
            raise ValueError("TP4 case match disposition does not reconcile material output")
        expected_hash = canonical_hash(self.model_dump(mode="json", exclude={"material_hash"}))
        if self.material_hash is not None and self.material_hash != expected_hash:
            raise ValueError("TP4 case material hash does not match output")
        object.__setattr__(self, "material_hash", expected_hash)
        return self


class TP4BeliefEvaluationResultV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.tp4-belief-evaluation-result/v1"] = TP4_EVALUATION_RESULT_VERSION
    config_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    corpus_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    cases_evaluated: int = Field(ge=0)
    cases_matched: int = Field(ge=0)
    case_match_rate: float = Field(ge=0, le=1)
    case_results: tuple[TP4CaseResultV1, ...]
    deterministic_replays: int = Field(ge=0)
    deterministic_replay_matches: int = Field(ge=0)
    deterministic_replay_rate: float = Field(ge=0, le=1)
    semantic_checks: dict[str, bool]
    runtime_checks_deferred: tuple[str, ...]
    product_isolation_violations: int = Field(ge=0)
    causal_negative_control_violations: int = Field(ge=0)
    unlinked_operational_entries: int = Field(ge=0)
    primary_model_calls: Literal[0] = 0
    input_tokens: Literal[0] = 0
    output_tokens: Literal[0] = 0
    estimated_cost_usd: Literal[0.0] = 0.0
    passed: bool
    outcome_hash: str | None = None

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        expected_rate = self.cases_matched / self.cases_evaluated if self.cases_evaluated else 0
        replay_rate = (
            self.deterministic_replay_matches / self.deterministic_replays if self.deterministic_replays else 0
        )
        if self.cases_evaluated != len(self.case_results) or abs(self.case_match_rate - expected_rate) > 1e-12:
            raise ValueError("TP4 case counts must reconcile")
        if abs(self.deterministic_replay_rate - replay_rate) > 1e-12:
            raise ValueError("TP4 replay counts must reconcile")
        expected_pass = (
            self.case_match_rate == 1
            and self.deterministic_replay_rate == 1
            and all(self.semantic_checks.values())
            and self.product_isolation_violations == 0
            and self.causal_negative_control_violations == 0
            and self.unlinked_operational_entries == 0
        )
        if self.passed != expected_pass:
            raise ValueError("TP4 overall disposition does not reconcile frozen thresholds")
        material = self.model_dump(mode="json", exclude={"outcome_hash"})
        expected_hash = canonical_hash(material)
        if self.outcome_hash is not None and self.outcome_hash != expected_hash:
            raise ValueError("TP4 outcome hash does not match material result")
        object.__setattr__(self, "outcome_hash", expected_hash)
        return self


_CASE_KEYS = frozenset(
    {
        "exact_replay_identical",
        "source_version_replaces_prior",
        "restatement_not_corroboration",
        "independent_factory_corroboration",
        "world_state_changes_over_time",
        "same_interval_operating_conflict",
        "unknown_event_time_remains_unknown",
        "contested_delivery_belief",
        "unknown_property_belief",
        "price_reaction_not_causal_fact",
        "sequence_without_causal_promotion",
        "causal_claim_requires_human_gate",
        "foreign_product_evidence_isolated",
    }
)


def load_tp4_config(path: str | Path = DEFAULT_CONFIG) -> TP4BeliefEvaluationConfigV1:
    return TP4BeliefEvaluationConfigV1.model_validate_json(Path(path).read_text(encoding="utf-8"))


def load_tp0_corpus(path: str | Path = DEFAULT_CORPUS) -> TemporalReferenceCorpusV1:
    return TemporalReferenceCorpusV1.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _evidence_endpoint(case_key: str, input_key: str, record) -> TypedEvidenceEndpointV1:
    kind_by_record = {
        EvidenceKind.SOURCE_DOCUMENT: (EvidenceEndpointKind.SOURCE, "grounded_source:"),
        EvidenceKind.CLAIM: (EvidenceEndpointKind.CLAIM, "grounded_claim:"),
        EvidenceKind.EVENT: (EvidenceEndpointKind.EVENT, "grounded_event:"),
        EvidenceKind.ENTITY: (EvidenceEndpointKind.ENTITY, "grounded_entity:"),
        EvidenceKind.ALIAS: (EvidenceEndpointKind.ALIAS, "grounded_alias:"),
        EvidenceKind.MENTION: (EvidenceEndpointKind.ALIAS, "grounded_alias:"),
    }
    endpoint_kind, prefix = kind_by_record[record.kind]
    return TypedEvidenceEndpointV1(
        product_id=record.product_id,
        kind=endpoint_kind,
        record_id=f"{prefix}{canonical_hash({'case_key': case_key, 'input_key': input_key, 'record': record.model_dump(mode='json')})[:32]}",
        record_version=record.source_version,
        content_hash=record.content_hash,
    )


def _belief_subject(product_id: str, subject: str) -> TypedEvidenceEndpointV1:
    kind = EvidenceEndpointKind.ENTITY if subject.startswith("entity:") else EvidenceEndpointKind.STATE
    record_id = subject if kind is EvidenceEndpointKind.ENTITY else f"belief_state:{canonical_hash(subject)[:32]}"
    return TypedEvidenceEndpointV1(
        product_id=product_id,
        kind=kind,
        record_id=record_id,
        record_version="tp0-owner-reviewed/v1",
        content_hash=canonical_hash(subject),
    )


def _state_endpoint(product_id: str, case_key: str, predicate: str, value: Any) -> TypedEvidenceEndpointV1:
    material = {"case_key": case_key, "predicate": predicate, "value": value}
    return TypedEvidenceEndpointV1(
        product_id=product_id,
        kind=EvidenceEndpointKind.STATE,
        record_id=f"belief_state:{canonical_hash(material)[:32]}",
        record_version="tp4-evaluation/v1",
        content_hash=canonical_hash(material),
    )


def _freeze_case_pack(
    case: TemporalReferenceCaseV1,
    product_id: str,
    config: TP4BeliefEvaluationConfigV1,
) -> tuple[BoundedEvidencePackV1, dict[str, TypedEvidenceEndpointV1]]:
    selected = [item for item in case.evidence if item.record.product_id == product_id]
    endpoint_by_key = {
        item.input_key: _evidence_endpoint(case.case_key, item.input_key, item.record) for item in selected
    }
    items = tuple(
        EvidencePackItemV1(
            endpoint=endpoint_by_key[item.input_key],
            temporal=item.record.temporal,
            published_at=item.record.published_at,
            ingested_at=item.record.ingested_at,
            extracted_at=item.record.extracted_at,
            ace_created_at=item.record.ingested_at,
            source_id=item.record.source_id,
            publisher_id=item.record.source_id,
            compact_content=item.record.content,
            source_confidence=item.record.confidence,
            candidate_rank=index,
            selection_signals=("frozen_tp0_case",),
        )
        for index, item in enumerate(selected, start=1)
    )
    selected_chars = sum(len(item.compact_content or "") for item in items)
    receipt_material = {"case_key": case.case_key, "product_id": product_id, "inputs": tuple(endpoint_by_key)}
    pack = BoundedEvidencePackV1(
        product_id=product_id,
        as_of=case.as_of_times[-1],
        query_hash=canonical_hash({"case_key": case.case_key, "product_id": product_id}),
        candidate_receipt_id=f"candidate_receipt:{canonical_hash(receipt_material)[:32]}",
        candidate_receipt_hash=canonical_hash(receipt_material),
        resolver_policy_version=config.resolver_policy_version,
        ontology_version=config.ontology_version,
        items=items,
        candidate_count=len(items),
        selected_count=len(items),
        max_records=config.budgets.max_evidence_records,
        max_chars=config.budgets.max_evidence_pack_chars,
        selected_chars=selected_chars,
    )
    return pack, endpoint_by_key


def _compile_case_assertions(
    case: TemporalReferenceCaseV1,
    product_id: str,
    pack: BoundedEvidencePackV1,
    endpoint_by_key: dict[str, TypedEvidenceEndpointV1],
    *,
    include_lineage: bool = False,
):
    evidence_by_key = {item.input_key: item.record for item in case.evidence if item.record.product_id == product_id}
    beliefs = sorted(
        (belief for belief in case.expected.beliefs if belief.product_id == product_id),
        key=lambda belief: (
            belief.validity.valid_from or belief.validity.occurred_at or belief.as_of,
            belief.predicate,
            canonical_hash(belief.value),
        ),
    )
    assertions = []
    proposals = []
    reviews = []
    targets = []
    prior_by_belief: dict[tuple[str, str], str] = {}
    for belief in beliefs:
        if not belief.supporting_evidence_keys:
            targets.append(
                ProjectionTargetV1(
                    subject=_belief_subject(product_id, belief.subject),
                    predicate=belief.predicate,
                )
            )
            continue
        support_refs = tuple(endpoint_by_key[key].record_id for key in belief.supporting_evidence_keys)
        contrary_refs = tuple(endpoint_by_key[key].record_id for key in belief.contradicting_evidence_keys)
        supporting_records = [evidence_by_key[key] for key in belief.supporting_evidence_keys]
        relation = EpistemicRelation.SUPPORTS
        supersedes_refs: tuple[str, ...] = ()
        belief_key = (belief.subject, belief.predicate)
        if contrary_refs:
            relation = EpistemicRelation.CONTRADICTS
        elif case.primary_category in {ReferenceCategory.RESTATEMENT, ReferenceCategory.INDEPENDENT_CORROBORATION}:
            relation = EpistemicRelation.CORROBORATES
        elif any(record.supersedes for record in supporting_records) and belief_key in prior_by_belief:
            relation = EpistemicRelation.SUPERSEDES
            supersedes_refs = (prior_by_belief[belief_key],)
        subject_endpoint = endpoint_by_key[belief.supporting_evidence_keys[0]]
        if contrary_refs:
            object_endpoint = endpoint_by_key[belief.contradicting_evidence_keys[0]]
        elif len(belief.supporting_evidence_keys) > 1:
            object_endpoint = endpoint_by_key[belief.supporting_evidence_keys[1]]
        else:
            object_endpoint = _state_endpoint(product_id, case.case_key, belief.predicate, belief.value)
        origins = tuple(sorted({record.source_id for record in supporting_records}))
        if case.primary_category is ReferenceCategory.RESTATEMENT:
            origins = (f"source_chain:{case.case_key}",)
        proposal = EpistemicAssertionProposalV1(
            product_id=product_id,
            subject=subject_endpoint,
            relation=relation,
            object=object_endpoint,
            belief_subject=_belief_subject(product_id, belief.subject),
            belief_predicate=belief.predicate,
            belief_value=belief.value,
            supersedes_assertion_refs=supersedes_refs,
            validity=belief.validity,
            occurred_at=belief.validity.occurred_at,
            proposed_at=belief.as_of,
            evidence_pack_id=str(pack.pack_id),
            evidence_pack_hash=str(pack.pack_hash),
            supporting_evidence_refs=support_refs,
            contrary_evidence_refs=contrary_refs,
            source_origin_ids=origins,
            source_confidence=min(
                (record.confidence for record in supporting_records if record.confidence is not None), default=None
            ),
            epistemic_confidence=0.75,
            freshness=0.9,
            rationale="Frozen TP0 owner-reviewed semantic input for TP4 projection evaluation.",
            proposer_authority="deterministic_policy",
            proposer_ref="policy:tp4-evaluation-compiler/v1",
        )
        review_disposition = (
            ReviewDisposition.PROPOSED
            if case.primary_category is ReferenceCategory.UNKNOWN_TIME
            else ReviewDisposition.ACCEPTED
        )
        review = AssertionReviewV1(
            product_id=product_id,
            proposal_id=str(proposal.proposal_id),
            assertion_id=proposal.assertion_id(),
            reviewed_material_hash=proposal.review_material_hash(),
            disposition=review_disposition,
            authority=ReviewAuthority.DETERMINISTIC_POLICY,
            reviewer_ref="policy:tp4-evaluation/v1",
            reviewed_at=belief.as_of,
            rationale="Apply the frozen provider-free TP4 assertion policy to exact semantic input.",
            policy_version=proposal.assertion_policy_version,
        )
        assertion = resolve_assertion(proposal, review)
        proposals.append(proposal)
        reviews.append(review)
        assertions.append(assertion)
        prior_by_belief[belief_key] = assertion.assertion_id
    if include_lineage:
        return tuple(assertions), tuple(targets), tuple(proposals), tuple(reviews)
    return tuple(assertions), tuple(targets)


def _negative_control_is_provisional(
    case: TemporalReferenceCaseV1,
    pack: BoundedEvidencePackV1,
    endpoint_by_key: dict[str, TypedEvidenceEndpointV1],
) -> bool:
    if case.primary_category not in {
        ReferenceCategory.REACTION_SEQUENCE,
        ReferenceCategory.TEMPORAL_SEQUENCE_NO_CAUSATION,
        ReferenceCategory.HUMAN_GATED_CAUSAL_CLAIM,
    }:
        return True
    endpoints = tuple(endpoint_by_key.values())
    if len(endpoints) < 2:
        return False
    proposal = EpistemicAssertionProposalV1(
        product_id=pack.product_id,
        subject=endpoints[0],
        relation=EpistemicRelation.CAUSES,
        object=endpoints[1],
        proposed_at=pack.as_of,
        evidence_pack_id=str(pack.pack_id),
        evidence_pack_hash=str(pack.pack_hash),
        supporting_evidence_refs=tuple(item.endpoint.record_id for item in pack.items),
        source_origin_ids=tuple(sorted({item.source_id for item in pack.items})),
        rationale="Negative-control causal proposal must remain unaccepted without its human gate.",
        proposer_authority="model",
        proposer_ref="model:tp4-negative-control",
    )
    review = AssertionReviewV1(
        product_id=pack.product_id,
        proposal_id=str(proposal.proposal_id),
        assertion_id=proposal.assertion_id(),
        reviewed_material_hash=proposal.review_material_hash(),
        disposition=ReviewDisposition.PROPOSED,
        authority=ReviewAuthority.MODEL,
        reviewer_ref="model:tp4-negative-control-review",
        reviewed_at=pack.as_of,
        rationale="No model-authored causal proposal can authorize itself.",
        policy_version=proposal.assertion_policy_version,
    )
    return resolve_assertion(proposal, review).disposition is ReviewDisposition.PROPOSED


def _relationship_from_execution(
    case: TemporalReferenceCaseV1,
    projections,
    assertions,
    causal_gate_held: bool,
) -> str:
    entries = tuple(entry for projection in projections for entry in projection.entries)
    records = tuple(item.record for item in case.evidence)
    if case.primary_category is ReferenceCategory.EXACT_REPLAY:
        return "exact_replay" if len({record.evidence_id() for record in records}) == 1 else "unclassified"
    if case.primary_category is ReferenceCategory.SOURCE_VERSION_REPLACEMENT:
        return "source_version_replacement" if any(record.supersedes for record in records) else "unclassified"
    if case.primary_category is ReferenceCategory.RESTATEMENT:
        return "restatement" if {entry.status for entry in entries} == {BeliefStatus.PROVISIONAL} else "unclassified"
    if case.primary_category is ReferenceCategory.INDEPENDENT_CORROBORATION:
        accepted = any(
            assertion.relation is EpistemicRelation.CORROBORATES and assertion.disposition is ReviewDisposition.ACCEPTED
            for assertion in assertions
        )
        return "corroborates" if accepted else "unclassified"
    if case.primary_category is ReferenceCategory.TEMPORAL_CHANGE:
        ordered = sorted(entries, key=lambda entry: entry.validity.valid_from or entry.as_of)
        separated = len(ordered) >= 2 and all(
            left.validity.valid_to is not None
            and right.validity.valid_from is not None
            and left.validity.valid_to < right.validity.valid_from
            for left, right in zip(ordered, ordered[1:])
        )
        return "state_transition" if separated else "unclassified"
    if case.primary_category in {ReferenceCategory.SAME_INTERVAL_CONTRADICTION, ReferenceCategory.BELIEF_CONTESTED}:
        return (
            "same_interval_contradiction"
            if any(entry.status is BeliefStatus.CONTESTED for entry in entries)
            else "unclassified"
        )
    if case.primary_category in {ReferenceCategory.UNKNOWN_TIME, ReferenceCategory.BELIEF_UNKNOWN}:
        return "background_evidence"
    if case.primary_category is ReferenceCategory.REACTION_SEQUENCE:
        return "reacts_to" if causal_gate_held else "causes"
    if case.primary_category is ReferenceCategory.TEMPORAL_SEQUENCE_NO_CAUSATION:
        return "precedes" if causal_gate_held else "causes"
    if case.primary_category is ReferenceCategory.HUMAN_GATED_CAUSAL_CLAIM:
        return "causal_candidate" if causal_gate_held else "causes"
    if case.primary_category is ReferenceCategory.CROSS_PRODUCT_ISOLATION:
        return "cross_product_isolated" if len(projections) == len(case.product_ids) else "unclassified"
    return "unclassified"


def _execute_case(case: TemporalReferenceCaseV1, config: TP4BeliefEvaluationConfigV1):
    projections = []
    replays = []
    all_assertions = []
    causal_gate_held = True
    product_violations = 0
    unlinked = 0
    for product_id in case.product_ids:
        pack, endpoints = _freeze_case_pack(case, product_id, config)
        assertions, targets = _compile_case_assertions(case, product_id, pack, endpoints)
        projection = build_projection(
            product_id=product_id,
            as_of=pack.as_of,
            evidence_pack=pack,
            assertions=assertions,
            targets=targets,
            max_entries=config.budgets.max_projection_entries,
        )
        replay_pack = BoundedEvidencePackV1.model_validate(
            {
                **pack.model_dump(mode="python", exclude={"pack_id", "pack_hash"}),
                "items": tuple(reversed(pack.items)),
            }
        )
        replay = build_projection(
            product_id=product_id,
            as_of=replay_pack.as_of,
            evidence_pack=replay_pack,
            assertions=tuple(reversed(assertions)),
            targets=tuple(reversed(targets)),
            max_entries=config.budgets.max_projection_entries,
        )
        projections.append(projection)
        replays.append(projection == replay)
        all_assertions.extend(assertions)
        causal_gate_held = causal_gate_held and _negative_control_is_provisional(case, pack, endpoints)
        product_violations += sum(entry.product_id != product_id for entry in projection.entries)
        unlinked += sum(
            entry.operational
            and not (
                entry.accepted_assertion_id
                and entry.assertion_revision_id
                and entry.review_id
                and entry.supporting_evidence_refs
            )
            for entry in projection.entries
        )
    states = tuple(sorted({entry.status.value for projection in projections for entry in projection.entries}))
    relationship = _relationship_from_execution(case, projections, all_assertions, causal_gate_held)
    projection_hashes = tuple(str(projection.projection_hash) for projection in projections)
    return (
        states,
        relationship,
        projection_hashes,
        all(replays),
        product_violations,
        int(not causal_gate_held),
        unlinked,
    )


def evaluate_tp4_belief_projection(
    corpus: TemporalReferenceCorpusV1,
    config: TP4BeliefEvaluationConfigV1,
) -> TP4BeliefEvaluationResultV1:
    if corpus.corpus_hash() != config.corpus_hash:
        raise ValueError("TP4 config targets a different frozen TP0 corpus")
    if set(config.expected_classifications) != _CASE_KEYS:
        raise ValueError("TP4 frozen case set does not match the versioned evaluator")
    case_by_key = {case.case_key: case for case in corpus.cases}
    results: list[TP4CaseResultV1] = []
    replay_matches = 0
    product_isolation_violations = 0
    causal_negative_control_violations = 0
    unlinked_operational_entries = 0
    for case_key, expected in config.expected_classifications.items():
        case = case_by_key[case_key]
        (
            states,
            relationship,
            projection_hashes,
            replay_matched,
            product_violations,
            causal_violations,
            unlinked,
        ) = _execute_case(case, config)
        replay_matches += int(replay_matched)
        product_isolation_violations += product_violations
        causal_negative_control_violations += causal_violations
        unlinked_operational_entries += unlinked
        unknown_time_preserved = all(
            item.record.temporal.precision.value != "unknown"
            or (
                item.record.temporal.occurred_at is None
                and item.record.temporal.valid_from is None
                and item.record.temporal.valid_to is None
            )
            for item in case.evidence
        )
        results.append(
            TP4CaseResultV1(
                case_key=case_key,
                states=states,
                relationship=relationship,
                projection_hashes=projection_hashes,
                expected_states=expected.states,
                expected_relationship=expected.relationship,
                unknown_time_preserved=unknown_time_preserved,
                matched=tuple(sorted(states)) == expected.states and relationship == expected.relationship,
            )
        )
    results.sort(key=lambda item: item.case_key)
    relationship_by_key = {item.case_key: item.relationship for item in results}
    semantic_checks = {
        "causal_negative_controls": all(
            relationship_by_key[key] != "causes"
            for key in (
                "price_reaction_not_causal_fact",
                "sequence_without_causal_promotion",
                "causal_claim_requires_human_gate",
            )
        ),
        "corroboration_distinct_from_restatement": (
            relationship_by_key["independent_factory_corroboration"]
            != relationship_by_key["restatement_not_corroboration"]
        ),
        "product_isolation_visible": (
            relationship_by_key["foreign_product_evidence_isolated"] == "cross_product_isolated"
        ),
        "temporal_update_not_contradiction": (
            relationship_by_key["world_state_changes_over_time"] == "state_transition"
            and relationship_by_key["same_interval_operating_conflict"] == "same_interval_contradiction"
        ),
        "unknown_time_preserved": all(item.unknown_time_preserved for item in results),
    }
    deferred = tuple(
        sorted(
            {
                "api_service_restart",
                "database_restart_replay",
                "exact_eleven_tool_surface",
                "migration_replay",
                "naked_kernel_without_extensions",
            }
        )
    )
    matches = sum(item.matched for item in results)
    return TP4BeliefEvaluationResultV1(
        config_hash=config.config_hash(),
        corpus_hash=corpus.corpus_hash(),
        cases_evaluated=len(results),
        cases_matched=matches,
        case_match_rate=matches / len(results),
        case_results=tuple(results),
        deterministic_replays=len(results),
        deterministic_replay_matches=replay_matches,
        deterministic_replay_rate=replay_matches / len(results),
        semantic_checks=semantic_checks,
        runtime_checks_deferred=deferred,
        product_isolation_violations=product_isolation_violations,
        causal_negative_control_violations=causal_negative_control_violations,
        unlinked_operational_entries=unlinked_operational_entries,
        passed=(
            matches == len(results)
            and replay_matches == len(results)
            and all(semantic_checks.values())
            and product_isolation_violations == 0
            and causal_negative_control_violations == 0
            and unlinked_operational_entries == 0
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    result = evaluate_tp4_belief_projection(load_tp0_corpus(args.corpus), load_tp4_config(args.config))
    print(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
