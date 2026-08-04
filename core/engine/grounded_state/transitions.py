"""Provider-free TP5 transition challenge, resolution, and calibration."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from core.engine.grounded_state.belief_contracts import (
    AssertionReviewV1,
    BeliefStateProjectionV1,
    BoundedEvidencePackV1,
    EpistemicAssertionProposalV1,
    EpistemicAssertionV1,
    ReviewAuthority,
)
from core.engine.grounded_state.contracts import (
    CausalStrength,
    ProbabilityEstimateV1,
    TransitionReviewState,
    canonical_hash,
)
from core.engine.grounded_state.transition_contracts import (
    ConditionOperator,
    ObservedTransitionOutcomeV1,
    RuleEvaluationV1,
    StateConditionV1,
    StateSnapshotV1,
    TransitionBranchInputV1,
    TransitionCalibrationReceiptV1,
    TransitionChallengeReceiptV1,
    TransitionDerivationRoute,
    TransitionHypothesisProposalV1,
    TransitionHypothesisRevisionV1,
    TransitionOutcomeDisposition,
    TransitionReviewV1,
    TransitionRuleKind,
    _value_matches,
)


class TransitionResolutionError(ValueError):
    """Exact TP5 lineage or fail-closed policy was not satisfied."""


def _pack_refs(pack: BoundedEvidencePackV1) -> set[str]:
    return {item.endpoint.record_id for item in pack.items}


def _ensure_base_lineage(
    proposal: TransitionHypothesisProposalV1,
    projection: BeliefStateProjectionV1,
    evidence_pack: BoundedEvidencePackV1,
) -> None:
    if len({proposal.product_id, projection.product_id, evidence_pack.product_id}) != 1:
        raise TransitionResolutionError("transition material cannot cross product scope")
    if proposal.projection_id != projection.projection_id or proposal.projection_hash != projection.projection_hash:
        raise TransitionResolutionError("transition proposal must bind the exact frozen belief projection")
    if proposal.evidence_pack_id != evidence_pack.pack_id or proposal.evidence_pack_hash != evidence_pack.pack_hash:
        raise TransitionResolutionError("transition proposal must bind the exact frozen evidence pack")
    if projection.evidence_pack_id != evidence_pack.pack_id or projection.evidence_pack_hash != evidence_pack.pack_hash:
        raise TransitionResolutionError("belief projection and transition pack must share exact evidence material")
    if proposal.as_of != projection.as_of or proposal.as_of != evidence_pack.as_of:
        raise TransitionResolutionError("transition proposal, projection, and pack must share one as-of time")
    projection_entries = {str(entry.entry_id) for entry in projection.entries}
    if set(proposal.projection_entry_refs) - projection_entries:
        raise TransitionResolutionError("transition proposal references entries outside its frozen projection")
    if set(proposal.supporting_assertion_refs) - set(projection.evaluated_assertion_refs):
        raise TransitionResolutionError("transition proposal cites assertions outside its frozen projection")


def challenge_transition(
    proposal: TransitionHypothesisProposalV1,
    *,
    projection: BeliefStateProjectionV1,
    evidence_pack: BoundedEvidencePackV1,
    contrary_evidence_refs: tuple[str, ...] | list[str] | None = None,
) -> TransitionChallengeReceiptV1:
    """Challenge one proposal against every record in its exact frozen pack."""

    _ensure_base_lineage(proposal, projection, evidence_pack)
    searched = _pack_refs(evidence_pack)
    support = set(proposal.supporting_evidence_refs)
    contrary = set(proposal.contrary_evidence_refs) | set(contrary_evidence_refs or ())
    missing: list[str] = []
    if support - searched:
        missing.append("supporting_evidence_missing_from_pack")
    if contrary - searched:
        missing.append("contrary_evidence_missing_from_pack")
    if not support:
        missing.append("supporting_evidence_unavailable")
    if not proposal.supporting_assertion_refs:
        missing.append("supporting_assertion_unavailable")
    if proposal.causal_strength in {CausalStrength.MECHANISTIC, CausalStrength.CAUSAL} and not proposal.mechanism:
        missing.append("mechanism_unavailable")
    omissions = list(evidence_pack.omissions)
    fallbacks = list(evidence_pack.fallbacks)
    failures = list(evidence_pack.failures)
    degraded = list(evidence_pack.degraded_reasons)
    if evidence_pack.truncated:
        omissions.append("evidence_pack_truncated")
    completed = not (missing or omissions or fallbacks or failures or degraded)
    return TransitionChallengeReceiptV1(
        product_id=proposal.product_id,
        proposal_id=str(proposal.proposal_id),
        proposal_material_hash=proposal.review_material_hash(),
        hypothesis_id=proposal.hypothesis_id(),
        projection_id=str(projection.projection_id),
        projection_hash=str(projection.projection_hash),
        evidence_pack_id=str(evidence_pack.pack_id),
        evidence_pack_hash=str(evidence_pack.pack_hash),
        as_of=proposal.as_of,
        searched_evidence_refs=tuple(searched),
        supporting_evidence_refs=tuple(support & searched),
        contrary_evidence_refs=tuple(contrary & searched),
        missing_inputs=tuple(missing),
        max_records=evidence_pack.max_records,
        pack_selected_count=evidence_pack.selected_count,
        records_searched=len(searched),
        index_versions={
            "candidate_resolver": evidence_pack.resolver_policy_version,
            "belief_resolver": projection.resolver_policy_version,
            "transition_ontology": proposal.ontology_version,
        },
        completed=completed,
        omissions=tuple(omissions),
        fallbacks=tuple(fallbacks),
        failures=tuple(failures),
        degraded_reasons=tuple(degraded),
        provider_usage=evidence_pack.provider_usage,
    )


def review_transition(
    proposal: TransitionHypothesisProposalV1,
    challenge: TransitionChallengeReceiptV1,
    *,
    disposition: TransitionReviewState,
    authority: ReviewAuthority,
    reviewer_ref: str,
    reviewed_at: datetime,
    rationale: str,
) -> TransitionReviewV1:
    """Create an exact-material transition review after independent challenge."""

    if proposal.product_id != challenge.product_id:
        raise TransitionResolutionError("transition review cannot cross product scope")
    if proposal.proposal_id != challenge.proposal_id:
        raise TransitionResolutionError("transition review must use the proposal challenged")
    if proposal.review_material_hash() != challenge.proposal_material_hash:
        raise TransitionResolutionError("transition challenge does not bind exact proposal material")
    if proposal.hypothesis_id() != challenge.hypothesis_id:
        raise TransitionResolutionError("transition challenge binds another hypothesis")
    if disposition in {TransitionReviewState.ACCEPTED, TransitionReviewState.PROVISIONAL} and not challenge.completed:
        raise TransitionResolutionError("incomplete challenge cannot make a transition rollout-eligible")
    if disposition is TransitionReviewState.ACCEPTED and challenge.contrary_evidence_refs:
        raise TransitionResolutionError("a transition with visible contrary evidence cannot be accepted")
    if disposition is TransitionReviewState.CONTESTED and not challenge.contrary_evidence_refs:
        raise TransitionResolutionError("contested transition review requires contrary evidence")
    if disposition is TransitionReviewState.ACCEPTED and (
        proposal.causal_strength is CausalStrength.ASSOCIATIVE
        or set(proposal.derivation_routes) == {TransitionDerivationRoute.TEMPORAL_SEQUENCE}
    ):
        raise TransitionResolutionError("temporal association alone cannot earn accepted transition status")
    if proposal.causal_strength is CausalStrength.CAUSAL and disposition is TransitionReviewState.ACCEPTED:
        if authority is not ReviewAuthority.HUMAN:
            raise TransitionResolutionError("causal transition acceptance requires human authority")
    return TransitionReviewV1(
        product_id=proposal.product_id,
        proposal_id=str(proposal.proposal_id),
        hypothesis_id=proposal.hypothesis_id(),
        reviewed_material_hash=proposal.review_material_hash(),
        challenge_receipt_id=str(challenge.receipt_id),
        challenge_receipt_hash=str(challenge.receipt_hash),
        disposition=disposition,
        authority=authority,
        reviewer_ref=reviewer_ref,
        reviewed_at=reviewed_at,
        rationale=rationale,
        omissions=challenge.omissions,
        failures=challenge.failures,
        degraded_reasons=challenge.degraded_reasons,
    )


def resolve_transition(
    proposal: TransitionHypothesisProposalV1,
    challenge: TransitionChallengeReceiptV1,
    review: TransitionReviewV1,
    *,
    revision: int = 1,
    prior_revision: TransitionHypothesisRevisionV1 | None = None,
    created_at: datetime | None = None,
    superseded_revision_refs: tuple[str, ...] = (),
    stale_at: datetime | None = None,
) -> TransitionHypothesisRevisionV1:
    """Resolve one reviewed proposal into an append-only transition revision."""

    if len({proposal.product_id, challenge.product_id, review.product_id}) != 1:
        raise TransitionResolutionError("transition resolution cannot cross product scope")
    if proposal.proposal_id != challenge.proposal_id or proposal.proposal_id != review.proposal_id:
        raise TransitionResolutionError("transition resolution requires one exact proposal")
    if proposal.hypothesis_id() != challenge.hypothesis_id or proposal.hypothesis_id() != review.hypothesis_id:
        raise TransitionResolutionError("transition resolution requires one stable hypothesis")
    if proposal.review_material_hash() != challenge.proposal_material_hash:
        raise TransitionResolutionError("transition challenge does not bind exact proposal material")
    if proposal.review_material_hash() != review.reviewed_material_hash:
        raise TransitionResolutionError("transition review does not bind exact proposal material")
    if challenge.receipt_id != review.challenge_receipt_id or challenge.receipt_hash != review.challenge_receipt_hash:
        raise TransitionResolutionError("transition review does not bind exact challenge material")
    expected_revision = 1 if prior_revision is None else prior_revision.revision + 1
    if revision != expected_revision:
        raise TransitionResolutionError("transition revision must increment exact prior lineage")
    if prior_revision is not None:
        if prior_revision.product_id != proposal.product_id or prior_revision.hypothesis_id != proposal.hypothesis_id():
            raise TransitionResolutionError("transition revision cannot inherit foreign hypothesis material")

    degraded = set(proposal.degraded_reasons) | set(challenge.degraded_reasons) | set(review.degraded_reasons)
    if challenge.contrary_evidence_refs:
        degraded.add("contrary_evidence_present")
    if review.disposition is TransitionReviewState.STALE:
        degraded.add("transition_stale")
    omissions = set(proposal.omissions) | set(challenge.omissions) | set(review.omissions)
    failures = set(proposal.failures) | set(challenge.failures) | set(review.failures)
    eligible = (
        review.disposition in {TransitionReviewState.PROVISIONAL, TransitionReviewState.ACCEPTED}
        and proposal.causal_strength in {CausalStrength.MECHANISTIC, CausalStrength.CAUSAL}
        and challenge.completed
        and not challenge.contrary_evidence_refs
        and not omissions
        and not failures
        and not degraded
    )
    return TransitionHypothesisRevisionV1(
        hypothesis_id=proposal.hypothesis_id(),
        revision=revision,
        product_id=proposal.product_id,
        proposal_id=str(proposal.proposal_id),
        proposal_material_hash=proposal.review_material_hash(),
        projection_id=proposal.projection_id,
        projection_hash=proposal.projection_hash,
        projection_entry_refs=proposal.projection_entry_refs,
        evidence_pack_id=proposal.evidence_pack_id,
        evidence_pack_hash=proposal.evidence_pack_hash,
        as_of=proposal.as_of,
        source=proposal.source,
        target=proposal.target,
        trigger=proposal.trigger,
        mechanism=proposal.mechanism,
        rules=proposal.rules,
        delay_min_seconds=proposal.delay_min_seconds,
        delay_max_seconds=proposal.delay_max_seconds,
        probability=proposal.probability,
        causal_strength=proposal.causal_strength,
        derivation_routes=proposal.derivation_routes,
        supporting_evidence_refs=challenge.supporting_evidence_refs,
        contrary_evidence_refs=challenge.contrary_evidence_refs,
        supporting_assertion_refs=proposal.supporting_assertion_refs,
        supporting_evidence_origins=proposal.supporting_evidence_origins,
        challenge_receipt_id=str(challenge.receipt_id),
        challenge_receipt_hash=str(challenge.receipt_hash),
        challenge_completed=challenge.completed,
        review_id=str(review.review_id),
        review_state=review.disposition,
        review_authority=review.authority,
        rollout_eligible=eligible,
        ontology_version=proposal.ontology_version,
        resolver_policy_version=proposal.resolver_policy_version,
        prior_revision_id=str(prior_revision.revision_id) if prior_revision else None,
        superseded_revision_refs=superseded_revision_refs,
        stale_at=stale_at,
        created_at=created_at or review.reviewed_at,
        omissions=tuple(omissions),
        failures=tuple(failures),
        degraded_reasons=tuple(degraded),
        provider_usage=proposal.provider_usage,
    )


def _evaluate_condition(condition: StateConditionV1, actual: Any, *, present: bool) -> tuple[bool | None, str]:
    operator = condition.operator
    if operator is ConditionOperator.EXISTS:
        return present, "state variable is present" if present else "state variable is missing"
    if operator is ConditionOperator.ABSENT:
        return not present, "state variable is absent" if not present else "state variable is present"
    if not present:
        return None, "state variable is missing"
    if not _value_matches(actual, condition.variable.value_type):
        return None, "state variable type does not match the transition contract"
    expected = condition.value
    if operator is ConditionOperator.EQ:
        result = actual == expected
    elif operator is ConditionOperator.NE:
        result = actual != expected
    elif operator is ConditionOperator.GT:
        result = actual > expected
    elif operator is ConditionOperator.GTE:
        result = actual >= expected
    elif operator is ConditionOperator.LT:
        result = actual < expected
    elif operator is ConditionOperator.LTE:
        result = actual <= expected
    elif operator is ConditionOperator.IN:
        result = actual in expected
    elif operator is ConditionOperator.NOT_IN:
        result = actual not in expected
    else:  # pragma: no cover - enum exhaustiveness
        raise AssertionError(f"unsupported transition operator: {operator}")
    return result, "condition satisfied" if result else "condition not satisfied"


def build_transition_branch_input(
    projection: BeliefStateProjectionV1,
    revision: TransitionHypothesisRevisionV1,
) -> TransitionBranchInputV1:
    """Freeze deterministic, rule-evaluated TP6 branch inputs without simulating a future."""

    if projection.product_id != revision.product_id:
        raise TransitionResolutionError("transition branch input cannot cross product scope")
    if projection.projection_id != revision.projection_id or projection.projection_hash != revision.projection_hash:
        raise TransitionResolutionError("transition branch input requires the revision's exact starting projection")
    entries = {str(entry.entry_id): entry for entry in projection.entries}
    if set(revision.projection_entry_refs) - set(entries):
        raise TransitionResolutionError("transition revision references missing projection entries")
    relevant_variables = {
        (revision.source.variable.subject.record_id, revision.source.variable.predicate),
        *((rule.condition.variable.subject.record_id, rule.condition.variable.predicate) for rule in revision.rules),
    }
    snapshots: list[StateSnapshotV1] = []
    values: dict[tuple[str, str], Any] = {}
    for ref in revision.projection_entry_refs:
        entry = entries[ref]
        key = (entry.subject.record_id, entry.predicate)
        if key not in relevant_variables:
            continue
        snapshots.append(
            StateSnapshotV1(
                entry_id=str(entry.entry_id),
                subject=entry.subject,
                predicate=entry.predicate,
                value=entry.value,
                status=entry.status.value,
            )
        )
        if entry.operational:
            values[key] = entry.value

    evaluations: list[RuleEvaluationV1] = []
    source_key = (revision.source.variable.subject.record_id, revision.source.variable.predicate)
    source_present = source_key in values
    source_satisfied, source_reason = _evaluate_condition(
        revision.source,
        values.get(source_key),
        present=source_present,
    )
    evaluations.append(
        RuleEvaluationV1(
            rule_id=f"transition_source_condition:{canonical_hash(revision.source)[:32]}",
            kind=TransitionRuleKind.PRECONDITION,
            actual_value=values.get(source_key),
            satisfied=source_satisfied,
            reason=source_reason,
        )
    )
    blocked: list[str] = []
    missing: list[str] = []
    if source_satisfied is False:
        blocked.append("source_state_condition_not_satisfied")
    elif source_satisfied is None:
        missing.append("source_state_input_missing")

    for rule in revision.rules:
        key = (rule.condition.variable.subject.record_id, rule.condition.variable.predicate)
        present = key in values
        satisfied, reason = _evaluate_condition(rule.condition, values.get(key), present=present)
        evaluations.append(
            RuleEvaluationV1(
                rule_id=str(rule.rule_id),
                kind=rule.kind,
                actual_value=values.get(key),
                satisfied=satisfied,
                reason=reason,
            )
        )
        if satisfied is False:
            blocked.append(f"{rule.kind.value}_not_satisfied:{rule.rule_id}")
        elif satisfied is None:
            missing.append(f"{rule.kind.value}_input_missing:{rule.rule_id}")

    degraded = list(revision.degraded_reasons)
    if not revision.rollout_eligible:
        blocked.append("transition_revision_not_rollout_eligible")
    applicable = not (blocked or missing or degraded)
    return TransitionBranchInputV1(
        product_id=revision.product_id,
        hypothesis_id=revision.hypothesis_id,
        transition_revision_id=str(revision.revision_id),
        transition_revision_hash=str(revision.revision_hash),
        starting_projection_id=str(projection.projection_id),
        starting_projection_hash=str(projection.projection_hash),
        as_of=projection.as_of,
        state_snapshot=tuple(snapshots),
        rule_evaluations=tuple(evaluations),
        applicable=applicable,
        blocked_reasons=tuple(blocked),
        missing_inputs=tuple(missing),
        degraded_reasons=tuple(degraded),
    )


def calibrate_transition(
    revision: TransitionHypothesisRevisionV1,
    outcomes: list[ObservedTransitionOutcomeV1] | tuple[ObservedTransitionOutcomeV1, ...],
    *,
    calibrated_at: datetime,
) -> TransitionCalibrationReceiptV1:
    """Calibrate a revision from immutable later outcomes without rewriting it."""

    ordered = tuple(sorted(outcomes, key=lambda item: str(item.outcome_id)))
    for outcome in ordered:
        if outcome.product_id != revision.product_id:
            raise TransitionResolutionError("transition calibration cannot cross product scope")
        if outcome.hypothesis_id != revision.hypothesis_id:
            raise TransitionResolutionError("transition calibration outcome targets another hypothesis")
        if (
            outcome.transition_revision_id != revision.revision_id
            or outcome.transition_revision_hash != revision.revision_hash
        ):
            raise TransitionResolutionError("transition calibration must bind the exact immutable revision")
        if outcome.observed_at <= revision.as_of:
            raise TransitionResolutionError("transition calibration requires an outcome observed after the revision")
        if outcome.disposition in {
            TransitionOutcomeDisposition.MATCHED,
            TransitionOutcomeDisposition.CONTRADICTED,
        }:
            observed = outcome.observed_target
            if observed is None or observed.variable != revision.target.variable:
                raise TransitionResolutionError("resolved transition outcome must observe the exact target variable")
            target_matched = observed.value == revision.target.value
            if (outcome.disposition is TransitionOutcomeDisposition.MATCHED) != target_matched:
                raise TransitionResolutionError("transition outcome disposition does not match observed target value")
    matched = 0.0
    contradicted = 0.0
    unresolved = 0
    for outcome in ordered:
        if outcome.disposition is TransitionOutcomeDisposition.MATCHED:
            matched += 1.0
        elif outcome.disposition is TransitionOutcomeDisposition.CONTRADICTED:
            contradicted += 1.0
        elif outcome.disposition is TransitionOutcomeDisposition.MIXED:
            matched += 0.5
            contradicted += 0.5
        else:
            unresolved += 1
    resolved = matched + contradicted
    if resolved:
        expected = (1.0 + matched) / (2.0 + resolved)
        half_width = min(0.5, 1.0 / math.sqrt(resolved + 4.0))
        probability = ProbabilityEstimateV1(
            lower=max(0.0, expected - half_width),
            expected=expected,
            upper=min(1.0, expected + half_width),
        )
    else:
        probability = revision.probability
    return TransitionCalibrationReceiptV1(
        product_id=revision.product_id,
        hypothesis_id=revision.hypothesis_id,
        transition_revision_id=str(revision.revision_id),
        transition_revision_hash=str(revision.revision_hash),
        original_probability=revision.probability,
        outcome_refs=tuple(str(outcome.outcome_id) for outcome in ordered),
        matched_weight=matched,
        contradicted_weight=contradicted,
        unresolved_count=unresolved,
        calibrated_probability=probability,
        calibrated_at=calibrated_at,
    )


class TransitionHypothesisService:
    """TP5 orchestration over already-persisted TP4 starting material."""

    def __init__(self, pool) -> None:
        from core.engine.grounded_state.belief_persistence import BeliefStateStore
        from core.engine.grounded_state.transition_persistence import TransitionStore

        self.belief_store = BeliefStateStore(pool)
        self.transition_store = TransitionStore(pool)

    async def resolve_and_persist(
        self,
        proposal: TransitionHypothesisProposalV1,
        *,
        disposition: TransitionReviewState,
        authority: ReviewAuthority,
        reviewer_ref: str,
        reviewed_at: datetime,
        rationale: str,
        contrary_evidence_refs: tuple[str, ...] = (),
        prior_revision: TransitionHypothesisRevisionV1 | None = None,
        superseded_revision_refs: tuple[str, ...] = (),
        stale_at: datetime | None = None,
    ) -> TransitionHypothesisRevisionV1:
        """Validate exact TP4 lineage and atomically persist the complete TP5 chain."""

        projection = await self.belief_store.require(
            BeliefStateProjectionV1,
            proposal.projection_id,
            product_id=proposal.product_id,
        )
        evidence_pack = await self.belief_store.require(
            BoundedEvidencePackV1,
            proposal.evidence_pack_id,
            product_id=proposal.product_id,
        )
        if (
            projection.projection_hash != proposal.projection_hash
            or evidence_pack.pack_hash != proposal.evidence_pack_hash
        ):
            raise TransitionResolutionError("persisted TP4 lineage does not match transition proposal hashes")
        projected_assertion_ids: set[str] = set()
        for assertion_revision_ref in projection.assertion_revision_refs:
            assertion = await self.belief_store.require(
                EpistemicAssertionV1,
                assertion_revision_ref,
                product_id=proposal.product_id,
            )
            assertion_proposal = await self.belief_store.require(
                EpistemicAssertionProposalV1,
                assertion.proposal_id,
                product_id=proposal.product_id,
            )
            assertion_review = await self.belief_store.require(
                AssertionReviewV1,
                assertion.review_id,
                product_id=proposal.product_id,
            )
            if (
                assertion_proposal.assertion_id() != assertion.assertion_id
                or assertion_review.assertion_id != assertion.assertion_id
                or assertion_proposal.evidence_pack_id != proposal.evidence_pack_id
            ):
                raise TransitionResolutionError("persisted TP4 assertion lineage is incomplete or mismatched")
            projected_assertion_ids.add(assertion.assertion_id)
        if projected_assertion_ids != set(projection.evaluated_assertion_refs):
            raise TransitionResolutionError("persisted TP4 assertion revisions do not reconcile the projection")
        if prior_revision is not None:
            persisted_prior = await self.transition_store.require(
                TransitionHypothesisRevisionV1,
                str(prior_revision.revision_id),
                product_id=proposal.product_id,
            )
            if persisted_prior != prior_revision:
                raise TransitionResolutionError("transition revision must extend exact persisted prior lineage")
        challenge = challenge_transition(
            proposal,
            projection=projection,
            evidence_pack=evidence_pack,
            contrary_evidence_refs=contrary_evidence_refs,
        )
        review = review_transition(
            proposal,
            challenge,
            disposition=disposition,
            authority=authority,
            reviewer_ref=reviewer_ref,
            reviewed_at=reviewed_at,
            rationale=rationale,
        )
        revision = resolve_transition(
            proposal,
            challenge,
            review,
            revision=1 if prior_revision is None else prior_revision.revision + 1,
            prior_revision=prior_revision,
            superseded_revision_refs=superseded_revision_refs,
            stale_at=stale_at,
        )
        await self.transition_store.persist_all((proposal, challenge, review, revision))
        return revision

    async def replay_revision(
        self,
        revision_id: str,
        *,
        product_id: str,
    ) -> TransitionHypothesisRevisionV1:
        """Rebuild one exact transition revision from its persisted lineage."""

        from core.engine.grounded_state.transition_persistence import TransitionProductScopeError

        revision = await self.transition_store.require(
            TransitionHypothesisRevisionV1,
            revision_id,
            product_id=product_id,
        )
        proposal = await self.transition_store.require(
            TransitionHypothesisProposalV1,
            revision.proposal_id,
            product_id=product_id,
        )
        challenge = await self.transition_store.require(
            TransitionChallengeReceiptV1,
            revision.challenge_receipt_id,
            product_id=product_id,
        )
        review = await self.transition_store.require(
            TransitionReviewV1,
            revision.review_id,
            product_id=product_id,
        )
        prior = None
        if revision.prior_revision_id is not None:
            prior = await self.transition_store.require(
                TransitionHypothesisRevisionV1,
                revision.prior_revision_id,
                product_id=product_id,
            )
        replayed = resolve_transition(
            proposal,
            challenge,
            review,
            revision=revision.revision,
            prior_revision=prior,
            created_at=revision.created_at,
            superseded_revision_refs=revision.superseded_revision_refs,
            stale_at=revision.stale_at,
        )
        if replayed != revision:
            raise TransitionProductScopeError("persisted TP5 revision does not reproduce from exact lineage")
        return replayed

    async def freeze_branch_input(
        self,
        revision_id: str,
        *,
        product_id: str,
    ) -> TransitionBranchInputV1:
        revision = await self.replay_revision(revision_id, product_id=product_id)
        projection = await self.belief_store.require(
            BeliefStateProjectionV1,
            revision.projection_id,
            product_id=product_id,
        )
        branch_input = build_transition_branch_input(projection, revision)
        await self.transition_store.persist(branch_input)
        return branch_input

    async def record_outcome_and_calibrate(
        self,
        outcome: ObservedTransitionOutcomeV1,
        *,
        calibrated_at: datetime,
    ) -> TransitionCalibrationReceiptV1:
        revision = await self.replay_revision(
            outcome.transition_revision_id,
            product_id=outcome.product_id,
        )
        if (
            outcome.transition_revision_hash != revision.revision_hash
            or outcome.hypothesis_id != revision.hypothesis_id
        ):
            raise TransitionResolutionError("transition outcome does not bind the exact immutable revision")
        evidence_pack = await self.belief_store.require(
            BoundedEvidencePackV1,
            outcome.evidence_pack_id,
            product_id=outcome.product_id,
        )
        if outcome.evidence_pack_hash != evidence_pack.pack_hash:
            raise TransitionResolutionError("transition outcome does not bind the exact observed evidence pack")
        if evidence_pack.as_of <= revision.as_of or evidence_pack.as_of > outcome.observed_at:
            raise TransitionResolutionError(
                "transition outcome requires a post-revision evidence pack frozen no later than observation"
            )
        if set(outcome.evidence_refs) - _pack_refs(evidence_pack):
            raise TransitionResolutionError("transition outcome cites evidence outside its frozen pack")
        await self.transition_store.persist(outcome)
        outcomes = await self.transition_store.list_outcomes(
            product_id=outcome.product_id,
            transition_revision_id=outcome.transition_revision_id,
        )
        receipt = calibrate_transition(revision, outcomes, calibrated_at=calibrated_at)
        await self.transition_store.persist(receipt)
        return receipt
