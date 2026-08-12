from __future__ import annotations

import ast
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from ace.core.agent_composition import (
    AuthorityClass,
    AuthorityCoordinateV1Alpha1,
    CompositionBudgetV1Alpha1,
    CompositionNodeKind,
    CompositionNodeV1Alpha1,
    CompositionParticipantV1Alpha1,
    ContextUseState,
    DomainActivationLineageV1Alpha1,
    ExactArtifactReferenceV1Alpha1,
    ParticipantKind,
    RunState,
    StageRunManifestV1Alpha1,
    StageRunReceiptV1Alpha1,
    TaskCompositionPlanV1Alpha1,
    UsageV1Alpha1,
    validate_run_receipt_against_manifest,
)
from ace.intelligence.contracts.agent_composition import (
    GovernedAgentDefinitionRevisionV1Alpha1,
    InstructionConstraintsV1Alpha1,
    InstructionContributionV1Alpha1,
    InstructionLayer,
    LifecycleStage,
    OrchestrationPattern,
    StageRoleBindingRevisionV1Alpha1,
    resolve_instruction_contributions,
    validate_role_binding_narrows_definition,
)

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "evaluations" / "fixtures" / "ac1_agent_composition_conformance_v1.json"
NOW = datetime(2026, 8, 11, 20, 0, tzinfo=UTC)
PRODUCT = "product:ac1-conformance"


def _ref(artifact_id: str, artifact_contract: str, fill: str = "a") -> ExactArtifactReferenceV1Alpha1:
    return ExactArtifactReferenceV1Alpha1(
        artifact_id=artifact_id,
        artifact_digest=f"sha256:{fill * 64}",
        artifact_contract=artifact_contract,
    )


def _budget(**overrides: int) -> CompositionBudgetV1Alpha1:
    values = {
        "max_items": 32,
        "max_tokens": 4_000,
        "max_calls": 8,
        "max_latency_ms": 30_000,
        "max_cost_microunits": 50_000,
        "max_concurrency": 4,
        "max_external_effects": 0,
    }
    values.update(overrides)
    return CompositionBudgetV1Alpha1(**values)


def _authority(principal: str, authority_class: AuthorityClass) -> AuthorityCoordinateV1Alpha1:
    return AuthorityCoordinateV1Alpha1(
        product_id=PRODUCT,
        principal_ref=principal,
        authority_class=authority_class,
        grant_ref=f"grant:{principal}:{authority_class.value}",
        scope_ref="scope:ac1-fixture",
        policy_ref="policy:ac1-authority-v1",
    )


def _participant(name: str) -> CompositionParticipantV1Alpha1:
    if name == "authorized-reviewer":
        return CompositionParticipantV1Alpha1(
            composition_participant_id=f"composition_participant:{name}",
            participant_kind=ParticipantKind.HUMAN,
            participant_ref="actor:ac1-reviewer",
            authority=(_authority("actor:ac1-reviewer", AuthorityClass.DECIDE_APPROVE),),
        )
    return CompositionParticipantV1Alpha1(
        composition_participant_id=f"composition_participant:{name}",
        participant_kind=ParticipantKind.MODEL_AGENT,
        participant_ref=f"agent_principal:{name}",
        definition_revision=_ref(
            f"agent_definition_revision:{name}",
            "ace.intelligence.governed-agent-definition-revision/v1alpha1",
            "b",
        ),
        role_binding=_ref(
            f"stage_role_binding_revision:{name}",
            "ace.intelligence.stage-role-binding-revision/v1alpha1",
            "c",
        ),
        authority=(
            _authority(f"agent_principal:{name}", AuthorityClass.OBSERVE_READ),
            _authority(f"agent_principal:{name}", AuthorityClass.DERIVE_PROPOSE),
        ),
        tool_refs=("tool:read", "tool:retrieve"),
        source_scope_refs=("source_scope:fixture",),
    )


def _build_plan(case: dict, *, reverse_inputs: bool = False) -> TaskCompositionPlanV1Alpha1:
    participants = [_participant(name) for name in case["participants"]]
    nodes = [
        CompositionNodeV1Alpha1(
            node_id=item["id"],
            node_kind=CompositionNodeKind(item["kind"]),
            composition_participant_id=(
                f"composition_participant:{item['participant']}" if item.get("participant") else None
            ),
            depends_on=tuple(item["depends_on"]),
            input_contracts=("fixture.stage-input/v1",),
            output_contracts=("fixture.stage-output/v1",),
            validator_refs=("validator:fixture-v1",),
            exit_criteria_refs=("exit:fixture-v1",),
            required=item.get("participant") != case.get("missing_optional_participant"),
        )
        for item in case["nodes"]
    ]
    if reverse_inputs:
        participants.reverse()
        nodes.reverse()
    activation_lineage = DomainActivationLineageV1Alpha1(
        commit_reference=_ref(
            "domain_activation_commit_reference:ac1-fixture",
            "ace.application.domain-activation-commit-reference/v1alpha2",
            "d",
        )
    )
    return TaskCompositionPlanV1Alpha1(
        product_id=PRODUCT,
        actor_ref="actor:ac1-builder",
        session_ref="session:ac1-fixture",
        task_ref=f"task:ac1-{case['name']}",
        objective="Produce one bounded, attributable recommendation without widening authority.",
        stage_id=LifecycleStage.DELIBERATE.value,
        activation_lineage=activation_lineage,
        trigger_artifacts=(
            _ref("fixture:approved-watch-proposal", "fixture.approved-watch-proposal/v1", "e"),
            _ref("fixture:inert-brief-preview", "fixture.inert-brief-preview/v1", "f"),
        ),
        classifier_revision_ref="classifier:ac1-fixture-v1",
        routing_revision_ref="routing:ac1-fixture-v1",
        policy_revision_ref="policy:ac1-fixture-v1",
        composer_revision_ref="composer:ac1-fixture-v1",
        participants=tuple(participants),
        nodes=tuple(nodes),
        orchestration_pattern=OrchestrationPattern(case["pattern"]).value,
        expected_output_contracts=("fixture.stage-output/v1",),
        gate_refs=("gate:typed-output",),
        allowed_next_stage_ids=(LifecycleStage.DECIDE.value,),
        aggregate_budget=_budget(),
        context_request_ref="context_request:ac1-fixture",
        candidate_receipts=(_ref("candidate_receipt:ac1-fixture", "fixture.candidate-receipt/v1", "1"),),
        context_receipts=(_ref("context_selection_receipt:ac1-fixture", "fixture.context-selection-receipt/v1", "2"),),
        failure_policy_ref="failure_policy:ac1-fixture-v1",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def _manifest(plan: TaskCompositionPlanV1Alpha1) -> StageRunManifestV1Alpha1:
    participant = next(item for item in plan.participants if item.participant_kind == ParticipantKind.MODEL_AGENT)
    plan_ref = ExactArtifactReferenceV1Alpha1(
        artifact_id=str(plan.composition_plan_id),
        artifact_digest=str(plan.composition_plan_digest),
        artifact_contract=plan.contract,
    )
    return StageRunManifestV1Alpha1(
        plan=plan_ref,
        product_id=plan.product_id,
        stage_id=plan.stage_id,
        node_id=next(
            item.node_id
            for item in plan.nodes
            if item.composition_participant_id == participant.composition_participant_id
        ),
        composition_participant_id=participant.composition_participant_id,
        definition_revision=participant.definition_revision,
        role_binding=participant.role_binding,
        task_ref=plan.task_ref,
        invocation_key=f"invocation:{plan.task_ref}",
        instruction_resolution=_ref(
            "instruction_resolution_receipt:fixture",
            "ace.intelligence.instruction-resolution-receipt/v1alpha1",
            "3",
        ),
        instruction_layer_refs=tuple(
            _ref(
                f"instruction_contribution:{layer.name.lower()}",
                "ace.intelligence.instruction-contribution/v1alpha1",
                str(index),
            )
            for index, layer in enumerate(InstructionLayer, start=1)
        ),
        context_manifest=_ref("context_manifest:am0-opaque", "fixture.context-manifest/v1", "4"),
        tool_refs=participant.tool_refs,
        source_scope_refs=participant.source_scope_refs,
        authority=participant.authority,
        execution_binding=_ref(
            "reasoning_execution_binding:fixture",
            "ace.core.reasoning-execution-binding/v1alpha1",
            "5",
        ),
        input_artifacts=plan.trigger_artifacts,
        output_contracts=("fixture.stage-output/v1",),
        validator_refs=("validator:fixture-v1",),
        exit_criteria_refs=("exit:fixture-v1",),
        handoff_target_ref="stage_handoff_contract:fixture",
        budget=_budget(max_concurrency=1),
        cancellation_ref="cancellation:fixture-v1",
        retry_ref="retry:fixture-v1",
        idempotency_key=f"idempotency:{plan.task_ref}",
        degraded_policy_ref="degraded:fixture-v1",
        escalation_policy_ref="escalation:fixture-v1",
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
    )


def _run_receipt(manifest: StageRunManifestV1Alpha1) -> StageRunReceiptV1Alpha1:
    return StageRunReceiptV1Alpha1(
        plan=manifest.plan,
        manifest=ExactArtifactReferenceV1Alpha1(
            artifact_id=str(manifest.manifest_id),
            artifact_digest=str(manifest.manifest_digest),
            artifact_contract=manifest.contract,
        ),
        product_id=manifest.product_id,
        composition_participant_id=manifest.composition_participant_id,
        attempt=1,
        state=RunState.COMPLETE,
        started_at=NOW + timedelta(seconds=1),
        ended_at=NOW + timedelta(seconds=2),
        actual_route=_ref("provider_route:observed", "ace.core.provider-route/v1alpha1", "6"),
        usage=UsageV1Alpha1(items=2, tokens=800, calls=1, latency_ms=1_000),
        actual_tool_refs=("tool:read",),
        authority_exercised=(manifest.authority[0],),
        output_artifacts=(_ref("contribution:fixture", "fixture.contribution/v1", "7"),),
        context_states=(
            ContextUseState.ELIGIBLE,
            ContextUseState.AUTHORIZED,
            ContextUseState.SELECTED,
            ContextUseState.INJECTED,
            ContextUseState.REFLECTED,
        ),
    )


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_frozen_fixture_covers_solo_pipeline_fanout_join_adversarial_and_human_gate() -> None:
    fixture = _fixture()
    assert fixture["fixture_version"] == "ace.agent-composition-conformance/v1"
    assert [item["pattern"] for item in fixture["cases"]] == [
        "solo",
        "pipeline",
        "fanout_join",
        "adversarial",
        "human_gate",
    ]
    for case in fixture["cases"]:
        plan = _build_plan(case)
        replay = TaskCompositionPlanV1Alpha1.model_validate_json(plan.model_dump_json())
        reordered = _build_plan(case, reverse_inputs=True)
        assert replay == plan
        assert reordered == plan
        assert plan.composition_plan_id.startswith("task_composition_plan:")
        assert "plan_id" not in TaskCompositionPlanV1Alpha1.model_fields
        assert plan.activation_lineage is not None and plan.activation_lineage.live_authority is False


def test_plan_local_participant_identity_does_not_collide_with_am0_participant_id() -> None:
    fields = CompositionParticipantV1Alpha1.model_fields
    assert "composition_participant_id" in fields
    assert "participant_id" not in fields
    plan = _build_plan(_fixture()["cases"][0])
    assert all(item.composition_participant_id.startswith("composition_participant:") for item in plan.participants)
    assert plan.candidate_receipts[0].artifact_id.startswith("candidate_receipt:")
    manifest = _manifest(plan)
    assert manifest.context_manifest.artifact_id == "context_manifest:am0-opaque"


def test_activation_commit_reference_is_lineage_only_and_cannot_be_an_activation_plan() -> None:
    lineage = DomainActivationLineageV1Alpha1(
        commit_reference=_ref(
            "domain_activation_commit_reference:historical",
            "ace.application.domain-activation-commit-reference/v1alpha2",
        )
    )
    assert lineage.live_authority is False
    with pytest.raises(ValidationError, match="historical commit-reference"):
        DomainActivationLineageV1Alpha1(
            commit_reference=_ref("activation_plan:wrong", "ace.application.activation-plan/v1alpha1")
        )
    with pytest.raises(ValidationError):
        DomainActivationLineageV1Alpha1.model_validate({**lineage.model_dump(mode="python"), "live_authority": True})


def test_definition_and_stage_role_binding_are_provider_neutral_and_binding_only_narrows() -> None:
    definition = GovernedAgentDefinitionRevisionV1Alpha1(
        principal_id="agent_principal:analyst",
        purpose="Produce bounded source-linked analysis.",
        eligible_stages=(LifecycleStage.DELIBERATE, LifecycleStage.INVESTIGATE),
        accepted_input_contracts=("fixture.stage-input/v1",),
        produced_output_contracts=("fixture.stage-output/v1",),
        eligible_cognition_refs=("cognition_revision:fixture",),
        required_tool_refs=("tool:read",),
        optional_tool_refs=("tool:retrieve",),
        source_policy_refs=("source_policy:fixture",),
        destination_policy_refs=("destination_policy:none",),
        maximum_authority=(AuthorityClass.OBSERVE_READ, AuthorityClass.DERIVE_PROPOSE),
        budget_ceiling=_budget(),
        escalation_policy_refs=("escalation:fixture",),
        failure_policy_ref="failure:fixture",
        approval_receipt_ref="approval:definition-fixture",
        lifecycle_ref="lifecycle:active-fixture",
        implementation_protocol_ref="protocol:fixture-v1",
    )
    binding = StageRoleBindingRevisionV1Alpha1(
        definition_revision=ExactArtifactReferenceV1Alpha1(
            artifact_id=str(definition.definition_revision_id),
            artifact_digest=str(definition.definition_digest),
            artifact_contract=definition.contract,
        ),
        stage=LifecycleStage.DELIBERATE,
        role_label="bounded analyst",
        objective_class="recommendation",
        required_input_contracts=("fixture.stage-input/v1",),
        expected_output_contracts=("fixture.stage-output/v1",),
        exit_criteria_refs=("exit:fixture",),
        orchestration_patterns=(OrchestrationPattern.SOLO, OrchestrationPattern.FANOUT_JOIN),
        independence_policy_ref="independence:fixture",
        tool_refs=("tool:read",),
        source_policy_refs=("source_policy:fixture",),
        authority_ceiling=(AuthorityClass.OBSERVE_READ,),
        budget_ceiling=_budget(max_calls=4, max_concurrency=2),
        escalation_policy_ref="escalation:fixture",
        lifecycle_ref="lifecycle:active-fixture",
    )
    validate_role_binding_narrows_definition(definition, binding)
    assert "provider" not in GovernedAgentDefinitionRevisionV1Alpha1.model_fields
    assert "model" not in GovernedAgentDefinitionRevisionV1Alpha1.model_fields
    widened = binding.model_copy(update={"tool_refs": ("tool:publish",)})
    with pytest.raises(ValueError, match="widens definition tools"):
        validate_role_binding_narrows_definition(definition, widened)


def _instruction_contributions() -> tuple[InstructionContributionV1Alpha1, ...]:
    result = []
    for index, layer in enumerate(InstructionLayer, start=1):
        tools = ("tool:read", "tool:retrieve")
        if layer == InstructionLayer.TASK_BRIEF:
            tools = ("tool:read",)
        if layer == InstructionLayer.AUTHORIZED_CONTEXT_MANIFEST:
            tools = ("tool:publish", "tool:read")
        result.append(
            InstructionContributionV1Alpha1(
                product_id=PRODUCT,
                layer=layer,
                policy_ref=_ref(f"policy:{layer.name.lower()}", "fixture.instruction-policy/v1", str(index)),
                instruction_content_ref=_ref(
                    f"instruction:{layer.name.lower()}",
                    "fixture.instruction-content/v1",
                    str(index),
                ),
                constraints=InstructionConstraintsV1Alpha1(
                    tool_refs=tools,
                    source_scope_refs=("source_scope:fixture",),
                    destination_scope_refs=(),
                    authority_classes=(AuthorityClass.OBSERVE_READ, AuthorityClass.DERIVE_PROPOSE),
                ),
                source_content_is_data_only=True,
            )
        )
    return tuple(result)


def test_instruction_resolution_is_precedence_ordered_authorization_first_and_injection_resistant() -> None:
    contributions = _instruction_contributions()
    first = resolve_instruction_contributions(contributions)
    second = resolve_instruction_contributions(tuple(reversed(contributions)))
    assert first == second
    assert first.blocked is False
    assert first.effective_constraints.tool_refs == ("tool:read",)
    assert first.effective_constraints.destination_scope_refs == ()
    assert [item.artifact_id for item in first.ordered_contributions] == [
        item.contribution_id for item in contributions
    ]
    assert contributions[6].layer == InstructionLayer.AUTHORIZED_CONTEXT_MANIFEST
    assert contributions[6].source_content_is_data_only is True
    missing_context = resolve_instruction_contributions(
        tuple(item for item in contributions if item.layer != InstructionLayer.AUTHORIZED_CONTEXT_MANIFEST)
    )
    assert missing_context.blocked is True
    assert missing_context.issues[0].issue_code == "ace.composition.instruction.missing_required_layer"


def test_manifest_is_immutable_provider_binding_is_separate_and_run_cannot_widen_it() -> None:
    adversarial = next(item for item in _fixture()["cases"] if item["name"] == "adversarial")
    plan = _build_plan(adversarial)
    manifest = _manifest(plan)
    receipt = _run_receipt(manifest)
    validate_run_receipt_against_manifest(manifest, receipt)
    serialized = manifest.model_dump_json()
    assert adversarial["untrusted_context"] not in serialized
    assert "provider-route" not in manifest.execution_binding.artifact_contract
    assert receipt.actual_route is not None and "provider-route" in receipt.actual_route.artifact_contract
    with pytest.raises(ValidationError):
        manifest.tool_refs += ("tool:publish",)
    widened = receipt.model_copy(update={"actual_tool_refs": ("tool:publish",)})
    with pytest.raises(ValueError, match="tools outside"):
        validate_run_receipt_against_manifest(manifest, widened)


def test_human_gate_requires_declared_human_and_exact_authority_not_generated_text() -> None:
    case = next(item for item in _fixture()["cases"] if item["name"] == "human_gate")
    plan = _build_plan(case)
    gate = next(item for item in plan.nodes if item.node_kind == CompositionNodeKind.HUMAN_GATE)
    reviewer = next(
        item for item in plan.participants if item.composition_participant_id == gate.composition_participant_id
    )
    assert reviewer.participant_kind == ParticipantKind.HUMAN
    assert reviewer.authority[0].grant_ref != case["generated_approval_text"]
    without_human = plan.model_dump(mode="python")
    without_human["participants"] = tuple(
        item for item in plan.participants if item.participant_kind != ParticipantKind.HUMAN
    )
    with pytest.raises(ValidationError, match="declared participants"):
        TaskCompositionPlanV1Alpha1.model_validate(without_human)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_ac1_contracts_and_ports_preserve_import_boundaries() -> None:
    core_imports = _imports(REPO / "ace" / "core" / "agent_composition.py")
    assert all(
        name.split(".")[0] in {"__future__", "datetime", "enum", "typing", "pydantic", "ace"} for name in core_imports
    )
    assert all(not name.startswith(("ace.application", "ace.intelligence", "core.engine")) for name in core_imports)
    semantic_imports = _imports(REPO / "ace" / "intelligence" / "contracts" / "agent_composition.py")
    assert all(not name.startswith(("ace.application", "core.engine")) for name in semantic_imports)
    application_imports = _imports(REPO / "ace" / "application" / "agent_composition.py")
    assert all(not name.startswith(("core.engine", "ace_mcp_client")) for name in application_imports)
