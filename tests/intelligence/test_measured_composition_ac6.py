"""AC6 preregistered matched-composition conformance and fail-closed proof."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from ace.application.measured_composition import (
    CompositionEvaluationAuthorityResolutionV1Alpha1,
    MeasuredCompositionError,
    MeasuredCompositionEvaluationService,
)
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1, GovernedStateHeadV1
from ace.intelligence.contracts.measured_composition import (
    CompositionComparisonDisposition,
    CompositionEvaluationCondition,
    CompositionEvaluationFailure,
    CompositionEvaluationProtocolV1Alpha1,
    CompositionPolicyProposalDisposition,
    CompositionPolicyProposalDispositionV1Alpha1,
    measured_composition_reference,
)
from ace.intelligence.measured_composition import compare_measured_composition
from ace.testing.immutable_records import InMemoryImmutableRecordStore
from evaluations.source.ac6_measured_composition import (
    BASE,
    FIXTURE_PATH,
    _build_assignment,
    _build_authority,
    _build_observation,
    _build_protocol,
    _ref,
    run_provider_free_fixture,
)

pytestmark = pytest.mark.unit
REPO = Path(__file__).resolve().parents[2]
RESULT = REPO / "evaluations/results/ac6_measured_composition_v1.json"


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def _scenario(case_id: str):
    fixture = _fixture()
    authority, heads = _build_authority(fixture["product_id"])
    protocol = _build_protocol(fixture, authority)
    case = next(item for item in fixture["cases"] if item["case_id"] == case_id)
    assignment = _build_assignment(protocol, case_id=case_id, assigned_at=BASE + timedelta(minutes=1))
    observations = tuple(
        _build_observation(
            fixture,
            protocol,
            assignment,
            case,
            condition,
            observed_at=assignment.assigned_at + timedelta(seconds=index + 1),
        )
        for index, condition in enumerate(CompositionEvaluationCondition)
    )
    return fixture, authority, heads, protocol, assignment, observations


def test_fixture_freezes_protocol_conditions_failure_taxonomy_and_inert_boundaries() -> None:
    fixture = _fixture()
    authority, _ = _build_authority(fixture["product_id"])
    protocol = _build_protocol(fixture, authority)
    assert set(protocol.conditions) == set(CompositionEvaluationCondition)
    assert set(protocol.failure_taxonomy) == set(CompositionEvaluationFailure)
    assert protocol.frozen_before_observation is True
    assert protocol.held_constants.budget.max_external_effects == 0
    assert fixture["optional_real_model_run"]["required_for_acceptance"] is False
    assert not any(
        value is True
        for key, value in fixture["invariants"].items()
        if key
        in {
            "proposal_activates_policy",
            "proposal_changes_roster",
            "proposal_grants_authority",
            "proposal_schedules_execution",
            "proposal_delivers_or_exports",
            "proposal_sends_external_effect",
            "evaluation_writes_agent_memory",
            "evaluation_trains_or_rewrites_policy",
        }
    )


def test_historical_activation_and_ac5_delivery_cannot_authorize_evaluation() -> None:
    fixture = _fixture()
    authority, _ = _build_authority(fixture["product_id"])
    protocol = _build_protocol(fixture, authority)
    for forbidden in (
        "ace.application.domain-activation-commit-reference/v1alpha2",
        "ace.application.prepared-lifecycle-delivery/v1alpha1",
    ):
        changed = protocol.model_dump(mode="python")
        changed["evaluation_authority"] = _ref("forbidden:authority", forbidden)
        changed["protocol_id"] = None
        changed["protocol_digest"] = None
        with pytest.raises(ValidationError, match="present-tense composition-evaluation authority"):
            CompositionEvaluationProtocolV1Alpha1.model_validate(changed)
    assert authority.reusable_authority is False


def test_dynamic_help_is_narrow_paired_and_emits_only_an_inert_proposal() -> None:
    _, _, _, protocol, assignment, observations = _scenario("dynamic_helps")
    comparison, proposal = compare_measured_composition(
        protocol,
        assignment,
        observations,
        current_policy=_ref("composition_policy:current", "ace.governance.composition-policy/v1"),
        proposed_policy_rule_ref="composition_policy_rule:dynamic-for-exact-scope",
        compared_at=assignment.assigned_at + timedelta(seconds=10),
    )
    assert comparison.disposition is CompositionComparisonDisposition.DYNAMIC_MATERIALLY_HELPS
    assert comparison.paired_and_controlled is True
    assert proposal is not None
    assert not any(
        (
            proposal.live_effect,
            proposal.activates_policy,
            proposal.changes_roster,
            proposal.grants_authority,
            proposal.schedules_execution,
            proposal.delivers,
            proposal.exports,
            proposal.sends_external_effect,
            proposal.writes_agent_memory,
            proposal.trains_or_rewrites_policy,
        )
    )
    assert proposal.requires_present_tense_approval is True
    assert proposal.requires_separate_admission is True
    assert proposal.rollback_policy == proposal.current_policy


@pytest.mark.parametrize(
    ("case_id", "expected"),
    [
        ("solo_suffices", CompositionComparisonDisposition.CONTROL_SUFFICES),
        ("dynamic_cost_no_benefit", CompositionComparisonDisposition.NO_MATERIAL_BENEFIT),
        ("missing_participant", CompositionComparisonDisposition.UNPROVEN_FAIL_CLOSED),
        ("timeout", CompositionComparisonDisposition.UNPROVEN_FAIL_CLOSED),
        ("partial_tainted_join", CompositionComparisonDisposition.UNPROVEN_FAIL_CLOSED),
        ("stale_authority", CompositionComparisonDisposition.UNPROVEN_FAIL_CLOSED),
        ("revoked_rotated_authority", CompositionComparisonDisposition.UNPROVEN_FAIL_CLOSED),
        ("delivery_denial", CompositionComparisonDisposition.UNPROVEN_FAIL_CLOSED),
        ("effect_denial", CompositionComparisonDisposition.UNPROVEN_FAIL_CLOSED),
        ("usage_cost_telemetry_unavailable", CompositionComparisonDisposition.UNPROVEN_FAIL_CLOSED),
        ("abstention", CompositionComparisonDisposition.UNPROVEN_FAIL_CLOSED),
        ("attempted_policy_self_activation", CompositionComparisonDisposition.UNPROVEN_FAIL_CLOSED),
        ("duplicate_effect_prevention", CompositionComparisonDisposition.NO_MATERIAL_BENEFIT),
    ],
)
def test_controls_and_fail_closed_cases_never_emit_a_policy_proposal(case_id, expected) -> None:
    _, _, _, protocol, assignment, observations = _scenario(case_id)
    comparison, proposal = compare_measured_composition(
        protocol,
        assignment,
        observations,
        current_policy=_ref("composition_policy:current", "ace.governance.composition-policy/v1"),
        proposed_policy_rule_ref="composition_policy_rule:dynamic-for-exact-scope",
        compared_at=assignment.assigned_at + timedelta(seconds=10),
    )
    assert comparison.disposition is expected
    assert proposal is None
    if expected is CompositionComparisonDisposition.UNPROVEN_FAIL_CLOSED:
        assert comparison.paired_and_controlled is False


def test_unmatched_input_or_unpreregistered_timing_cannot_create_a_causal_claim() -> None:
    _, _, _, protocol, assignment, observations = _scenario("dynamic_helps")
    changed = assignment.model_dump(mode="python")
    changed["task_inputs"] = (_ref("task:different", "ace.evaluation.fixture-task/v1"),)
    changed["assignment_id"] = None
    changed["assignment_digest"] = None
    drifted = type(assignment).model_validate(changed)
    with pytest.raises(ValueError, match="changed frozen task"):
        compare_measured_composition(
            protocol,
            drifted,
            observations,
            current_policy=_ref("composition_policy:current", "ace.governance.composition-policy/v1"),
            proposed_policy_rule_ref="composition_policy_rule:dynamic-for-exact-scope",
            compared_at=assignment.assigned_at + timedelta(seconds=10),
        )


def test_accept_reject_supersede_and_rollback_are_non_applying_review_evidence() -> None:
    _, _, heads, protocol, assignment, observations = _scenario("dynamic_helps")
    _, proposal = compare_measured_composition(
        protocol,
        assignment,
        observations,
        current_policy=_ref("composition_policy:current", "ace.governance.composition-policy/v1"),
        proposed_policy_rule_ref="composition_policy_rule:dynamic-for-exact-scope",
        compared_at=assignment.assigned_at + timedelta(seconds=10),
    )
    assert proposal is not None
    proposal_ref = measured_composition_reference(proposal)
    approval = _ref("approval:present-tense-ac6", "ace.core.approval-receipt/v1alpha1")
    policy_head = GovernedStateHeadPreconditionV1Alpha1(
        state_kind="composition_policy",
        product_id=protocol.product_id,
        state_id="composition_policy:current",
        sequence=1,
        revision_id="composition_policy_revision:1",
        commit_receipt_id="governed_state_commit:composition-policy-1",
    )
    assert heads
    for disposition in CompositionPolicyProposalDisposition:
        evidence = CompositionPolicyProposalDispositionV1Alpha1(
            product_id=protocol.product_id,
            proposal=proposal_ref,
            disposition=disposition,
            present_tense_approval=approval,
            current_policy_head=policy_head,
            superseding_proposal=proposal_ref
            if disposition is CompositionPolicyProposalDisposition.SUPERSEDE
            else None,
            rationale=f"Exercise the {disposition.value} governed review path without applying a change.",
            decided_at=assignment.assigned_at + timedelta(minutes=1),
        )
        assert evidence.applies_change is False


@pytest.mark.asyncio
async def test_append_chain_is_content_addressed_restart_safe_and_current_head_guarded() -> None:
    fixture, authority, heads, protocol, assignment, observations = _scenario("dynamic_helps")
    store = InMemoryImmutableRecordStore(
        governed_state_heads={(item.state_kind, item.product_id, item.state_id): item for item in heads}
    )
    service = MeasuredCompositionEvaluationService(store=store)
    preregistration = await service.preregister(authority=authority, protocol=protocol)
    assert preregistration.protocol.record_key == protocol.protocol_id
    await service.assign(assignment)
    refs = tuple([await service.observe(item) for item in observations])
    closure = await service.close(
        product_id=protocol.product_id,
        protocol_ref=measured_composition_reference(protocol),
        assignment_ref=measured_composition_reference(assignment),
        observation_refs=tuple(measured_composition_reference(item) for item in observations),
        current_policy=_ref("composition_policy:current", "ace.governance.composition-policy/v1"),
        proposed_policy_rule_ref="composition_policy_rule:dynamic-for-exact-scope",
        compared_at=assignment.assigned_at + timedelta(seconds=10),
    )
    restarted = MeasuredCompositionEvaluationService(store=store)
    replay = await restarted.close(
        product_id=protocol.product_id,
        protocol_ref=measured_composition_reference(protocol),
        assignment_ref=measured_composition_reference(assignment),
        observation_refs=tuple(measured_composition_reference(item) for item in observations),
        current_policy=_ref("composition_policy:current", "ace.governance.composition-policy/v1"),
        proposed_policy_rule_ref="composition_policy_rule:dynamic-for-exact-scope",
        compared_at=assignment.assigned_at + timedelta(seconds=10),
    )
    assert closure == replay
    assert len(refs) == 3

    grant = heads[0] if heads[0].state_kind == "authority_grant" else heads[1]
    rotated = GovernedStateHeadV1(
        state_kind=grant.state_kind,
        product_id=grant.product_id,
        state_id=grant.state_id,
        sequence=2,
        revision_id="authority_grant_revision:ac6-2",
        commit_receipt_id="governed_state_commit:authority-grant-ac6-2",
        updated_at=BASE + timedelta(hours=1),
    )
    store.set_governed_state_head(rotated)
    later = _build_assignment(protocol, case_id="rotated-head", assigned_at=BASE + timedelta(hours=2))
    with pytest.raises(MeasuredCompositionError, match="append failed closed"):
        await restarted.assign(later)
    assert fixture["product_id"] == protocol.product_id


def test_provider_free_fixture_is_deterministic_across_fresh_processes() -> None:
    outputs = []
    for seed in ("1", "991"):
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = seed
        env["PYTHONPATH"] = str(REPO)
        process = subprocess.run(
            [sys.executable, str(REPO / "scripts/verify_ac6_measured_composition.py"), "--json"],
            cwd=REPO,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        outputs.append(process.stdout.strip())
    assert outputs[0] == outputs[1]
    result = json.loads(outputs[0])
    assert result["restart_replay_identical"] is True
    assert result["provider_credentials_used"] is False
    assert result["network_used"] is False
    assert result["proposal_count"] == 1


def test_provider_free_fixture_runs_without_extensions() -> None:
    prior = os.environ.get("ACE_DISABLE_EXTENSIONS")
    os.environ["ACE_DISABLE_EXTENSIONS"] = "1"
    try:
        result = asyncio.run(run_provider_free_fixture())
    finally:
        if prior is None:
            os.environ.pop("ACE_DISABLE_EXTENSIONS", None)
        else:
            os.environ["ACE_DISABLE_EXTENSIONS"] = prior
    assert result["restart_replay_identical"] is True
    assert result["case_count"] == len(_fixture()["cases"])
    assert CompositionEvaluationAuthorityResolutionV1Alpha1.__module__ == "ace.application.measured_composition"


def test_committed_machine_result_matches_a_fresh_provider_free_run() -> None:
    assert json.loads(RESULT.read_text()) == asyncio.run(run_provider_free_fixture())
