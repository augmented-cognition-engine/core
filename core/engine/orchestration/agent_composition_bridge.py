"""AC2 compatibility bridge around the supported orchestration journey.

The legacy classifier, cognitive composer, recipe instruments, pattern runner,
I2 deliberation, and I3 intelligence-use projection remain authoritative for
their existing semantics.  This module adds immutable AC1 control/evidence
coordinates around that journey; it does not replace those components.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from core.engine.core.agent_composition_runtime import (
    CompositionBudgetV1Alpha1,
    CompositionNodeKind,
    CompositionNodeV1Alpha1,
    CompositionParticipantV1Alpha1,
    ContextUseState,
    ExactArtifactReferenceV1Alpha1,
    HandoffState,
    ParticipantKind,
    ReasoningCompositionRuntimeAuthorityBundle,
    ReasoningCompositionRuntimeAuthorityPort,
    RunState,
    StageHandoffContractV1Alpha1,
    StageHandoffReceiptV1Alpha1,
    StageRunManifestV1Alpha1,
    StageRunReceiptV1Alpha1,
    TaskCompositionPlanV1Alpha1,
    UsageV1Alpha1,
    canonical_hash,
    exact_reference,
    validate_run_receipt_against_manifest,
)
from core.engine.orchestration.agent import AgentConfig, AgentResult
from core.engine.orchestration.patterns.base import PatternResult


class GovernedCompositionBridgeError(RuntimeError):
    """The selected governed path could not produce exact evidence."""


@dataclass(frozen=True, slots=True)
class LegacyCompositionAuthorityPolicy:
    participant_principal_ref: str
    authority_class: str
    operation: str
    grant_ref: str
    scope_ref: str
    policy_ref: str
    classifier_revision_ref: str
    routing_revision_ref: str
    composition_policy_revision_ref: str
    composer_revision_ref: str
    context_policy_ref: str
    failure_policy_ref: str


@dataclass(frozen=True, slots=True)
class PreparedGovernedComposition:
    plan: TaskCompositionPlanV1Alpha1
    manifests: tuple[StageRunManifestV1Alpha1, ...]
    planning_authority: tuple[ReasoningCompositionRuntimeAuthorityBundle, ...]
    instruction_resolution: ExactArtifactReferenceV1Alpha1
    context_manifest: ExactArtifactReferenceV1Alpha1


@dataclass(frozen=True, slots=True)
class CompletedGovernedComposition:
    plan: TaskCompositionPlanV1Alpha1
    manifests: tuple[StageRunManifestV1Alpha1, ...]
    run_receipts: tuple[StageRunReceiptV1Alpha1, ...]
    join_evidence: ExactArtifactReferenceV1Alpha1
    handoff_contract: StageHandoffContractV1Alpha1
    handoff_receipt: StageHandoffReceiptV1Alpha1
    planning_authority_receipts: tuple[ExactArtifactReferenceV1Alpha1, ...]
    execution_authority_receipts: tuple[ExactArtifactReferenceV1Alpha1, ...]

    def projection(self) -> dict[str, Any]:
        return {
            "contract": "ace.orchestration.governed-composition-record-set/v1alpha1",
            "task_composition_plan": self.plan.model_dump(mode="json"),
            "stage_run_manifests": [item.model_dump(mode="json") for item in self.manifests],
            "stage_run_receipts": [item.model_dump(mode="json") for item in self.run_receipts],
            "join_evidence": self.join_evidence.model_dump(mode="json"),
            "stage_handoff_contract": self.handoff_contract.model_dump(mode="json"),
            "stage_handoff_receipt": self.handoff_receipt.model_dump(mode="json"),
            "planning_authority_receipts": [item.model_dump(mode="json") for item in self.planning_authority_receipts],
            "execution_authority_receipts": [
                item.model_dump(mode="json") for item in self.execution_authority_receipts
            ],
            "legacy_ownership": {
                "classifier_composer_recipes": "selection_inputs",
                "i2_deliberation": "contributor_independence_and_synthesis",
                "i3_intelligence_use": "selection_injection_reflection_and_material_use",
                "delivery_authority": False,
            },
        }


def _ref(prefix: str, contract: str, material: object) -> ExactArtifactReferenceV1Alpha1:
    digest = canonical_hash(material)
    return ExactArtifactReferenceV1Alpha1(
        artifact_id=f"{prefix}:{digest[:32]}",
        artifact_digest=f"sha256:{digest}",
        artifact_contract=contract,
    )


def _pattern(value: str) -> str:
    mapping = {
        "independent": "solo",
        "pipeline": "pipeline",
        "fanout": "fanout_join",
        "adversarial": "adversarial",
        "team": "fanout_join",
        "multi-phase": "pipeline",
        "human_gate": "human_gate",
    }
    try:
        return mapping[value]
    except KeyError as exc:
        raise GovernedCompositionBridgeError(f"unsupported governed compatibility pattern: {value}") from exc


def _context_states(snapshot: dict[str, Any]) -> tuple[ContextUseState, ...]:
    trace = snapshot.get("_intelligence_use_trace")
    if not isinstance(trace, dict) or not trace.get("items"):
        return ()
    states = [ContextUseState.ELIGIBLE, ContextUseState.AUTHORIZED, ContextUseState.SELECTED]
    items = [item for item in trace.get("items", []) if isinstance(item, dict)]
    if any(item.get("injected") is True for item in items):
        states.append(ContextUseState.INJECTED)
        reflected = set(trace.get("reflected_ids") or [])
        if reflected:
            states.append(ContextUseState.REFLECTED)
    # Material use remains exclusively owned by the later I3 decision receipt.
    return tuple(states)


def _run_state(result: AgentResult | None, aggregate: PatternResult) -> RunState:
    if result is None:
        return RunState.FAILED
    status = str(getattr(result, "status", None) or aggregate.status).lower()
    if status in {"completed", "complete"}:
        return RunState.COMPLETE
    if status in {"timeout", "timed_out"}:
        return RunState.DEGRADED
    if status in {"abstained", "abstain"}:
        return RunState.ABSTAINED
    if status in {"cancelled", "canceled"}:
        return RunState.CANCELLED
    if status in {"blocked"}:
        return RunState.BLOCKED
    return RunState.FAILED


class LegacyOrchestrationCompositionBridge:
    def __init__(
        self,
        *,
        authority: ReasoningCompositionRuntimeAuthorityPort,
        policy: LegacyCompositionAuthorityPolicy,
    ) -> None:
        self.authority = authority
        self.policy = policy

    async def prepare(
        self,
        *,
        authenticated_context,
        task_ref: str,
        session_ref: str,
        objective: str,
        classification: dict[str, Any],
        snapshot: dict[str, Any],
        pattern_name: str,
        agent_configs: list[AgentConfig],
        trigger_artifacts: tuple[ExactArtifactReferenceV1Alpha1, ...] = (),
        activation_lineage=None,
        now: datetime | None = None,
    ) -> PreparedGovernedComposition:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        request_subject = _ref(
            "composition_request",
            "ace.orchestration.internal-composition-request/v1alpha1",
            {
                "task_ref": task_ref,
                "product_id": authenticated_context.product_id,
                "actor_ref": authenticated_context.actor_ref,
                "objective": objective,
                "triggers": [item.model_dump(mode="json") for item in trigger_artifacts],
            },
        )
        if not agent_configs:
            raise GovernedCompositionBridgeError("governed composition requires at least one execution unit")
        planning = []
        for _ in agent_configs:
            planning.append(
                await self.authority.resolve_planning(
                    authenticated_context=authenticated_context,
                    use_subject=request_subject,
                    participant_principal_ref=self.policy.participant_principal_ref,
                    authority_class=self.policy.authority_class,
                    operation=self.policy.operation,
                    grant_ref=self.policy.grant_ref,
                    scope_ref=self.policy.scope_ref,
                    policy_ref=self.policy.policy_ref,
                    evaluated_at=now,
                )
            )
        execution_participants = tuple(
            CompositionParticipantV1Alpha1(
                composition_participant_id=(
                    "composition_participant:"
                    + canonical_hash({"task": task_ref, "index": index, "role": config.role})[:32]
                ),
                participant_kind=ParticipantKind.ADAPTER,
                participant_ref=self.policy.participant_principal_ref,
                authority=planning[index].authority_coordinates,
                tool_refs=tuple(sorted(set(config.tools or ()))),
                source_scope_refs=(self.policy.scope_ref,),
            )
            for index, config in enumerate(agent_configs)
        )
        participants = execution_participants
        human_gate_participant = None
        if _pattern(pattern_name) == "human_gate":
            human_gate_participant = CompositionParticipantV1Alpha1(
                composition_participant_id=(
                    "composition_participant:"
                    + canonical_hash({"task": task_ref, "kind": "human_gate"})[:32]
                ),
                participant_kind=ParticipantKind.HUMAN,
                participant_ref=f"human_gate:{authenticated_context.actor_ref}",
                required=True,
            )
            participants = (*execution_participants, human_gate_participant)
        execution_nodes = []
        canonical_pattern = _pattern(pattern_name)
        for index, participant in enumerate(execution_participants):
            dependencies: tuple[str, ...] = ()
            if canonical_pattern == "pipeline" and index:
                dependencies = (execution_nodes[-1].node_id,)
            execution_nodes.append(
                CompositionNodeV1Alpha1(
                    node_id=f"execution:{index + 1}",
                    node_kind=CompositionNodeKind.EXECUTION,
                    composition_participant_id=participant.composition_participant_id,
                    depends_on=dependencies,
                    input_contracts=("ace.orchestration.legacy-task-input/v1",),
                    output_contracts=("ace.orchestration.legacy-contribution/v1",),
                    validator_refs=("validator:i2-contributor-v1",),
                    exit_criteria_refs=("exit:bounded-final-artifact-v1",),
                )
            )
        join_dependencies = tuple(item.node_id for item in execution_nodes)
        human_gate_node = None
        if human_gate_participant is not None:
            human_gate_node = CompositionNodeV1Alpha1(
                node_id="human_gate:1",
                node_kind=CompositionNodeKind.HUMAN_GATE,
                composition_participant_id=human_gate_participant.composition_participant_id,
                depends_on=join_dependencies,
                input_contracts=("ace.orchestration.legacy-contribution/v1",),
                output_contracts=("ace.orchestration.human-gate-disposition/v1",),
                validator_refs=("validator:authenticated-human-disposition-v1",),
                exit_criteria_refs=("exit:exact-human-disposition-receipt-v1",),
            )
            join_dependencies = (human_gate_node.node_id,)
        join = CompositionNodeV1Alpha1(
            node_id="join:1",
            node_kind=CompositionNodeKind.JOIN,
            depends_on=join_dependencies,
            input_contracts=("ace.orchestration.legacy-contribution/v1",),
            output_contracts=("ace.orchestration.legacy-synthesis/v1",),
            validator_refs=("validator:i2-synthesis-v1",),
            exit_criteria_refs=("exit:honest-partial-coverage-v1",),
        )
        handoff = CompositionNodeV1Alpha1(
            node_id="handoff:1",
            node_kind=CompositionNodeKind.HANDOFF,
            depends_on=(join.node_id,),
            input_contracts=("ace.orchestration.legacy-synthesis/v1",),
            output_contracts=("ace.orchestration.internal-stage-handoff/v1",),
            validator_refs=("validator:typed-internal-handoff-v1",),
            exit_criteria_refs=("exit:prepared-no-delivery-v1",),
        )
        context_material = {
            "task_ref": task_ref,
            "marker_map": snapshot.get("_marker_map") or {},
            "intelligence_trace": snapshot.get("_intelligence_use_trace") or {},
            "policy_ref": self.policy.context_policy_ref,
        }
        context_manifest = _ref(
            "context_manifest_projection",
            "ace.bridge.i3-context-manifest-coordinate/v1alpha1",
            context_material,
        )
        context_receipt = _ref(
            "context_selection_receipt",
            "ace.bridge.i3-context-selection-receipt/v1alpha1",
            context_material,
        )
        classifier_ref = _ref(
            "classification_contribution",
            "ace.bridge.classifier-contribution/v1alpha1",
            {"revision": self.policy.classifier_revision_ref, "classification": classification},
        )
        composition = classification.get("cognitive_composition")
        composer_material = (
            composition.model_dump(mode="json")
            if hasattr(composition, "model_dump")
            else getattr(composition, "__dict__", composition)
        )
        composer_ref = _ref(
            "composer_contribution",
            "ace.bridge.cognitive-composer-contribution/v1alpha1",
            {"revision": self.policy.composer_revision_ref, "composition": composer_material},
        )
        instruction_resolution = _ref(
            "instruction_resolution_receipt",
            "ace.intelligence.instruction-resolution-receipt/v1alpha1",
            {
                "task_ref": task_ref,
                "classifier": classifier_ref.model_dump(mode="json"),
                "composer": composer_ref.model_dump(mode="json"),
                "context": context_manifest.model_dump(mode="json"),
            },
        )
        plan = TaskCompositionPlanV1Alpha1(
            product_id=authenticated_context.product_id,
            actor_ref=authenticated_context.actor_ref,
            session_ref=session_ref,
            task_ref=task_ref,
            objective=objective,
            stage_id="deliberate",
            activation_lineage=activation_lineage,
            trigger_artifacts=trigger_artifacts,
            classifier_revision_ref=self.policy.classifier_revision_ref,
            routing_revision_ref=self.policy.routing_revision_ref,
            policy_revision_ref=self.policy.composition_policy_revision_ref,
            composer_revision_ref=self.policy.composer_revision_ref,
            participants=participants,
            nodes=tuple((*execution_nodes, *((human_gate_node,) if human_gate_node is not None else ()), join, handoff)),
            orchestration_pattern=canonical_pattern,
            expected_output_contracts=("ace.orchestration.legacy-synthesis/v1",),
            gate_refs=("gate:current-authority-pre-execution-v1",),
            allowed_next_stage_ids=("decide",),
            aggregate_budget=CompositionBudgetV1Alpha1(
                max_items=256,
                max_tokens=128_000,
                max_calls=max(1, len(agent_configs) * 8),
                max_latency_ms=max(item.timeout_s for item in agent_configs) * 1_000,
                max_concurrency=max(1, len(agent_configs)),
            ),
            context_request_ref=f"context_request:{canonical_hash(context_material)[:32]}",
            candidate_receipts=tuple(
                {
                    exact_reference(item.resolution_receipt): None
                    for item in planning
                }
            ),
            context_receipts=(context_receipt,),
            failure_policy_ref=self.policy.failure_policy_ref,
            created_at=now,
            expires_at=min(authenticated_context.expires_at, now + timedelta(minutes=30)),
        )
        plan_ref = exact_reference(plan)
        instruction_layers = (classifier_ref, composer_ref, context_manifest)
        manifests = tuple(
            StageRunManifestV1Alpha1(
                plan=plan_ref,
                product_id=plan.product_id,
                stage_id=plan.stage_id,
                node_id=execution_nodes[index].node_id,
                composition_participant_id=participant.composition_participant_id,
                task_ref=plan.task_ref,
                invocation_key=f"invocation:{plan.task_ref}:{index + 1}",
                instruction_resolution=instruction_resolution,
                instruction_layer_refs=instruction_layers,
                context_manifest=context_manifest,
                tool_refs=participant.tool_refs,
                source_scope_refs=participant.source_scope_refs,
                authority=participant.authority,
                execution_binding=exact_reference(planning[index].execution_binding),
                input_artifacts=trigger_artifacts,
                output_contracts=("ace.orchestration.legacy-contribution/v1",),
                validator_refs=("validator:i2-contributor-v1",),
                exit_criteria_refs=("exit:bounded-final-artifact-v1",),
                handoff_target_ref="stage_handoff_contract:internal-synthesis",
                budget=CompositionBudgetV1Alpha1(
                    max_items=64,
                    max_tokens=64_000,
                    max_calls=8,
                    max_latency_ms=agent_configs[index].timeout_s * 1_000,
                ),
                cancellation_ref="cancellation:task-runtime-v1",
                retry_ref="retry:fresh-authority-v1",
                idempotency_key=f"stage:{plan.task_ref}:{index + 1}",
                degraded_policy_ref="degraded:honest-partial-v1",
                escalation_policy_ref="escalation:human-review-v1",
                created_at=now,
                expires_at=plan.expires_at,
            )
            for index, participant in enumerate(execution_participants)
        )
        return PreparedGovernedComposition(
            plan=plan,
            manifests=manifests,
            planning_authority=tuple(planning),
            instruction_resolution=instruction_resolution,
            context_manifest=context_manifest,
        )

    async def authorize_execution(
        self,
        *,
        prepared: PreparedGovernedComposition,
        authenticated_context,
        now: datetime | None = None,
    ) -> tuple[ReasoningCompositionRuntimeAuthorityBundle, ...]:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        results = []
        for index, manifest in enumerate(prepared.manifests):
            resolved = await self.authority.resolve_pre_execution(
                    authenticated_context=authenticated_context,
                    manifest=manifest,
                    evaluated_at=now,
                )
            planned = prepared.planning_authority[index]
            if (
                resolved.execution_binding != planned.execution_binding
                or resolved.authority_coordinates != planned.authority_coordinates
                or resolved.current_heads != planned.current_heads
            ):
                raise GovernedCompositionBridgeError(
                    "current authority rotated between planning and pre-execution evaluation"
                )
            results.append(resolved)
        return tuple(results)

    def complete(
        self,
        *,
        prepared: PreparedGovernedComposition,
        execution_authority: tuple[ReasoningCompositionRuntimeAuthorityBundle, ...],
        pattern_result: PatternResult,
        snapshot: dict[str, Any],
        actual_route: ExactArtifactReferenceV1Alpha1 | None,
        now: datetime | None = None,
        attempt: int = 1,
        retry_of_receipt_refs: tuple[str | None, ...] = (),
    ) -> CompletedGovernedComposition:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        if len(execution_authority) != len(prepared.manifests):
            raise GovernedCompositionBridgeError("execution authority coverage does not match frozen manifests")
        results = list(pattern_result.agent_results or [])
        run_receipts = []
        for index, manifest in enumerate(prepared.manifests):
            result = results[index] if index < len(results) else None
            state = _run_state(result, pattern_result)
            output = str(getattr(result, "output", "") or "")
            output_artifacts = (
                (
                    _ref(
                        "contribution",
                        "ace.orchestration.legacy-contribution/v1",
                        {
                            "manifest": str(manifest.manifest_id),
                            "output": output,
                            "structured": getattr(result, "structured_output", None),
                        },
                    ),
                )
                if output
                else ()
            )
            issue_codes = []
            if result is None:
                issue_codes.append("ace.composition.contributor.missing")
            elif state == RunState.DEGRADED:
                issue_codes.append("ace.composition.contributor.timeout")
            elif state == RunState.ABSTAINED:
                issue_codes.append("ace.composition.contributor.abstained")
            elif state in {RunState.FAILED, RunState.CANCELLED}:
                issue_codes.append(f"ace.composition.contributor.{state.value}")
            duration = max(0, int(getattr(result, "duration_ms", 0) or 0))
            started_at = None if state == RunState.BLOCKED else now - timedelta(milliseconds=duration)
            receipt = StageRunReceiptV1Alpha1(
                plan=manifest.plan,
                manifest=exact_reference(manifest),
                product_id=manifest.product_id,
                composition_participant_id=manifest.composition_participant_id,
                attempt=attempt,
                state=state,
                started_at=started_at,
                ended_at=now,
                actual_route=actual_route,
                usage=UsageV1Alpha1(latency_ms=duration, calls=0 if state == RunState.BLOCKED else 1),
                actual_tool_refs=(),
                authority_exercised=manifest.authority if state not in {RunState.BLOCKED, RunState.CANCELLED} else (),
                output_artifacts=output_artifacts,
                context_states=_context_states(snapshot),
                issue_codes=tuple(issue_codes),
                retry_of_receipt_ref=(
                    retry_of_receipt_refs[index] if index < len(retry_of_receipt_refs) else None
                ),
            )
            validate_run_receipt_against_manifest(manifest, receipt)
            run_receipts.append(receipt)
        usable = tuple(item for receipt in run_receipts for item in receipt.output_artifacts)
        join_state = "complete"
        if not usable:
            join_state = "failed"
        elif any(item.state != RunState.COMPLETE for item in run_receipts):
            join_state = "partial"
        tainted = bool(
            any(isinstance(item, dict) and item.get("tainted") is True for item in snapshot.get("phase_traces", []))
        )
        join_evidence = _ref(
            "join_evidence",
            "ace.bridge.i2-join-evidence/v1alpha1",
            {
                "plan": str(prepared.plan.composition_plan_id),
                "runs": [exact_reference(item).model_dump(mode="json") for item in run_receipts],
                "state": join_state,
                "tainted": tainted,
                "missing": max(0, len(prepared.manifests) - len(results)),
                "i2_owner": "deliberation-receipt-v1",
            },
        )
        handoff_contract = StageHandoffContractV1Alpha1(
            source_stage_id=prepared.plan.stage_id,
            target_stage_id="decide",
            source_product_id=prepared.plan.product_id,
            target_product_id=prepared.plan.product_id,
            destination_kind="internal_task_synthesis",
            accepted_contracts=("ace.orchestration.legacy-synthesis/v1",),
            required_evidence_refs=(join_evidence.artifact_id,),
            required_policy_refs=(self.policy.failure_policy_ref,),
            completion_policy_ref="completion:honest-partial-v1",
            retry_policy_ref="retry:fresh-authority-v1",
            acknowledgment_policy_ref="ack:internal-receipt-v1",
            allowed_next_stage_ids=("decide",),
        )
        handoff_state = HandoffState.PREPARED
        if join_state == "partial" or tainted:
            handoff_state = HandoffState.PARTIAL
        elif join_state == "failed":
            handoff_state = HandoffState.FAILED
        handoff_receipt = StageHandoffReceiptV1Alpha1(
            handoff_contract=exact_reference(handoff_contract),
            source_plan=exact_reference(prepared.plan),
            source_runs=tuple(exact_reference(item) for item in run_receipts),
            target_ref="task_synthesis:internal",
            artifacts=usable,
            authority_used=(),
            policy_refs=(self.policy.failure_policy_ref,),
            state=handoff_state,
            external_send_occurred=False,
            omitted_refs=tuple(
                str(item.receipt_id)
                for item in run_receipts
                if item.state not in {RunState.COMPLETE, RunState.PARTIAL}
            ),
            idempotency_key=f"handoff:{prepared.plan.composition_plan_id}",
            occurred_at=now,
        )
        return CompletedGovernedComposition(
            plan=prepared.plan,
            manifests=prepared.manifests,
            run_receipts=tuple(run_receipts),
            join_evidence=join_evidence,
            handoff_contract=handoff_contract,
            handoff_receipt=handoff_receipt,
            planning_authority_receipts=tuple(
                exact_reference(item.resolution_receipt) for item in prepared.planning_authority
            ),
            execution_authority_receipts=tuple(
                exact_reference(item.resolution_receipt) for item in execution_authority
            ),
        )


__all__ = [
    "CompletedGovernedComposition",
    "GovernedCompositionBridgeError",
    "LegacyCompositionAuthorityPolicy",
    "LegacyOrchestrationCompositionBridge",
    "PreparedGovernedComposition",
]
