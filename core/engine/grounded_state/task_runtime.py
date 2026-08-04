"""Production task bridge for TP6 rollout use and TP7 governed promotion.

The extension prepares immutable task-bound material before orchestration.  This
module runs only after Core has persisted the real terminal task receipt, so I3
and promotion lineage bind actual execution rather than an evaluator fixture.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from core.engine.core.db import parse_one, parse_record_id
from core.engine.grounded_state.belief_contracts import BeliefStateProjectionV1, ReviewAuthority
from core.engine.grounded_state.belief_persistence import BeliefStateStore
from core.engine.grounded_state.contracts import canonical_hash
from core.engine.grounded_state.promotion import PromotionService, build_promotion_proposal
from core.engine.grounded_state.promotion_contracts import PromotionMaterialV1
from core.engine.grounded_state.rollout_contracts import ReasoningEvidencePackV1
from core.engine.grounded_state.rollouts import ConsequenceRolloutService, build_reasoning_use_receipt
from core.engine.grounded_state.transition_contracts import TransitionHypothesisRevisionV1
from core.engine.grounded_state.transition_persistence import TransitionStore
from core.engine.product.decision_receipts import normalize_decision_receipt

TASK_RUNTIME_CONTRACT = "ace.grounded-state.task-runtime/v1"
_DECISION_FIELDS = (
    "selected_option",
    "scope",
    "assumptions",
    "alternatives",
    "reconsideration_conditions",
    "evidence_refs",
)
_MATCHED_DIMENSIONS = (
    "task_hash",
    "provider",
    "model",
    "configuration",
    "decision_schema",
    "toolset",
)


class StateEngineTaskRuntimeError(RuntimeError):
    """A task-bound State Engine completion could not be proven exactly."""


async def _task(pool, task_id: str, *, product_id: str) -> dict[str, Any]:
    async with pool.connection() as db:
        row = parse_one(
            await db.query(
                "SELECT * FROM ONLY <record>$task WHERE product = $product LIMIT 1",
                {"task": task_id, "product": parse_record_id(product_id)},
            )
        )
    if not row:
        raise StateEngineTaskRuntimeError("state-engine task is unavailable in trusted product scope")
    return row


def _coordinates(extension_invocation: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(extension_invocation, dict):
        return None
    value = extension_invocation.get("runtime_coordinates")
    if not isinstance(value, dict) or value.get("contract_version") != TASK_RUNTIME_CONTRACT:
        return None
    return value


def _output_hash(output: object) -> str:
    return hashlib.sha256(str(output or "").encode("utf-8")).hexdigest()


def _route(task: dict[str, Any]) -> tuple[object, object]:
    provenance = (task.get("reasoning_trace") or {}).get("provenance") or {}
    return provenance.get("provider"), provenance.get("model")


def _configuration(task: dict[str, Any]) -> str:
    options = task.get("request_options") if isinstance(task.get("request_options"), dict) else {}
    return canonical_hash(
        {
            "model": options.get("model"),
            "deep": bool(options.get("deep", False)),
            "force_skill": options.get("force_skill"),
            "frameworks_hint": options.get("frameworks_hint"),
        }
    )


async def _matched_control(
    pool,
    *,
    treatment: dict[str, Any],
    coordinates: dict[str, Any],
    product_id: str,
    reflected_ids: set[str],
) -> dict[str, Any] | None:
    control_task_id = coordinates.get("matched_control_task_id")
    if not control_task_id:
        return None
    control = await _task(pool, str(control_task_id), product_id=product_id)
    control_coordinates = _coordinates(control.get("extension_invocation"))
    if not control_coordinates or control_coordinates.get("mode") != "control":
        raise StateEngineTaskRuntimeError("matched control must be a completed state-engine control task")
    if control.get("status") != "completed":
        raise StateEngineTaskRuntimeError("matched state-engine control task is not complete")

    treatment_decision = normalize_decision_receipt(treatment.get("decision_receipt"), task=treatment)
    control_decision = normalize_decision_receipt(control.get("decision_receipt"), task=control)
    changed = tuple(field for field in _DECISION_FIELDS if treatment_decision.get(field) != control_decision.get(field))
    treatment_provider, treatment_model = _route(treatment)
    control_provider, control_model = _route(control)
    matches = {
        "task_hash": coordinates.get("comparison_basis_hash") == control_coordinates.get("comparison_basis_hash"),
        "provider": treatment_provider == control_provider,
        "model": treatment_model == control_model,
        "configuration": _configuration(treatment) == _configuration(control),
        "decision_schema": (treatment_decision.get("contract_version") == control_decision.get("contract_version")),
        "toolset": (
            (treatment.get("extension_invocation") or {}).get("capability")
            == (control.get("extension_invocation") or {}).get("capability")
        ),
    }
    treatment_hash = _output_hash(treatment.get("output"))
    control_hash = _output_hash(control.get("output"))
    matched = all(matches.values()) and treatment_hash != control_hash and bool(changed)
    return {
        "state": "matched" if matched else "unmatched",
        "comparison_id": f"state_engine_comparison:{canonical_hash({'treatment': str(treatment.get('id')), 'control': str(control.get('id'))})[:32]}",
        "matched_dimensions": [name for name in _MATCHED_DIMENSIONS if matches[name]],
        "treatment_output_hash": treatment_hash,
        "control_output_hash": control_hash,
        "changed_decision_fields": list(changed),
        "material_item_ids": sorted(reflected_ids) if matched else [],
    }


async def complete_state_engine_task(
    *,
    pool,
    task_id: str,
    product_id: str,
    extension_invocation: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Persist task-specific TP6 I3 and an optional TP7 proposal."""
    coordinates = _coordinates(extension_invocation)
    if coordinates is None:
        return None
    if coordinates.get("task_id") != task_id or coordinates.get("product_id") != product_id:
        raise StateEngineTaskRuntimeError("state-engine runtime coordinates do not bind the durable task scope")

    task = await _task(pool, task_id, product_id=product_id)
    base = {
        "contract_version": TASK_RUNTIME_CONTRACT,
        "mode": coordinates.get("mode"),
        "task_id": task_id,
        "product_id": product_id,
        "comparison_basis_hash": coordinates.get("comparison_basis_hash"),
    }
    if coordinates.get("mode") == "control":
        return {**base, "completion_state": "control_completed"}
    if coordinates.get("mode") != "rollout":
        return None

    rollout_id = str(coordinates.get("rollout_revision_id") or "")
    if not rollout_id:
        raise StateEngineTaskRuntimeError("rollout task is missing its immutable rollout revision")
    service = ConsequenceRolloutService(pool)
    rollout = await service.replay_rollout(rollout_id, product_id=product_id)
    if rollout.task_id != task_id or rollout.rollout_revision_hash != coordinates.get("rollout_revision_hash"):
        raise StateEngineTaskRuntimeError("persisted rollout does not bind the actual task execution")
    context_pack = await service.rollout_store.require(
        ReasoningEvidencePackV1,
        str(coordinates.get("context_pack_id") or ""),
        product_id=product_id,
    )
    if context_pack.context_pack_hash != coordinates.get("context_pack_hash"):
        raise StateEngineTaskRuntimeError("persisted reasoning context does not match task runtime coordinates")

    output = str(task.get("output") or "")
    marker_rows = coordinates.get("consequence_markers") or []
    reflected_ids = {
        str(item.get("item_id"))
        for item in marker_rows
        if isinstance(item, dict) and str(item.get("marker") or "") in output and item.get("item_id")
    }
    matched_control = await _matched_control(
        pool,
        treatment=task,
        coordinates=coordinates,
        product_id=product_id,
        reflected_ids=reflected_ids,
    )
    reasoning_use = build_reasoning_use_receipt(
        rollout,
        context_pack=context_pack,
        reflected_item_ids=reflected_ids,
        matched_control=matched_control,
    )
    await service.persist_reasoning_use(reasoning_use)

    result: dict[str, Any] = {
        **base,
        "completion_state": "reasoning_use_persisted",
        "rollout_revision_id": str(rollout.rollout_revision_id),
        "rollout_revision_hash": str(rollout.rollout_revision_hash),
        "reasoning_use_receipt_id": str(reasoning_use.receipt_id),
        "reasoning_use_receipt_hash": str(reasoning_use.receipt_hash),
        "retrieved_count": len(reasoning_use.items),
        "injected_count": sum(item.injected for item in reasoning_use.items),
        "reflected_count": sum(item.reflected for item in reasoning_use.items),
        "decision_material_count": sum(item.decision_material for item in reasoning_use.items),
        "comparison_state": reasoning_use.comparison_state,
    }

    raw_material = coordinates.get("promotion_material")
    if raw_material is not None:
        material = PromotionMaterialV1.model_validate(raw_material)
        belief_store = BeliefStateStore(pool)
        projection = await belief_store.require(
            BeliefStateProjectionV1,
            str(coordinates.get("projection_id") or ""),
            product_id=product_id,
        )
        revision_ids = tuple(str(value) for value in coordinates.get("transition_revision_ids") or ())
        transition_store = TransitionStore(pool)
        revisions = tuple(
            [
                await transition_store.require(
                    TransitionHypothesisRevisionV1,
                    revision_id,
                    product_id=product_id,
                )
                for revision_id in revision_ids
            ]
        )
        proposal = build_promotion_proposal(
            task=task,
            material=material,
            context_pack=context_pack,
            projection=projection,
            transition_revisions=revisions,
            rollout=rollout,
            reasoning_use=reasoning_use,
            proposer_authority=ReviewAuthority.HUMAN,
            proposer_ref=str(task.get("user") or "authenticated_user"),
            proposed_at=datetime.now(timezone.utc),
            provenance={
                "contract_version": TASK_RUNTIME_CONTRACT,
                "task_id": task_id,
                "invocation_id": rollout.invocation_id,
                "reasoning_use_receipt_id": str(reasoning_use.receipt_id),
                "source_instruction_authority": False,
            },
            correction_observation_id=(
                str(coordinates["correction_observation_id"]) if coordinates.get("correction_observation_id") else None
            ),
            prior_promotion_receipt_ids=tuple(
                str(value) for value in coordinates.get("prior_promotion_receipt_ids") or ()
            ),
        )
        await PromotionService(pool).propose(proposal)
        result.update(
            {
                "completion_state": "promotion_proposed",
                "promotion_proposal_id": str(proposal.proposal_id),
                "promotion_proposal_hash": str(proposal.proposal_hash),
            }
        )
    return result


async def record_promoted_memory_task_use(
    *,
    pool,
    task_id: str,
    product_id: str,
    trace: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Persist TP7 later-use I3 when authoritative promoted memory entered a real task.

    A runtime trace may already contain an exact matched comparison.  Preserve
    that recorded material so the production bridge can establish bounded
    decision-material use; never synthesize a comparison from task prose.
    """
    trace = trace if isinstance(trace, dict) else {}
    rows = [
        item
        for item in (trace.get("items") or [])
        if isinstance(item, dict) and (item.get("provenance") or {}).get("promotion_receipt_id")
    ]
    if not rows:
        return None
    service = PromotionService(pool)
    authoritative = await service.retrieve(product_id=product_id, limit=20)
    requested_ids = {str(item.get("id")) for item in rows}
    memories = [item for item in authoritative if item.memory_id in requested_ids]
    if not memories:
        raise StateEngineTaskRuntimeError("promoted-memory runtime trace has no authoritative product-scoped memory")
    injected = {str(item.get("id")) for item in rows if item.get("injected", True)}
    reflected = set(trace.get("reflected_ids") or ())
    comparison = trace.get("comparison") if isinstance(trace.get("comparison"), dict) else None
    return await service.record_later_use(
        product_id=product_id,
        task_id=task_id,
        memories=memories,
        injected_ids=injected,
        reflected_ids=reflected,
        comparison=comparison,
    )
