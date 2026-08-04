"""Provider-free TP6 consequence execution, challenge, use, and reconciliation."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable

from core.engine.grounded_state.belief_contracts import (
    BeliefStateProjectionV1,
    BoundedEvidencePackV1,
    ReviewAuthority,
)
from core.engine.grounded_state.contracts import (
    ConsequenceRolloutRequestV1,
    ProbabilityEstimateV1,
    RolloutBranchKind,
    canonical_hash,
)
from core.engine.grounded_state.rollout_contracts import (
    MAX_ROLLOUT_HORIZON_SECONDS,
    BranchAssumptionV1,
    BranchConstraintV1,
    ConsequenceRolloutRevisionV1,
    EvidenceCoverageState,
    FalsifiableOutcomeV1,
    PredictedConsequenceV1,
    PredictedStateStepV1,
    ReasoningContextUseReceiptV1,
    ReasoningEvidencePackV1,
    ReasoningUseItemV1,
    RolloutChallengeReceiptV1,
    RolloutDerivationRoute,
    RolloutDisposition,
    RolloutOutcomeDisposition,
    RolloutOutcomeObservationV1,
    RolloutProposalV1,
    RolloutReconciliationReceiptV1,
    StateAssignmentV1,
    StateSnapshotV1,
    TransitionExecutionReceiptV1,
)
from core.engine.grounded_state.transition_contracts import TransitionHypothesisRevisionV1
from core.engine.grounded_state.transitions import build_transition_branch_input


class ConsequenceRolloutError(ValueError):
    """TP6 exact lineage, comparability, or bounded execution failed closed."""


def _projection_snapshot(projection: BeliefStateProjectionV1) -> tuple[StateSnapshotV1, ...]:
    return tuple(
        StateSnapshotV1(
            entry_id=str(entry.entry_id),
            subject=entry.subject,
            predicate=entry.predicate,
            value=entry.value,
            status=entry.status.value,
        )
        for entry in projection.entries
    )


def _ensure_lineage(
    request: ConsequenceRolloutRequestV1,
    *,
    projection: BeliefStateProjectionV1,
    context_pack: ReasoningEvidencePackV1,
    revisions: tuple[TransitionHypothesisRevisionV1, ...],
) -> None:
    evidence_pack = context_pack.evidence_pack
    if (request.horizon - request.as_of).total_seconds() > MAX_ROLLOUT_HORIZON_SECONDS:
        raise ConsequenceRolloutError("rollout horizon exceeds the TP6 v1 deterministic bound")
    if len({request.product_id, projection.product_id, context_pack.product_id, evidence_pack.product_id}) != 1:
        raise ConsequenceRolloutError("rollout material cannot cross product scope")
    if (
        request.starting_state_id != projection.projection_id
        or request.starting_state_hash != projection.projection_hash
    ):
        raise ConsequenceRolloutError("rollout request must bind one exact frozen TP4 starting projection")
    if request.evidence_pack_id != evidence_pack.pack_id or request.evidence_pack_hash != evidence_pack.pack_hash:
        raise ConsequenceRolloutError("rollout request must bind the exact TP3/TP4 evidence pack")
    if projection.evidence_pack_id != evidence_pack.pack_id or projection.evidence_pack_hash != evidence_pack.pack_hash:
        raise ConsequenceRolloutError("starting projection and reasoning pack must share exact evidence material")
    if request.as_of != projection.as_of or request.as_of != evidence_pack.as_of:
        raise ConsequenceRolloutError("rollout request, projection, and evidence pack must share one frozen as-of time")
    for revision in revisions:
        if revision.product_id != request.product_id:
            raise ConsequenceRolloutError("transition revision cannot cross rollout product scope")
        if revision.projection_id != projection.projection_id or revision.projection_hash != projection.projection_hash:
            raise ConsequenceRolloutError("transition revision must bind the exact rollout starting projection")
        if revision.evidence_pack_id != evidence_pack.pack_id or revision.evidence_pack_hash != evidence_pack.pack_hash:
            raise ConsequenceRolloutError("transition revision must bind the rollout evidence pack")
        if revision.as_of != request.as_of:
            raise ConsequenceRolloutError("transition revision must share the rollout as-of time")
    available = {revision.hypothesis_id for revision in revisions} | {
        str(revision.revision_id) for revision in revisions
    }
    declared = {transition_ref for branch in request.branches for transition_ref in branch.transition_hypothesis_ids}
    if declared - available:
        raise ConsequenceRolloutError("rollout branch names unavailable transition material")


def build_rollout_proposal(
    *,
    task_id: str,
    invocation_id: str,
    request: ConsequenceRolloutRequestV1,
    projection: BeliefStateProjectionV1,
    context_pack: ReasoningEvidencePackV1,
    revisions: Iterable[TransitionHypothesisRevisionV1],
    assumptions: Iterable[BranchAssumptionV1] = (),
    constraints: Iterable[BranchConstraintV1] = (),
) -> RolloutProposalV1:
    """Freeze exact TP4/TP5/context inputs before executing any future state."""
    ordered = tuple(sorted(revisions, key=lambda item: str(item.revision_id)))
    _ensure_lineage(request, projection=projection, context_pack=context_pack, revisions=ordered)
    if task_id != context_pack.task_id or invocation_id != context_pack.invocation_id:
        raise ConsequenceRolloutError("rollout proposal must retain exact task and invocation context")
    return RolloutProposalV1(
        product_id=request.product_id,
        task_id=task_id,
        invocation_id=invocation_id,
        context_pack_id=str(context_pack.context_pack_id),
        context_pack_hash=str(context_pack.context_pack_hash),
        request=request,
        transition_revision_ids=tuple(str(item.revision_id) for item in ordered),
        transition_revision_hashes={str(item.revision_id): str(item.revision_hash) for item in ordered},
        assumptions=tuple(assumptions),
        constraints=tuple(constraints),
        ontology_version=projection.ontology_version,
        resolver_policy_version=projection.resolver_policy_version,
    )


def _branch_revisions(
    branch,
    revisions: tuple[TransitionHypothesisRevisionV1, ...],
) -> tuple[TransitionHypothesisRevisionV1, ...]:
    declared = set(branch.transition_hypothesis_ids)
    return tuple(item for item in revisions if item.hypothesis_id in declared or str(item.revision_id) in declared)


def _current_assignment(
    projection: BeliefStateProjectionV1,
    revision: TransitionHypothesisRevisionV1,
) -> StateAssignmentV1 | None:
    variable = revision.source.variable
    for entry in projection.entries:
        if (
            entry.operational
            and entry.subject.record_id == variable.subject.record_id
            and entry.predicate == variable.predicate
        ):
            try:
                return StateAssignmentV1(variable=variable, value=entry.value)
            except ValueError:
                return None
    return None


def _initial_step(
    *,
    branch_id: str,
    branch_kind: RolloutBranchKind,
    projection: BeliefStateProjectionV1,
) -> PredictedStateStepV1:
    route = (
        RolloutDerivationRoute.NO_ACTION_BASELINE
        if branch_kind is RolloutBranchKind.NO_ACTION
        else RolloutDerivationRoute.DETERMINISTIC_TRANSITION
    )
    return PredictedStateStepV1(
        branch_id=branch_id,
        ordinal=0,
        predicted_at=projection.as_of,
        starting_projection_id=str(projection.projection_id),
        starting_projection_hash=str(projection.projection_hash),
        state_snapshot=_projection_snapshot(projection),
        probability=ProbabilityEstimateV1(lower=1.0, expected=1.0, upper=1.0),
        derivation_route=route,
        evidence_refs=tuple(sorted({ref for entry in projection.entries for ref in entry.supporting_evidence_refs})),
        belief_entry_refs=tuple(str(entry.entry_id) for entry in projection.entries),
        uncertainty_reasons=tuple(
            sorted({reason for entry in projection.entries for reason in entry.degraded_reasons})
        ),
    )


def execute_rollout_branch(
    proposal: RolloutProposalV1,
    *,
    branch_id: str,
    projection: BeliefStateProjectionV1,
    context_pack: ReasoningEvidencePackV1,
    revisions: Iterable[TransitionHypothesisRevisionV1],
    max_steps: int = 8,
    max_transitions: int = 8,
) -> TransitionExecutionReceiptV1:
    """Apply explicit eligible TP5 revisions in deterministic identity order."""
    if not 1 <= max_steps <= 32 or not 1 <= max_transitions <= 16:
        raise ConsequenceRolloutError("rollout execution bounds exceed TP6 v1")
    request = proposal.request
    branch = next((item for item in request.branches if item.branch_id == branch_id), None)
    if branch is None:
        raise ConsequenceRolloutError("rollout branch is not declared in the frozen request")
    ordered = tuple(sorted(revisions, key=lambda item: str(item.revision_id)))
    _ensure_lineage(request, projection=projection, context_pack=context_pack, revisions=ordered)
    selected = _branch_revisions(branch, ordered)
    if branch.kind is not RolloutBranchKind.NO_ACTION and not selected:
        raise ConsequenceRolloutError("action and named-alternative branches require an explicit transition revision")

    assumptions = tuple(item for item in proposal.assumptions if item.branch_id == branch.branch_id)
    constraints = tuple(item for item in proposal.constraints if item.branch_id == branch.branch_id)
    constraint_failures = [str(item.constraint_id) for item in constraints if item.satisfied is not True]
    steps = [_initial_step(branch_id=branch.branch_id, branch_kind=branch.kind, projection=projection)]
    consequences: list[PredictedConsequenceV1] = []
    applicable: list[str] = []
    blocked: list[str] = []
    missing: list[str] = []
    omissions: list[str] = []
    failures: list[str] = []
    degraded: list[str] = []

    if branch.kind is RolloutBranchKind.NO_ACTION:
        if ordered:
            baseline = _current_assignment(projection, ordered[0])
            if baseline is None:
                missing.append("no_action_baseline_value_unavailable")
            else:
                outcome = FalsifiableOutcomeV1(
                    branch_id=branch.branch_id,
                    indicator=f"Observe {baseline.variable.predicate} without the declared action.",
                    expected_assignment=baseline,
                    earliest_at=request.as_of,
                    latest_at=request.horizon,
                    evidence_required=("post_rollout_observation",),
                )
                consequences.append(
                    PredictedConsequenceV1(
                        branch_id=branch.branch_id,
                        description=f"No-action baseline retains {baseline.variable.predicate}={baseline.value!r}.",
                        predicted_state_ref=str(steps[0].simulated_state_id),
                        probability=ProbabilityEstimateV1(lower=1.0, expected=1.0, upper=1.0),
                        evidence_refs=steps[0].evidence_refs,
                        belief_entry_refs=steps[0].belief_entry_refs,
                        assumption_refs=tuple(str(item.assumption_id) for item in assumptions),
                        derivation_route=RolloutDerivationRoute.NO_ACTION_BASELINE,
                        falsifiable_outcome=outcome,
                    )
                )
    else:
        if len(selected) > max_transitions:
            omissions.append("transition_bound")
            selected = selected[:max_transitions]
        for revision in selected:
            revision_ref = str(revision.revision_id)
            branch_input = build_transition_branch_input(projection, revision)
            if constraint_failures:
                blocked.append(revision_ref)
                continue
            if not branch_input.applicable:
                blocked.append(revision_ref)
                missing.extend(branch_input.missing_inputs)
                degraded.extend(branch_input.degraded_reasons)
                continue
            predicted_at = request.as_of + timedelta(seconds=revision.delay_max_seconds)
            if predicted_at > request.horizon:
                blocked.append(revision_ref)
                degraded.append(f"transition_outside_horizon:{revision_ref}")
                continue
            if len(steps) >= max_steps:
                omissions.append("step_bound")
                break
            applicable.append(revision_ref)
            step = PredictedStateStepV1(
                branch_id=branch.branch_id,
                ordinal=len(steps),
                predicted_at=predicted_at,
                starting_projection_id=str(projection.projection_id),
                starting_projection_hash=str(projection.projection_hash),
                prior_simulated_state_id=str(steps[-1].simulated_state_id),
                transition_revision_id=revision_ref,
                transition_revision_hash=str(revision.revision_hash),
                assignment=revision.target,
                state_snapshot=_projection_snapshot(projection),
                probability=revision.probability,
                derivation_route=RolloutDerivationRoute.DETERMINISTIC_TRANSITION,
                evidence_refs=revision.supporting_evidence_refs,
                belief_entry_refs=revision.projection_entry_refs,
                assumption_refs=tuple(str(item.assumption_id) for item in assumptions),
                uncertainty_reasons=(
                    *revision.degraded_reasons,
                    *(
                        ("transition_probability_interval",)
                        if revision.probability.lower != revision.probability.upper
                        else ()
                    ),
                ),
            )
            steps.append(step)
            outcome = FalsifiableOutcomeV1(
                branch_id=branch.branch_id,
                indicator=(
                    f"Observe {revision.target.variable.predicate}={revision.target.value!r} "
                    f"after {revision.delay_min_seconds}–{revision.delay_max_seconds} seconds."
                ),
                expected_assignment=revision.target,
                earliest_at=request.as_of + timedelta(seconds=revision.delay_min_seconds),
                latest_at=predicted_at,
                evidence_required=revision.supporting_evidence_refs,
            )
            consequences.append(
                PredictedConsequenceV1(
                    branch_id=branch.branch_id,
                    description=(
                        f"Conditional on branch {branch.branch_id}, predict "
                        f"{revision.target.variable.predicate}={revision.target.value!r}."
                    ),
                    predicted_state_ref=str(step.simulated_state_id),
                    probability=revision.probability,
                    evidence_refs=revision.supporting_evidence_refs,
                    belief_entry_refs=revision.projection_entry_refs,
                    transition_revision_refs=(revision_ref,),
                    assumption_refs=tuple(str(item.assumption_id) for item in assumptions),
                    derivation_route=RolloutDerivationRoute.DETERMINISTIC_TRANSITION,
                    falsifiable_outcome=outcome,
                )
            )

    return TransitionExecutionReceiptV1(
        product_id=proposal.product_id,
        proposal_id=str(proposal.proposal_id),
        proposal_hash=str(proposal.proposal_hash),
        branch_id=branch.branch_id,
        branch_kind=branch.kind,
        starting_projection_id=str(projection.projection_id),
        starting_projection_hash=str(projection.projection_hash),
        as_of=request.as_of,
        horizon=request.horizon,
        applicable_transition_refs=tuple(applicable),
        blocked_transition_refs=tuple(blocked),
        transition_revision_hashes={str(item.revision_id): str(item.revision_hash) for item in selected},
        missing_inputs=tuple(missing),
        constraint_failures=tuple(constraint_failures),
        steps=tuple(steps),
        consequences=tuple(consequences),
        omissions=tuple(omissions),
        failures=tuple(failures),
        degraded_reasons=tuple(degraded),
    )


def execute_rollout(
    proposal: RolloutProposalV1,
    *,
    projection: BeliefStateProjectionV1,
    context_pack: ReasoningEvidencePackV1,
    revisions: Iterable[TransitionHypothesisRevisionV1],
    max_steps: int = 8,
    max_transitions: int = 8,
) -> tuple[TransitionExecutionReceiptV1, ...]:
    """Execute all branches against one exact start, independent of input order."""
    ordered = tuple(sorted(revisions, key=lambda item: str(item.revision_id)))
    _ensure_lineage(proposal.request, projection=projection, context_pack=context_pack, revisions=ordered)
    return tuple(
        execute_rollout_branch(
            proposal,
            branch_id=branch.branch_id,
            projection=projection,
            context_pack=context_pack,
            revisions=ordered,
            max_steps=max_steps,
            max_transitions=max_transitions,
        )
        for branch in proposal.request.branches
    )


def challenge_rollout(
    proposal: RolloutProposalV1,
    *,
    context_pack: ReasoningEvidencePackV1,
    executions: Iterable[TransitionExecutionReceiptV1],
    revisions: Iterable[TransitionHypothesisRevisionV1],
    challenged_at: datetime,
    challenger_ref: str = "policy:tp6-independent-challenge",
) -> RolloutChallengeReceiptV1:
    """Run the mandatory independent fail-closed TP6 challenge."""
    ordered_executions = tuple(sorted(executions, key=lambda item: item.branch_id))
    ordered_revisions = tuple(sorted(revisions, key=lambda item: str(item.revision_id)))
    request = proposal.request
    starts = {
        (item.starting_projection_id, item.starting_projection_hash, item.as_of, item.horizon)
        for item in ordered_executions
    }
    branch_kinds = {item.branch_kind for item in ordered_executions}
    all_steps = [step for execution in ordered_executions for step in execution.steps]
    all_consequences = [item for execution in ordered_executions for item in execution.consequences]
    assumptions = {str(item.assumption_id): item for item in proposal.assumptions}
    unsupported = tuple(key for key, item in assumptions.items() if not item.supported)
    challenged_states = {
        EvidenceCoverageState.CONTESTED,
        EvidenceCoverageState.STALE,
        EvidenceCoverageState.SUPERSEDED,
        EvidenceCoverageState.REJECTED,
        EvidenceCoverageState.UNKNOWN,
        EvidenceCoverageState.MISSING,
        EvidenceCoverageState.TRUNCATED,
    }
    counterevidence = tuple(
        sorted({ref for item in context_pack.coverage if item.state in challenged_states for ref in item.evidence_refs})
    )
    omissions = tuple(
        sorted(
            {
                *context_pack.omissions,
                *(reason for item in ordered_executions for reason in item.omissions),
            }
        )
    )
    failures = tuple(
        sorted(
            {
                *context_pack.failures,
                *(reason for item in ordered_executions for reason in item.failures),
            }
        )
    )
    degraded = tuple(
        sorted(
            {
                *context_pack.degraded_reasons,
                *(reason for item in ordered_executions for reason in item.degraded_reasons),
                *(("challenged_evidence_present",) if counterevidence else ()),
            }
        )
    )
    missing = tuple(
        sorted(
            {
                *request.unavailable_inputs,
                *(reason for item in ordered_executions for reason in item.missing_inputs),
            }
        )
    )
    checks = {
        "complete_starting_lineage": len(starts) == 1 and bool(ordered_executions),
        "unsupported_assumptions_absent": not unsupported,
        "contrary_or_degraded_evidence_absent": not counterevidence,
        "action_no_action_comparable": (
            RolloutBranchKind.NO_ACTION in branch_kinds
            and any(kind is not RolloutBranchKind.NO_ACTION for kind in branch_kinds)
            and len(starts) == 1
        ),
        "causal_overstatement_absent": all(item.record_meaning == "simulated_consequence" for item in all_consequences),
        "domain_assignments_valid": all(
            step.assignment is None or step.assignment.variable.subject.product_id == proposal.product_id
            for step in all_steps
        ),
        "constraints_satisfied": not any(item.constraint_failures for item in ordered_executions),
        "horizon_unambiguous": all(step.predicted_at <= request.horizon for step in all_steps),
        "omissions_absent": not omissions,
        "source_instructions_non_authoritative": (
            context_pack.source_instruction_authority is False and context_pack.execution_authority is False
        ),
        "product_scope_preserved": all(
            step.assignment is None or step.assignment.variable.subject.product_id == proposal.product_id
            for step in all_steps
        ),
        "policy_inputs_available": all(
            (
                proposal.ontology_version,
                proposal.resolver_policy_version,
                proposal.rollout_policy_version,
                context_pack.evidence_pack.ontology_version,
                context_pack.evidence_pack.resolver_policy_version,
            )
        ),
        "transition_lineage_complete": {str(item.revision_id): str(item.revision_hash) for item in ordered_revisions}
        == proposal.transition_revision_hashes,
    }
    completed = all(checks.values()) and not any((unsupported, missing, omissions, failures, degraded))
    return RolloutChallengeReceiptV1(
        product_id=proposal.product_id,
        proposal_id=str(proposal.proposal_id),
        proposal_hash=str(proposal.proposal_hash),
        context_pack_id=str(context_pack.context_pack_id),
        context_pack_hash=str(context_pack.context_pack_hash),
        execution_receipt_refs=tuple(str(item.receipt_id) for item in ordered_executions),
        checked_transition_refs=tuple(str(item.revision_id) for item in ordered_revisions),
        checks=checks,
        counterevidence_refs=counterevidence,
        unsupported_assumption_refs=unsupported,
        missing_inputs=missing,
        omissions=omissions,
        failures=failures,
        degraded_reasons=degraded,
        completed=completed,
        independent_authority=ReviewAuthority.DETERMINISTIC_POLICY,
        challenger_ref=challenger_ref,
        challenged_at=challenged_at,
    )


def finalize_rollout(
    proposal: RolloutProposalV1,
    *,
    executions: Iterable[TransitionExecutionReceiptV1],
    challenge: RolloutChallengeReceiptV1,
    prior_revision: ConsequenceRolloutRevisionV1 | None = None,
) -> ConsequenceRolloutRevisionV1:
    """Create one append-only final synthesis without rewriting earlier material."""
    ordered = tuple(sorted(executions, key=lambda item: item.branch_id))
    if challenge.proposal_id != proposal.proposal_id or challenge.proposal_hash != proposal.proposal_hash:
        raise ConsequenceRolloutError("rollout finalization requires the exact independently challenged proposal")
    if set(challenge.execution_receipt_refs) != {str(item.receipt_id) for item in ordered}:
        raise ConsequenceRolloutError("rollout challenge must account for every branch execution")
    problems = {
        *challenge.omissions,
        *challenge.failures,
        *challenge.degraded_reasons,
        *challenge.missing_inputs,
        *(reason for item in ordered for reason in item.constraint_failures),
    }
    if challenge.completed and not problems:
        disposition = RolloutDisposition.ELIGIBLE
    elif ordered:
        disposition = RolloutDisposition.DEGRADED
    else:
        disposition = RolloutDisposition.BLOCKED
    branch_summary = "; ".join(
        f"{item.branch_id} ({item.branch_kind.value}): {len(item.consequences)} consequence(s), "
        f"{len(item.blocked_transition_refs)} blocked transition(s)"
        for item in ordered
    )
    synthesis = (
        f"Bounded simulated comparison only; not an observation or belief. {branch_summary}. "
        f"Independent challenge: {'complete' if challenge.completed else 'incomplete'}."
    )
    return ConsequenceRolloutRevisionV1(
        rollout_id=proposal.request.rollout_id(),
        revision=1 if prior_revision is None else prior_revision.revision + 1,
        prior_revision_id=str(prior_revision.rollout_revision_id) if prior_revision else None,
        product_id=proposal.product_id,
        task_id=proposal.task_id,
        invocation_id=proposal.invocation_id,
        proposal_id=str(proposal.proposal_id),
        proposal_hash=str(proposal.proposal_hash),
        context_pack_id=proposal.context_pack_id,
        context_pack_hash=proposal.context_pack_hash,
        starting_projection_id=proposal.request.starting_state_id,
        starting_projection_hash=proposal.request.starting_state_hash,
        as_of=proposal.request.as_of,
        horizon=proposal.request.horizon,
        transition_revision_ids=proposal.transition_revision_ids,
        transition_revision_hashes=proposal.transition_revision_hashes,
        execution_receipts=ordered,
        challenge_receipt_id=str(challenge.receipt_id),
        challenge_receipt_hash=str(challenge.receipt_hash),
        challenge_completed=challenge.completed,
        disposition=disposition,
        final_synthesis=synthesis,
        ontology_version=proposal.ontology_version,
        resolver_policy_version=proposal.resolver_policy_version,
        rollout_policy_version=proposal.rollout_policy_version,
        challenge_policy_version=challenge.policy_version,
        omissions=challenge.omissions,
        failures=challenge.failures,
        degraded_reasons=tuple(sorted(problems)),
    )


def build_reasoning_use_receipt(
    rollout: ConsequenceRolloutRevisionV1,
    *,
    context_pack: ReasoningEvidencePackV1,
    reflected_item_ids: Iterable[str] = (),
    matched_control: dict[str, Any] | None = None,
) -> ReasoningContextUseReceiptV1:
    """Project exact I3 use states; credit materiality only for a matched pair."""
    reflected = set(reflected_item_ids)
    item_material: list[tuple[str, str, str]] = []
    item_material.extend(
        (item.endpoint.record_id, "evidence", item.endpoint.content_hash) for item in context_pack.evidence_pack.items
    )
    for execution in rollout.execution_receipts:
        item_material.append((execution.branch_id, "branch", str(execution.receipt_hash)))
        for step in execution.steps:
            for ref in step.belief_entry_refs:
                item_material.append((ref, "belief", canonical_hash(ref)))
            for ref in step.assumption_refs:
                item_material.append((ref, "assumption", canonical_hash(ref)))
            if step.transition_revision_id:
                item_material.append((step.transition_revision_id, "transition", str(step.transition_revision_hash)))
        for consequence in execution.consequences:
            item_material.append((str(consequence.consequence_id), "consequence", canonical_hash(consequence)))
    unique = {(item_id, item_type): digest for item_id, item_type, digest in item_material}
    control = matched_control if isinstance(matched_control, dict) else None
    comparison_state = str(control.get("state")) if control else "unknown"
    if comparison_state not in {"matched", "unknown", "unmatched", "failed"}:
        comparison_state = "failed"
    changed = tuple(sorted(set(control.get("changed_decision_fields") or ()))) if control else ()
    required_matches = {"task_hash", "provider", "model", "configuration", "decision_schema", "toolset"}
    matched_dimensions = set(control.get("matched_dimensions") or ()) if control else set()
    treatment_hash = control.get("treatment_output_hash") if control else None
    control_hash = control.get("control_output_hash") if control else None
    material_comparison = bool(
        control
        and comparison_state == "matched"
        and control.get("comparison_id")
        and required_matches <= matched_dimensions
        and treatment_hash
        and control_hash
        and treatment_hash != control_hash
        and changed
    )
    material_ids = set(control.get("material_item_ids") or ()) if material_comparison else set()
    items = tuple(
        ReasoningUseItemV1(
            item_id=item_id,
            item_type=item_type,
            content_hash=digest,
            retrieved=True,
            injected=True,
            reflected=item_id in reflected,
            decision_material=item_id in material_ids and item_id in reflected and bool(changed),
            changed_fields=changed if item_id in material_ids and item_id in reflected else (),
            non_credit_reasons=(
                ()
                if item_id in material_ids and item_id in reflected and changed
                else ("matched_material_use_not_established",)
            ),
        )
        for (item_id, item_type), digest in sorted(unique.items())
    )
    return ReasoningContextUseReceiptV1(
        product_id=rollout.product_id,
        task_id=rollout.task_id,
        invocation_id=rollout.invocation_id,
        rollout_revision_id=str(rollout.rollout_revision_id),
        rollout_revision_hash=str(rollout.rollout_revision_hash),
        context_pack_id=context_pack.context_pack_id,
        context_pack_hash=context_pack.context_pack_hash,
        items=items,
        comparison_state=comparison_state,
        comparison_id=str(control.get("comparison_id")) if control and control.get("comparison_id") else None,
        matched_dimensions=tuple(control.get("matched_dimensions") or ()) if control else (),
        treatment_output_hash=treatment_hash,
        control_output_hash=control_hash,
        changed_decision_fields=changed,
        degraded_reasons=(
            ()
            if material_comparison
            else (
                "matched_no_rollout_control_not_executed"
                if control is None
                else "matched_control_materiality_not_established",
            )
        ),
    )


def reconcile_rollout_outcome(
    rollout: ConsequenceRolloutRevisionV1,
    observation: RolloutOutcomeObservationV1,
    *,
    observed_evidence_pack: BoundedEvidencePackV1,
    reconciled_at: datetime,
) -> RolloutReconciliationReceiptV1:
    """Score one compatible later outcome without mutating its rollout revision."""
    if observation.product_id != rollout.product_id or observed_evidence_pack.product_id != rollout.product_id:
        raise ConsequenceRolloutError("rollout outcome reconciliation cannot cross product scope")
    if (
        observation.rollout_revision_id != rollout.rollout_revision_id
        or observation.rollout_revision_hash != rollout.rollout_revision_hash
    ):
        raise ConsequenceRolloutError("rollout outcome must bind the exact immutable rollout revision")
    if (
        observation.evidence_pack_id != observed_evidence_pack.pack_id
        or observation.evidence_pack_hash != observed_evidence_pack.pack_hash
    ):
        raise ConsequenceRolloutError("rollout outcome must bind one exact post-rollout evidence pack")
    if observed_evidence_pack.as_of <= rollout.as_of or observed_evidence_pack.as_of > observation.observed_at:
        raise ConsequenceRolloutError(
            "rollout outcome requires a post-rollout evidence pack frozen no later than observation"
        )
    pack_refs = {item.endpoint.record_id for item in observed_evidence_pack.items}
    if set(observation.evidence_refs) - pack_refs:
        raise ConsequenceRolloutError("rollout outcome cites evidence outside its frozen observed pack")
    outcomes = {
        str(item.falsifiable_outcome.outcome_id): item.falsifiable_outcome
        for execution in rollout.execution_receipts
        for item in execution.consequences
    }
    predicted = outcomes.get(observation.predicted_outcome_id)
    if predicted is None:
        raise ConsequenceRolloutError("rollout outcome names an unavailable predicted outcome")
    compatible_branch = predicted.branch_id == observation.branch_id
    compatible_horizon = predicted.earliest_at <= observation.observed_at <= predicted.latest_at
    degraded: list[str] = []
    if not compatible_branch:
        degraded.append("incompatible_branch")
    if not compatible_horizon:
        degraded.append("incompatible_horizon")
    assignments = (
        *((observation.observed_assignment,) if observation.observed_assignment is not None else ()),
        *observation.observed_assignment_samples,
    )
    if not (compatible_branch and compatible_horizon) or not assignments:
        disposition = RolloutOutcomeDisposition.UNRESOLVED
        score = None
        if not assignments:
            degraded.append("observed_assignment_unavailable")
    else:
        expected = predicted.expected_assignment
        compatible_assignments = tuple(item for item in assignments if item.variable == expected.variable)
        if not compatible_assignments:
            disposition = RolloutOutcomeDisposition.UNRESOLVED
            score = None
            degraded.append("observed_variable_incompatible")
        else:
            matches = sum(item.value == expected.value for item in compatible_assignments)
            score = matches / len(compatible_assignments)
            if matches == len(compatible_assignments):
                disposition = RolloutOutcomeDisposition.MATCHED
            elif matches == 0:
                disposition = RolloutOutcomeDisposition.CONTRADICTED
            else:
                disposition = RolloutOutcomeDisposition.MIXED
    return RolloutReconciliationReceiptV1(
        product_id=rollout.product_id,
        rollout_revision_id=str(rollout.rollout_revision_id),
        rollout_revision_hash=str(rollout.rollout_revision_hash),
        predicted_outcome_id=observation.predicted_outcome_id,
        observation_id=str(observation.observation_id),
        observation_hash=str(observation.observation_hash),
        evidence_pack_id=str(observed_evidence_pack.pack_id),
        evidence_pack_hash=str(observed_evidence_pack.pack_hash),
        branch_id=observation.branch_id,
        disposition=disposition,
        score=score,
        compatible_branch=compatible_branch,
        compatible_horizon=compatible_horizon,
        reconciled_at=reconciled_at,
        foresight_prediction_ref=observation.foresight_prediction_ref,
        foresight_resolution_ref=observation.foresight_resolution_ref,
        degraded_reasons=tuple(degraded),
    )


class ConsequenceRolloutService:
    """TP6 orchestration over exact persisted TP4 and TP5 starting material."""

    def __init__(self, pool) -> None:
        from core.engine.grounded_state.belief_persistence import BeliefStateStore
        from core.engine.grounded_state.rollout_persistence import RolloutStore
        from core.engine.grounded_state.transition_persistence import TransitionStore

        self.belief_store = BeliefStateStore(pool)
        self.transition_store = TransitionStore(pool)
        self.rollout_store = RolloutStore(pool)
        from core.engine.grounded_state.transitions import TransitionHypothesisService

        self.transition_service = TransitionHypothesisService(pool)

    async def execute_and_persist(
        self,
        proposal: RolloutProposalV1,
        *,
        challenged_at: datetime,
        max_steps: int = 8,
        max_transitions: int = 8,
        prior_revision: ConsequenceRolloutRevisionV1 | None = None,
    ) -> ConsequenceRolloutRevisionV1:
        """Load exact lineage and atomically persist the complete TP6 rollout chain."""
        context_pack = await self.rollout_store.require(
            ReasoningEvidencePackV1,
            proposal.context_pack_id,
            product_id=proposal.product_id,
        )
        projection = await self.belief_store.require(
            BeliefStateProjectionV1,
            proposal.request.starting_state_id,
            product_id=proposal.product_id,
        )
        revisions = tuple(
            [
                await self.transition_service.replay_revision(
                    revision_id,
                    product_id=proposal.product_id,
                )
                for revision_id in proposal.transition_revision_ids
            ]
        )
        _ensure_lineage(
            proposal.request,
            projection=projection,
            context_pack=context_pack,
            revisions=revisions,
        )
        if proposal.context_pack_hash != context_pack.context_pack_hash:
            raise ConsequenceRolloutError("persisted reasoning pack hash does not match rollout proposal")
        if {
            str(item.revision_id): str(item.revision_hash) for item in revisions
        } != proposal.transition_revision_hashes:
            raise ConsequenceRolloutError("persisted transition hashes do not match rollout proposal")
        if prior_revision is not None:
            persisted_prior = await self.rollout_store.require(
                ConsequenceRolloutRevisionV1,
                str(prior_revision.rollout_revision_id),
                product_id=proposal.product_id,
            )
            if persisted_prior != prior_revision:
                raise ConsequenceRolloutError("rollout recalculation must extend exact persisted prior material")
        executions = execute_rollout(
            proposal,
            projection=projection,
            context_pack=context_pack,
            revisions=revisions,
            max_steps=max_steps,
            max_transitions=max_transitions,
        )
        challenge = challenge_rollout(
            proposal,
            context_pack=context_pack,
            executions=executions,
            revisions=revisions,
            challenged_at=challenged_at,
        )
        rollout = finalize_rollout(
            proposal,
            executions=executions,
            challenge=challenge,
            prior_revision=prior_revision,
        )
        await self.rollout_store.persist_all((proposal, *executions, challenge, rollout))
        return rollout

    async def replay_rollout(
        self,
        rollout_revision_id: str,
        *,
        product_id: str,
    ) -> ConsequenceRolloutRevisionV1:
        """Rebuild one exact rollout revision from persisted immutable lineage."""
        rollout = await self.rollout_store.require(
            ConsequenceRolloutRevisionV1,
            rollout_revision_id,
            product_id=product_id,
        )
        proposal = await self.rollout_store.require(
            RolloutProposalV1,
            rollout.proposal_id,
            product_id=product_id,
        )
        challenge = await self.rollout_store.require(
            RolloutChallengeReceiptV1,
            rollout.challenge_receipt_id,
            product_id=product_id,
        )
        executions = tuple(
            [
                await self.rollout_store.require(
                    TransitionExecutionReceiptV1,
                    str(item.receipt_id),
                    product_id=product_id,
                )
                for item in rollout.execution_receipts
            ]
        )
        prior = None
        if rollout.prior_revision_id is not None:
            prior = await self.rollout_store.require(
                ConsequenceRolloutRevisionV1,
                rollout.prior_revision_id,
                product_id=product_id,
            )
        replayed = finalize_rollout(
            proposal,
            executions=executions,
            challenge=challenge,
            prior_revision=prior,
        )
        if replayed != rollout:
            raise ConsequenceRolloutError("persisted rollout does not reproduce from exact TP6 lineage")
        return replayed

    async def persist_reasoning_use(
        self,
        receipt: ReasoningContextUseReceiptV1,
    ) -> ReasoningContextUseReceiptV1:
        rollout = await self.replay_rollout(
            receipt.rollout_revision_id,
            product_id=receipt.product_id,
        )
        if receipt.rollout_revision_hash != rollout.rollout_revision_hash:
            raise ConsequenceRolloutError("reasoning-use receipt does not bind exact rollout material")
        await self.rollout_store.persist(receipt)
        return receipt

    async def reconcile_and_persist(
        self,
        observation: RolloutOutcomeObservationV1,
        *,
        reconciled_at: datetime,
    ) -> RolloutReconciliationReceiptV1:
        rollout = await self.replay_rollout(
            observation.rollout_revision_id,
            product_id=observation.product_id,
        )
        observed_pack = await self.belief_store.require(
            BoundedEvidencePackV1,
            observation.evidence_pack_id,
            product_id=observation.product_id,
        )
        reconciliation = reconcile_rollout_outcome(
            rollout,
            observation,
            observed_evidence_pack=observed_pack,
            reconciled_at=reconciled_at,
        )
        await self.rollout_store.persist_all((observation, reconciliation))
        return reconciliation
