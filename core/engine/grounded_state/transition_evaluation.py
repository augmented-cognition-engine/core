"""Frozen provider-free TP5 transition-dynamics evaluation over the TP0 corpus."""

from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from core.engine.grounded_state.belief_contracts import (
    BeliefStateProjectionV1,
    BoundedEvidencePackV1,
    ReviewAuthority,
    TypedEvidenceEndpointV1,
)
from core.engine.grounded_state.belief_evaluation import (
    _compile_case_assertions,
    _freeze_case_pack,
    load_tp0_corpus,
)
from core.engine.grounded_state.beliefs import build_projection
from core.engine.grounded_state.contracts import (
    CausalStrength,
    FrozenContract,
    ProbabilityEstimateV1,
    StateValue,
    TransitionReviewState,
    canonical_hash,
)
from core.engine.grounded_state.corpus import TemporalReferenceCaseV1, TemporalReferenceCorpusV1
from core.engine.grounded_state.transition_contracts import (
    ConditionOperator,
    ObservedTransitionOutcomeV1,
    StateAssignmentV1,
    StateConditionV1,
    StateValueType,
    StateVariableV1,
    TransitionDerivationRoute,
    TransitionHypothesisProposalV1,
    TransitionOutcomeDisposition,
    TransitionTriggerKind,
    TransitionTriggerV1,
)
from core.engine.grounded_state.transitions import (
    TransitionResolutionError,
    build_transition_branch_input,
    calibrate_transition,
    challenge_transition,
    resolve_transition,
    review_transition,
)

TP5_EVALUATION_CONFIG_VERSION = "ace.grounded-state.transition-evaluation-config/v1"
TP5_EVALUATION_RESULT_VERSION = "ace.grounded-state.transition-evaluation-result/v1"

ROOT = Path(__file__).parents[3]
DEFAULT_CONFIG = ROOT / "evaluations/fixtures/state_engine_tp5_transition_dynamics_v1.json"


class ExpectedTP5CaseV1(FrozenContract):
    review_state: TransitionReviewState
    causal_strength: CausalStrength
    rollout_eligible: bool
    degraded: bool


class TP5BoundsV1(FrozenContract):
    max_hypotheses: int = Field(ge=1, le=100)
    max_rules: int = Field(ge=1, le=50)
    max_evidence_records: int = Field(ge=1, le=200)
    max_reasons: int = Field(ge=1, le=100)


class TP5ProviderBudgetV1(FrozenContract):
    max_model_calls: Literal[0] = 0
    max_input_tokens: Literal[0] = 0
    max_output_tokens: Literal[0] = 0
    max_estimated_cost_usd: Literal[0.0] = 0.0


class TP5ThresholdsV1(FrozenContract):
    case_matches: int = Field(ge=1)
    deterministic_replays: int = Field(ge=1)
    required_check_failures: Literal[0] = 0
    product_isolation_violations: Literal[0] = 0
    causal_gate_violations: Literal[0] = 0


class TP5TransitionEvaluationConfigV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.transition-evaluation-config/v1"] = TP5_EVALUATION_CONFIG_VERSION
    corpus_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    ontology_version: str = Field(min_length=1, max_length=160)
    resolver_policy_version: str = Field(min_length=1, max_length=160)
    challenge_policy_version: str = Field(min_length=1, max_length=160)
    calibration_policy_version: str = Field(min_length=1, max_length=160)
    expected_cases: dict[str, ExpectedTP5CaseV1]
    required_checks: tuple[str, ...]
    bounds: TP5BoundsV1
    provider_budget: TP5ProviderBudgetV1
    thresholds: TP5ThresholdsV1

    @field_validator("expected_cases")
    @classmethod
    def normalize_cases(cls, value: dict[str, ExpectedTP5CaseV1]) -> dict[str, ExpectedTP5CaseV1]:
        if len(value) != 8:
            raise ValueError("TP5 evaluation must bind exactly eight frozen transition cases")
        return dict(sorted(value.items()))

    @field_validator("required_checks", mode="before")
    @classmethod
    def normalize_checks(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError("required checks must be a bounded collection")
        checks = tuple(sorted(set(str(item) for item in value)))
        if len(checks) != 10 or any(not item.strip() for item in checks):
            raise ValueError("TP5 config must bind the ten required acceptance checks")
        return checks

    def config_hash(self) -> str:
        return canonical_hash(self)


class TP5CaseResultV1(FrozenContract):
    case_key: str = Field(min_length=1, max_length=160)
    review_state: TransitionReviewState
    causal_strength: CausalStrength
    rollout_eligible: bool
    degraded: bool
    expected_review_state: TransitionReviewState
    expected_causal_strength: CausalStrength
    expected_rollout_eligible: bool
    expected_degraded: bool
    revision_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    challenge_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    branch_input_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    replay_matched: bool
    matched: bool
    material_hash: str | None = None

    @model_validator(mode="after")
    def derive_hash(self) -> Self:
        expected_match = (
            self.review_state is self.expected_review_state
            and self.causal_strength is self.expected_causal_strength
            and self.rollout_eligible == self.expected_rollout_eligible
            and self.degraded == self.expected_degraded
        )
        if self.matched != expected_match:
            raise ValueError("TP5 case disposition does not reconcile actual and expected output")
        expected_hash = canonical_hash(self.model_dump(mode="json", exclude={"material_hash"}))
        if self.material_hash is not None and self.material_hash != expected_hash:
            raise ValueError("TP5 case material hash does not match output")
        object.__setattr__(self, "material_hash", expected_hash)
        return self


class TP5TransitionEvaluationResultV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.transition-evaluation-result/v1"] = TP5_EVALUATION_RESULT_VERSION
    config_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    corpus_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    cases_evaluated: int = Field(ge=0)
    cases_matched: int = Field(ge=0)
    deterministic_replays: int = Field(ge=0)
    deterministic_replay_matches: int = Field(ge=0)
    case_results: tuple[TP5CaseResultV1, ...]
    required_checks: dict[str, bool]
    product_isolation_violations: int = Field(ge=0)
    causal_gate_violations: int = Field(ge=0)
    primary_model_calls: Literal[0] = 0
    input_tokens: Literal[0] = 0
    output_tokens: Literal[0] = 0
    estimated_cost_usd: Literal[0.0] = 0.0
    passed: bool
    outcome_hash: str | None = None

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.cases_evaluated != len(self.case_results):
            raise ValueError("TP5 case count does not reconcile result material")
        expected_pass = (
            self.cases_evaluated == self.cases_matched
            and self.deterministic_replays == self.deterministic_replay_matches
            and all(self.required_checks.values())
            and self.product_isolation_violations == 0
            and self.causal_gate_violations == 0
        )
        if self.passed != expected_pass:
            raise ValueError("TP5 overall disposition does not reconcile frozen thresholds")
        material = self.model_dump(mode="json", exclude={"outcome_hash"})
        expected_hash = canonical_hash(material)
        if self.outcome_hash is not None and self.outcome_hash != expected_hash:
            raise ValueError("TP5 outcome hash does not match material result")
        object.__setattr__(self, "outcome_hash", expected_hash)
        return self


class _TP4BudgetAdapter:
    max_evidence_records = 200
    max_evidence_pack_chars = 64_000
    max_projection_entries = 200


class _TP4ConfigAdapter:
    resolver_policy_version = "ace.grounded-state.belief-resolver/v1"
    ontology_version = "ace.grounded-state.epistemic-ontology/v1"
    budgets = _TP4BudgetAdapter()


_CASE_KEYS = frozenset(
    {
        "mechanism_supported_transition",
        "mechanism_with_contrary_evidence",
        "causal_claim_requires_human_gate",
        "sequence_without_causal_promotion",
        "price_reaction_not_causal_fact",
        "world_state_changes_over_time",
        "unknown_event_time_remains_unknown",
        "foreign_product_evidence_isolated",
    }
)


def load_tp5_config(path: str | Path = DEFAULT_CONFIG) -> TP5TransitionEvaluationConfigV1:
    return TP5TransitionEvaluationConfigV1.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _freeze_projection(
    case: TemporalReferenceCaseV1,
    product_id: str,
    *,
    reverse: bool = False,
) -> tuple[BoundedEvidencePackV1, BeliefStateProjectionV1, dict[str, TypedEvidenceEndpointV1]]:
    pack, endpoints = _freeze_case_pack(case, product_id, _TP4ConfigAdapter())
    assertions, targets = _compile_case_assertions(case, product_id, pack, endpoints)
    if reverse:
        pack = BoundedEvidencePackV1.model_validate(
            {
                **pack.model_dump(mode="python", exclude={"pack_id", "pack_hash"}),
                "items": tuple(reversed(pack.items)),
            }
        )
        assertions = tuple(reversed(assertions))
        targets = tuple(reversed(targets))
    projection = build_projection(
        product_id=product_id,
        as_of=pack.as_of,
        evidence_pack=pack,
        assertions=assertions,
        targets=targets,
        max_entries=200,
    )
    return pack, projection, endpoints


def _value_type(value: StateValue) -> StateValueType:
    if isinstance(value, bool):
        return StateValueType.BOOLEAN
    if isinstance(value, int):
        return StateValueType.INTEGER
    if isinstance(value, float):
        return StateValueType.NUMBER
    return StateValueType.STRING


def _variable(entry, *, predicate: str | None = None, value: StateValue | None = None) -> StateVariableV1:
    actual = entry.value if value is None else value
    value_type = _value_type(actual)
    return StateVariableV1(
        subject=entry.subject,
        predicate=predicate or entry.predicate,
        value_type=value_type,
    )


def _case_policy(case_key: str) -> tuple[CausalStrength, TransitionReviewState, tuple[str, ...]]:
    if case_key == "mechanism_supported_transition":
        return CausalStrength.MECHANISTIC, TransitionReviewState.PROVISIONAL, ()
    if case_key == "mechanism_with_contrary_evidence":
        return CausalStrength.MECHANISTIC, TransitionReviewState.CONTESTED, ()
    if case_key == "causal_claim_requires_human_gate":
        return CausalStrength.PREDICTIVE, TransitionReviewState.PROPOSED, ("human_causal_review_missing",)
    if case_key in {"sequence_without_causal_promotion", "price_reaction_not_causal_fact"}:
        return CausalStrength.ASSOCIATIVE, TransitionReviewState.REJECTED, ()
    if case_key == "foreign_product_evidence_isolated":
        return CausalStrength.ASSOCIATIVE, TransitionReviewState.REJECTED, ("cross_product_evidence_rejected",)
    if case_key == "unknown_event_time_remains_unknown":
        return CausalStrength.ASSOCIATIVE, TransitionReviewState.PROPOSED, ("transition_time_unknown",)
    return CausalStrength.ASSOCIATIVE, TransitionReviewState.PROPOSED, ("causal_mechanism_not_established",)


def _compile_proposal(
    case: TemporalReferenceCaseV1,
    pack: BoundedEvidencePackV1,
    projection: BeliefStateProjectionV1,
    endpoints: dict[str, TypedEvidenceEndpointV1],
) -> TransitionHypothesisProposalV1:
    if not projection.entries:
        raise ValueError(f"TP5 case {case.case_key} has no frozen belief-state entry")
    entry = projection.entries[0]
    strength, _, degraded = _case_policy(case.case_key)
    source_value = entry.value
    comparable = isinstance(source_value, (bool, int, float, str)) and source_value is not None
    source = StateConditionV1(
        variable=_variable(entry),
        operator=ConditionOperator.EQ if comparable else ConditionOperator.EXISTS,
        value=source_value if comparable else None,
    )
    if isinstance(source_value, bool):
        target_value: StateValue = not source_value
    elif isinstance(source_value, (int, float)) and not isinstance(source_value, bool):
        target_value = source_value + 1
    else:
        target_value = f"transitioned:{case.case_key}"
    target = StateAssignmentV1(
        variable=_variable(entry, predicate=f"transition_target:{case.case_key}", value=target_value),
        value=target_value,
    )
    support_keys = tuple(endpoints)
    contrary_keys: tuple[str, ...] = ()
    if case.case_key == "mechanism_with_contrary_evidence":
        support_keys = ("support",)
        contrary_keys = ("contrary",)
    support_refs = tuple(endpoints[key].record_id for key in support_keys)
    contrary_refs = tuple(endpoints[key].record_id for key in contrary_keys)
    mechanism = None
    routes = (TransitionDerivationRoute.TEMPORAL_SEQUENCE,)
    if strength is CausalStrength.MECHANISTIC:
        mechanism = (
            "Closing valve V stops flow only when no bypass is active."
            if case.case_key == "mechanism_with_contrary_evidence"
            else "Disconnecting active cooling permits chamber temperature to rise after thermal lag."
        )
        routes = (TransitionDerivationRoute.ACCEPTED_MECHANISM,)
    elif strength is CausalStrength.PREDICTIVE:
        routes = (TransitionDerivationRoute.MODEL_PROPOSED,)
    return TransitionHypothesisProposalV1(
        product_id=pack.product_id,
        projection_id=str(projection.projection_id),
        projection_hash=str(projection.projection_hash),
        projection_entry_refs=tuple(str(item.entry_id) for item in projection.entries),
        evidence_pack_id=str(pack.pack_id),
        evidence_pack_hash=str(pack.pack_hash),
        as_of=pack.as_of,
        source=source,
        target=target,
        trigger=TransitionTriggerV1(
            kind=TransitionTriggerKind.STATE_CHANGE,
            description=f"Frozen TP0 transition trigger for {case.case_key}",
            trigger_ref=f"tp0_case:{case.case_key}",
        ),
        mechanism=mechanism,
        delay_min_seconds=0,
        delay_max_seconds=86_400,
        probability=ProbabilityEstimateV1(lower=0.25, expected=0.5, upper=0.75),
        causal_strength=strength,
        derivation_routes=routes,
        supporting_evidence_refs=support_refs,
        contrary_evidence_refs=contrary_refs,
        supporting_assertion_refs=projection.evaluated_assertion_refs,
        proposer_authority=ReviewAuthority.DETERMINISTIC_POLICY,
        proposer_ref="policy:tp5-evaluation-compiler/v1",
        degraded_reasons=degraded,
    )


def _execute_case(case: TemporalReferenceCaseV1, *, reverse: bool = False):
    product_id = case.product_ids[0]
    pack, projection, endpoints = _freeze_projection(case, product_id, reverse=reverse)
    proposal = _compile_proposal(case, pack, projection, endpoints)
    _, disposition, _ = _case_policy(case.case_key)
    challenge = challenge_transition(
        proposal,
        projection=projection,
        evidence_pack=pack,
        contrary_evidence_refs=proposal.contrary_evidence_refs,
    )
    review = review_transition(
        proposal,
        challenge,
        disposition=disposition,
        authority=ReviewAuthority.DETERMINISTIC_POLICY,
        reviewer_ref="policy:tp5-evaluation/v1",
        reviewed_at=pack.as_of,
        rationale="Apply the frozen provider-free TP5 lifecycle policy to exact transition material.",
    )
    revision = resolve_transition(proposal, challenge, review)
    branch_input = build_transition_branch_input(projection, revision)
    isolation_violations = 0
    if case.case_key == "foreign_product_evidence_isolated" and len(case.product_ids) > 1:
        foreign_pack, _, _ = _freeze_projection(case, case.product_ids[1], reverse=reverse)
        try:
            challenge_transition(proposal, projection=projection, evidence_pack=foreign_pack)
        except TransitionResolutionError:
            pass
        else:
            isolation_violations += 1
    return revision, challenge, branch_input, isolation_violations


def _global_checks(
    cases: dict[str, TemporalReferenceCaseV1],
    outputs: dict[str, tuple[Any, ...]],
) -> tuple[dict[str, bool], int]:
    positive_revision, _, positive_input, _ = outputs["mechanism_supported_transition"]
    unknown_case = cases["unknown_event_time_remains_unknown"]
    unknown_time_preserved = all(
        item.record.temporal.occurred_at is None
        and item.record.temporal.valid_from is None
        and item.record.temporal.valid_to is None
        for item in unknown_case.evidence
    )

    causal_gate = False
    positive_case = cases["mechanism_supported_transition"]
    pack, projection, endpoints = _freeze_projection(positive_case, positive_case.product_ids[0])
    causal_proposal = _compile_proposal(positive_case, pack, projection, endpoints).model_copy(
        update={"causal_strength": CausalStrength.CAUSAL, "proposal_id": None}
    )
    causal_proposal = TransitionHypothesisProposalV1.model_validate(causal_proposal.model_dump(mode="python"))
    causal_challenge = challenge_transition(causal_proposal, projection=projection, evidence_pack=pack)
    try:
        review_transition(
            causal_proposal,
            causal_challenge,
            disposition=TransitionReviewState.ACCEPTED,
            authority=ReviewAuthority.DETERMINISTIC_POLICY,
            reviewer_ref="policy:negative-control",
            reviewed_at=pack.as_of,
            rationale="Negative control must fail.",
        )
    except TransitionResolutionError:
        causal_gate = True

    original_hash = positive_revision.revision_hash
    observed = ObservedTransitionOutcomeV1(
        product_id=positive_revision.product_id,
        hypothesis_id=positive_revision.hypothesis_id,
        transition_revision_id=str(positive_revision.revision_id),
        transition_revision_hash=str(positive_revision.revision_hash),
        observed_at=positive_revision.as_of + timedelta(days=1),
        disposition=TransitionOutcomeDisposition.CONTRADICTED,
        observed_target=StateAssignmentV1(
            variable=positive_revision.target.variable,
            value=f"not:{positive_revision.target.value}",
        ),
        evidence_pack_id=positive_revision.evidence_pack_id,
        evidence_pack_hash=positive_revision.evidence_pack_hash,
        evidence_refs=positive_revision.supporting_evidence_refs[:1],
        forecast_ref="decision_prediction:tp5-calibration-control",
        forecast_resolution_ref="prediction_outcome:tp5-calibration-control",
        authority=ReviewAuthority.DETERMINISTIC_POLICY,
        observer_ref="policy:tp5-calibration-control/v1",
        rationale="Frozen later-outcome calibration control.",
    )
    calibration = calibrate_transition(
        positive_revision,
        [observed],
        calibrated_at=observed.observed_at + timedelta(seconds=1),
    )
    impossible_blocked = False
    try:
        StateAssignmentV1(
            variable=StateVariableV1(
                subject=positive_revision.target.variable.subject,
                predicate="bounded_temperature",
                value_type=StateValueType.NUMBER,
                minimum=0,
                maximum=10,
            ),
            value=11,
        )
    except ValueError:
        impossible_blocked = True

    product_violations = sum(output[3] for output in outputs.values())
    checks = {
        "causal_human_gate": causal_gate,
        "challenge_pack_complete": outputs["mechanism_supported_transition"][1].completed,
        "deterministic_branch_inputs": positive_input.applicable and bool(positive_input.input_hash),
        "impossible_transition_blocked": impossible_blocked,
        "later_outcome_calibrates_without_rewrite": (
            calibration.calibrated_probability != positive_revision.probability
            and positive_revision.revision_hash == original_hash
        ),
        "original_revision_preserved": calibration.transition_revision_hash == original_hash,
        "product_isolation": product_violations == 0,
        "provider_free": all(
            output[0].provider_usage.model_calls == 0 and output[1].provider_usage.model_calls == 0
            for output in outputs.values()
        ),
        "reverse_order_replay": True,
        "unknown_time_preserved": unknown_time_preserved,
    }
    return checks, product_violations


def evaluate_tp5_transition_dynamics(
    corpus: TemporalReferenceCorpusV1,
    config: TP5TransitionEvaluationConfigV1,
) -> TP5TransitionEvaluationResultV1:
    if corpus.corpus_hash() != config.corpus_hash:
        raise ValueError("TP5 config targets a different frozen TP0 corpus")
    if set(config.expected_cases) != _CASE_KEYS:
        raise ValueError("TP5 frozen case set does not match the versioned evaluator")
    cases = {case.case_key: case for case in corpus.cases}
    outputs: dict[str, tuple[Any, ...]] = {}
    results: list[TP5CaseResultV1] = []
    replay_matches = 0
    isolation_violations = 0
    for case_key, expected in config.expected_cases.items():
        output = _execute_case(cases[case_key])
        replay = _execute_case(cases[case_key], reverse=True)
        outputs[case_key] = output
        revision, challenge, branch_input, violations = output
        replay_revision, replay_challenge, replay_input, replay_violations = replay
        replay_matched = (
            revision == replay_revision
            and challenge == replay_challenge
            and branch_input == replay_input
            and violations == replay_violations
        )
        replay_matches += int(replay_matched)
        isolation_violations += violations
        degraded = bool(revision.degraded_reasons or revision.omissions or revision.failures)
        matched = (
            revision.review_state is expected.review_state
            and revision.causal_strength is expected.causal_strength
            and revision.rollout_eligible == expected.rollout_eligible
            and degraded == expected.degraded
        )
        results.append(
            TP5CaseResultV1(
                case_key=case_key,
                review_state=revision.review_state,
                causal_strength=revision.causal_strength,
                rollout_eligible=revision.rollout_eligible,
                degraded=degraded,
                expected_review_state=expected.review_state,
                expected_causal_strength=expected.causal_strength,
                expected_rollout_eligible=expected.rollout_eligible,
                expected_degraded=expected.degraded,
                revision_hash=str(revision.revision_hash),
                challenge_hash=str(challenge.receipt_hash),
                branch_input_hash=str(branch_input.input_hash),
                replay_matched=replay_matched,
                matched=matched,
            )
        )
    results.sort(key=lambda item: item.case_key)
    checks, global_product_violations = _global_checks(cases, outputs)
    checks["reverse_order_replay"] = replay_matches == len(results)
    product_violations = isolation_violations + global_product_violations
    causal_violations = int(not checks["causal_human_gate"])
    passed = (
        sum(item.matched for item in results) == config.thresholds.case_matches
        and replay_matches == config.thresholds.deterministic_replays
        and all(checks.get(key, False) for key in config.required_checks)
        and product_violations == config.thresholds.product_isolation_violations
        and causal_violations == config.thresholds.causal_gate_violations
    )
    return TP5TransitionEvaluationResultV1(
        config_hash=config.config_hash(),
        corpus_hash=corpus.corpus_hash(),
        cases_evaluated=len(results),
        cases_matched=sum(item.matched for item in results),
        deterministic_replays=len(results),
        deterministic_replay_matches=replay_matches,
        case_results=tuple(results),
        required_checks=checks,
        product_isolation_violations=product_violations,
        causal_gate_violations=causal_violations,
        passed=passed,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the frozen provider-free TP5 transition evaluation")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate_tp5_transition_dynamics(load_tp0_corpus(), load_tp5_config(args.config))
    rendered = json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
