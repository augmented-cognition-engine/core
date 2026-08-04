"""Provider-neutral TP7 promotion, correction, retrieval, and I3 integration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.engine.core.db import parse_one, parse_record_id
from core.engine.grounded_state.belief_contracts import BeliefStateProjectionV1, ReviewAuthority
from core.engine.grounded_state.belief_persistence import BeliefStateStore
from core.engine.grounded_state.contracts import canonical_hash
from core.engine.grounded_state.operations import StateEngineOperationsService
from core.engine.grounded_state.promotion_contracts import (
    TP7_PROMOTION_REVIEW_POLICY_VERSION,
    PromotedMemoryProjectionV1,
    PromotionDisposition,
    PromotionEffectiveState,
    PromotionEvidenceVersionV1,
    PromotionMaterialV1,
    PromotionMemoryLineageV1,
    PromotionMemoryMeaning,
    PromotionProposalV1,
    PromotionReceiptV1,
    PromotionReviewV1,
    PromotionTargetKind,
    PromotionTransitionRevisionV1,
)
from core.engine.grounded_state.promotion_persistence import (
    PromotionProductScopeError,
    PromotionStore,
)
from core.engine.grounded_state.rollout_contracts import (
    ConsequenceRolloutRevisionV1,
    EvidenceCoverageState,
    ReasoningContextUseReceiptV1,
    ReasoningEvidencePackV1,
    RolloutDisposition,
)
from core.engine.grounded_state.rollout_persistence import RolloutStore
from core.engine.grounded_state.transition_contracts import TransitionHypothesisRevisionV1
from core.engine.grounded_state.transition_persistence import TransitionStore
from core.engine.product.decision_receipts import normalize_decision_receipt
from core.engine.product.intelligence_use import build_intelligence_use_receipt

_ALLOWLISTED_POLICY_RULES = {
    "tp7-stable-preference-v1": PromotionTargetKind.STABLE_PREFERENCE,
}
_COVERAGE_PRECEDENCE = {
    EvidenceCoverageState.REJECTED: 90,
    EvidenceCoverageState.TRUNCATED: 80,
    EvidenceCoverageState.STALE: 70,
    EvidenceCoverageState.CONTESTED: 60,
    EvidenceCoverageState.MISSING: 50,
    EvidenceCoverageState.UNKNOWN: 40,
    EvidenceCoverageState.SUPERSEDED: 30,
    EvidenceCoverageState.PROVISIONAL: 20,
    EvidenceCoverageState.SUPPORTED: 10,
}


class PromotionEligibilityError(RuntimeError):
    """Exact promotion lineage is unavailable or ineligible."""


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    return str(value)


def _record_ref(value: Any) -> str:
    """Normalize SurrealDB v3 escaped record IDs into contract references."""
    text = str(value or "")
    table, separator, key = text.partition(":")
    if not separator:
        return text
    return f"{table}:{key.strip('⟨⟩<>')}"


def task_receipt_material(task: dict[str, Any]) -> dict[str, Any]:
    """Freeze stable task/decision facts without volatile feedback projections."""
    decision = normalize_decision_receipt(task.get("decision_receipt"), task=task)
    return _json_safe(
        {
            "task_id": _record_ref(task.get("id")),
            "product_id": _record_ref(task.get("product")),
            "status": str(task.get("status") or ""),
            "decision_receipt": decision,
            "deliberation_receipt_id": (task.get("deliberation_receipt") or {}).get("receipt_id"),
            "extension_receipt_id": (task.get("extension_receipt") or {}).get("receipt_id"),
        }
    )


def task_receipt_hash(task: dict[str, Any]) -> str:
    return canonical_hash(task_receipt_material(task))


def _coverage_for_record(context_pack: ReasoningEvidencePackV1, record_id: str) -> EvidenceCoverageState:
    states = [item.state for item in context_pack.coverage if record_id in item.evidence_refs]
    return max(states, key=_COVERAGE_PRECEDENCE.__getitem__) if states else EvidenceCoverageState.SUPPORTED


def build_promotion_proposal(
    *,
    task: dict[str, Any],
    material: PromotionMaterialV1,
    context_pack: ReasoningEvidencePackV1,
    projection: BeliefStateProjectionV1,
    transition_revisions: tuple[TransitionHypothesisRevisionV1, ...],
    rollout: ConsequenceRolloutRevisionV1,
    reasoning_use: ReasoningContextUseReceiptV1,
    proposer_authority: ReviewAuthority,
    proposer_ref: str,
    proposed_at: datetime,
    provenance: dict[str, Any],
    correction_observation_id: str | None = None,
    prior_promotion_receipt_ids: tuple[str, ...] = (),
) -> PromotionProposalV1:
    """Build a proposal from exact TP4–TP6 and I1 lineage without authorizing it."""
    normalized_decision = normalize_decision_receipt(task.get("decision_receipt"), task=task)
    decision_id = normalized_decision.get("decision_id")
    if not decision_id:
        raise PromotionEligibilityError("promotion requires an exact structured I1 decision receipt")
    task_product_id = _record_ref(task.get("product"))
    task_id = _record_ref(task.get("id"))
    if task_product_id != context_pack.product_id or task_id != context_pack.task_id:
        raise PromotionEligibilityError(
            "promotion task must share exact context-pack product and task scope "
            f"(task={task_id}, context_task={context_pack.task_id}, "
            f"product={task_product_id}, context_product={context_pack.product_id})"
        )
    evidence_versions = tuple(
        PromotionEvidenceVersionV1(
            product_id=context_pack.product_id,
            record_id=item.endpoint.record_id,
            record_kind=item.endpoint.kind.value,
            record_version=item.endpoint.record_version,
            content_hash=item.endpoint.content_hash,
            coverage_state=_coverage_for_record(context_pack, item.endpoint.record_id),
        )
        for item in context_pack.evidence_pack.items
    )
    contested = tuple(
        item.record_id for item in evidence_versions if item.coverage_state is EvidenceCoverageState.CONTESTED
    )
    degraded = tuple(
        sorted(
            {
                *context_pack.degraded_reasons,
                *context_pack.evidence_pack.degraded_reasons,
            }
        )
    )
    return PromotionProposalV1(
        product_id=context_pack.product_id,
        material=material,
        task_id=context_pack.task_id,
        task_receipt_hash=task_receipt_hash(task),
        decision_receipt_id=str(decision_id),
        decision_receipt_hash=canonical_hash(_json_safe(normalized_decision)),
        context_pack_id=str(context_pack.context_pack_id),
        context_pack_hash=str(context_pack.context_pack_hash),
        evidence_pack_id=str(context_pack.evidence_pack.pack_id),
        evidence_pack_hash=str(context_pack.evidence_pack.pack_hash),
        evidence_versions=evidence_versions,
        belief_projection_id=str(projection.projection_id),
        belief_projection_hash=str(projection.projection_hash),
        transition_revisions=tuple(
            PromotionTransitionRevisionV1(
                revision_id=str(revision.revision_id),
                revision_hash=str(revision.revision_hash),
            )
            for revision in transition_revisions
        ),
        rollout_revision_id=str(rollout.rollout_revision_id),
        rollout_revision_hash=str(rollout.rollout_revision_hash),
        reasoning_use_receipt_id=str(reasoning_use.receipt_id),
        reasoning_use_receipt_hash=str(reasoning_use.receipt_hash),
        proposer_authority=proposer_authority,
        proposer_ref=proposer_ref,
        proposed_at=proposed_at,
        provenance=provenance,
        correction_observation_id=correction_observation_id,
        prior_promotion_receipt_ids=prior_promotion_receipt_ids,
        omissions=tuple(sorted({*context_pack.omissions, *context_pack.evidence_pack.omissions})),
        failures=tuple(sorted({*context_pack.failures, *context_pack.evidence_pack.failures})),
        degraded_reasons=degraded,
        contested_input_refs=contested,
    )


def _memory_identity(proposal: PromotionProposalV1) -> tuple[str, str]:
    memory_material = {
        "product_id": proposal.product_id,
        "target_kind": proposal.material.target_kind.value,
        "memory_meaning": proposal.material.memory_meaning.value,
        "content_hash": proposal.material.content_hash,
        "proposal_id": proposal.proposal_id,
        "prior_promotion_receipt_ids": proposal.prior_promotion_receipt_ids,
    }
    memory_hash = canonical_hash(memory_material)
    return f"insight:promotion_{memory_hash[:24]}", memory_hash


def _insight_type(meaning: PromotionMemoryMeaning) -> str:
    return {
        PromotionMemoryMeaning.DURABLE_CONCLUSION: "discovery",
        PromotionMemoryMeaning.DECISION: "decision",
        PromotionMemoryMeaning.CORRECTION: "correction",
        PromotionMemoryMeaning.PREFERENCE: "preference",
        PromotionMemoryMeaning.PATTERN: "pattern",
    }[meaning]


def promoted_memory_as_insight(item: PromotedMemoryProjectionV1) -> dict[str, Any]:
    """Project authoritative TP7 memory into the existing insight read shape."""
    return {
        "id": item.memory_id,
        "content": item.content,
        "confidence": 1.0,
        "tier": "product",
        "insight_type": _insight_type(item.memory_meaning),
        "product": item.product_id,
        "trust": 1.0,
        "status": item.effective_state.value,
        "created_at": item.created_at,
        "tags": list(item.tags),
        "domain_path": item.domain_path,
        "source_observations": [],
        "source_kind": "grounded_promotion",
        "source_ref": item.receipt_id,
        "source_graph": item.lineage_id,
        "promotion_receipt_id": item.receipt_id,
        "promotion_receipt_hash": item.receipt_hash,
        "promotion_evidence_pack_id": item.evidence_pack_id,
        "promotion_evidence_pack_hash": item.evidence_pack_hash,
        "promotion_lineage_id": item.lineage_id,
        "promotion_material_hash": item.memory_hash,
    }


class PromotionService:
    """Orchestrate exact TP7 proposal, review, memory, and correction lineage."""

    def __init__(self, pool) -> None:
        self.pool = pool
        self.store = PromotionStore(pool)
        self.rollouts = RolloutStore(pool)
        self.beliefs = BeliefStateStore(pool)
        self.transitions = TransitionStore(pool)

    async def propose(self, proposal: PromotionProposalV1) -> PromotionProposalV1:
        await self._verify_lineage(proposal)
        await self.store.persist(proposal)
        return proposal

    async def _task(self, task_id: str, *, product_id: str) -> dict[str, Any]:
        async with self.pool.connection() as db:
            row = parse_one(
                await db.query(
                    "SELECT * FROM ONLY <record>$task WHERE product = $product LIMIT 1",
                    {"task": parse_record_id(task_id), "product": parse_record_id(product_id)},
                )
            )
        if not row:
            raise PromotionProductScopeError("promotion task is unavailable in product scope")
        return row

    async def _verify_lineage(self, proposal: PromotionProposalV1) -> dict[str, Any]:
        task = await self._task(proposal.task_id, product_id=proposal.product_id)
        if task_receipt_hash(task) != proposal.task_receipt_hash:
            raise PromotionEligibilityError("promotion task receipt hash is missing, stale, or conflicting")
        decision = normalize_decision_receipt(task.get("decision_receipt"), task=task)
        if (
            decision.get("decision_id") != proposal.decision_receipt_id
            or canonical_hash(_json_safe(decision)) != proposal.decision_receipt_hash
        ):
            raise PromotionEligibilityError("promotion decision receipt lineage is missing, stale, or conflicting")

        context_pack = await self.rollouts.require(
            ReasoningEvidencePackV1,
            proposal.context_pack_id,
            product_id=proposal.product_id,
        )
        projection = await self.beliefs.require(
            BeliefStateProjectionV1,
            proposal.belief_projection_id,
            product_id=proposal.product_id,
        )
        rollout = await self.rollouts.require(
            ConsequenceRolloutRevisionV1,
            proposal.rollout_revision_id,
            product_id=proposal.product_id,
        )
        use = await self.rollouts.require(
            ReasoningContextUseReceiptV1,
            proposal.reasoning_use_receipt_id,
            product_id=proposal.product_id,
        )
        revisions = tuple(
            [
                await self.transitions.require(
                    TransitionHypothesisRevisionV1,
                    item.revision_id,
                    product_id=proposal.product_id,
                )
                for item in proposal.transition_revisions
            ]
        )
        exact_evidence = tuple(
            PromotionEvidenceVersionV1(
                product_id=context_pack.product_id,
                record_id=item.endpoint.record_id,
                record_kind=item.endpoint.kind.value,
                record_version=item.endpoint.record_version,
                content_hash=item.endpoint.content_hash,
                coverage_state=_coverage_for_record(context_pack, item.endpoint.record_id),
            )
            for item in context_pack.evidence_pack.items
        )
        checks = {
            "context_pack": (
                context_pack.context_pack_hash == proposal.context_pack_hash
                and context_pack.evidence_pack.pack_id == proposal.evidence_pack_id
                and context_pack.evidence_pack.pack_hash == proposal.evidence_pack_hash
            ),
            "evidence_versions": exact_evidence == proposal.evidence_versions,
            "projection": (
                projection.projection_hash == proposal.belief_projection_hash
                and projection.evidence_pack_id == proposal.evidence_pack_id
                and projection.evidence_pack_hash == proposal.evidence_pack_hash
            ),
            "transitions": all(
                revision.revision_hash == item.revision_hash
                for revision, item in zip(revisions, proposal.transition_revisions, strict=True)
            ),
            "rollout": (
                rollout.rollout_revision_hash == proposal.rollout_revision_hash
                and rollout.task_id == proposal.task_id
                and rollout.context_pack_id == proposal.context_pack_id
                and rollout.context_pack_hash == proposal.context_pack_hash
                and rollout.starting_projection_id == proposal.belief_projection_id
                and rollout.starting_projection_hash == proposal.belief_projection_hash
                and tuple(rollout.transition_revision_ids)
                == tuple(item.revision_id for item in proposal.transition_revisions)
            ),
            "reasoning_use": (
                use.receipt_hash == proposal.reasoning_use_receipt_hash
                and use.task_id == proposal.task_id
                and use.rollout_revision_id == proposal.rollout_revision_id
                and use.rollout_revision_hash == proposal.rollout_revision_hash
                and use.context_pack_id == proposal.context_pack_id
                and use.context_pack_hash == proposal.context_pack_hash
            ),
        }
        failed = sorted(name for name, passed in checks.items() if not passed)
        if failed:
            raise PromotionEligibilityError(f"promotion exact-lineage checks failed: {', '.join(failed)}")

        prior_receipts = [
            await self.store.require(PromotionReceiptV1, receipt_id, product_id=proposal.product_id)
            for receipt_id in proposal.prior_promotion_receipt_ids
        ]
        if proposal.material.target_kind is PromotionTargetKind.CORRECTION:
            await self._verify_correction_observation(proposal)
            states = await self.store.effective_states(product_id=proposal.product_id)
            if any(states.get(str(item.receipt_id)) is not PromotionEffectiveState.ACTIVE for item in prior_receipts):
                raise PromotionEligibilityError("correction promotion must extend active authoritative memory")
        return {
            "task": task,
            "context_pack": context_pack,
            "projection": projection,
            "rollout": rollout,
            "reasoning_use": use,
            "transitions": revisions,
            "prior_receipts": prior_receipts,
        }

    async def _verify_correction_observation(self, proposal: PromotionProposalV1) -> None:
        async with self.pool.connection() as db:
            correction = parse_one(
                await db.query(
                    "SELECT id, product, observation_type, correction_contract_version, lifecycle_state "
                    "FROM ONLY <record>$observation WHERE product = $product LIMIT 1",
                    {
                        "observation": parse_record_id(str(proposal.correction_observation_id)),
                        "product": parse_record_id(proposal.product_id),
                    },
                )
            )
        if not correction:
            raise PromotionProductScopeError("correction observation is unavailable in product scope")
        if (
            correction.get("observation_type") != "correction"
            or correction.get("correction_contract_version") != "correction-v1"
            or correction.get("lifecycle_state") not in {None, "active"}
        ):
            raise PromotionEligibilityError("promotion correction requires an active exact I1 correction record")

    @staticmethod
    def _eligibility_failures(
        proposal: PromotionProposalV1,
        lineage: dict[str, Any],
        *,
        authority: ReviewAuthority,
        deterministic_rule_id: str | None,
    ) -> list[str]:
        failures = [*proposal.failures, *proposal.omissions, *proposal.degraded_reasons]
        failures.extend(
            f"evidence_{item.coverage_state.value}:{item.record_id}"
            for item in proposal.evidence_versions
            if item.coverage_state is not EvidenceCoverageState.SUPPORTED
        )
        if proposal.contested_input_refs:
            failures.append("contested_support")
        rollout: ConsequenceRolloutRevisionV1 = lineage["rollout"]
        if rollout.disposition is not RolloutDisposition.ELIGIBLE:
            failures.append(f"rollout_{rollout.disposition.value}")
        use: ReasoningContextUseReceiptV1 = lineage["reasoning_use"]
        # Human review may accept an explicitly reflected, exactly attributed
        # grounded conclusion even when a matched control has not established
        # decision materiality.  Deterministic policy remains stricter.  This
        # never upgrades reflection into benefit or decision-material credit.
        if authority is ReviewAuthority.HUMAN:
            if not any(item.reflected for item in use.items):
                failures.append("reasoning_not_reflected")
        elif not any(item.decision_material for item in use.items):
            failures.append("reasoning_not_decision_material")
        if authority is ReviewAuthority.DETERMINISTIC_POLICY:
            if _ALLOWLISTED_POLICY_RULES.get(str(deterministic_rule_id)) is not proposal.material.target_kind:
                failures.append("deterministic_policy_rule_not_authorized_for_target")
        return sorted(set(failures))

    async def review(
        self,
        *,
        proposal_id: str,
        product_id: str,
        disposition: PromotionDisposition,
        authority: ReviewAuthority,
        reviewer_ref: str,
        authority_scope: str,
        rationale: str,
        reviewed_at: datetime,
        deterministic_rule_id: str | None = None,
        expires_at: datetime | None = None,
        supersedes_receipt_ids: tuple[str, ...] = (),
        invalidates_receipt_ids: tuple[str, ...] = (),
        contests_receipt_ids: tuple[str, ...] = (),
    ) -> PromotionReceiptV1:
        proposal = await self.store.require(PromotionProposalV1, proposal_id, product_id=product_id)
        lineage = await self._verify_lineage(proposal)
        review = PromotionReviewV1(
            product_id=product_id,
            proposal_id=str(proposal.proposal_id),
            proposal_hash=str(proposal.proposal_hash),
            disposition=disposition,
            authority=authority,
            reviewer_ref=reviewer_ref,
            authority_scope=authority_scope,
            rationale=rationale,
            reviewed_at=reviewed_at,
            policy_version=TP7_PROMOTION_REVIEW_POLICY_VERSION,
            deterministic_rule_id=deterministic_rule_id,
        )
        final_disposition = disposition
        reasons: tuple[str, ...] = ()
        if disposition is PromotionDisposition.ACCEPTED:
            failures = self._eligibility_failures(
                proposal,
                lineage,
                authority=authority,
                deterministic_rule_id=deterministic_rule_id,
            )
            if failures:
                final_disposition = (
                    PromotionDisposition.CONTESTED
                    if proposal.contested_input_refs
                    else PromotionDisposition.DEGRADED
                    if proposal.degraded_reasons or proposal.omissions
                    else PromotionDisposition.FAILED
                )
                reasons = tuple(failures)

        if proposal.material.target_kind is PromotionTargetKind.CORRECTION:
            supersedes_receipt_ids = tuple(sorted({*supersedes_receipt_ids, *proposal.prior_promotion_receipt_ids}))
        related = {*supersedes_receipt_ids, *invalidates_receipt_ids, *contests_receipt_ids}
        for related_id in sorted(related):
            await self.store.require(PromotionReceiptV1, related_id, product_id=product_id)

        memory_id: str | None = None
        memory_hash: str | None = None
        if final_disposition is PromotionDisposition.ACCEPTED:
            memory_id, memory_hash = _memory_identity(proposal)
        receipt = PromotionReceiptV1(
            product_id=product_id,
            proposal_id=str(proposal.proposal_id),
            proposal_hash=str(proposal.proposal_hash),
            review_id=str(review.review_id),
            review_hash=str(review.review_hash),
            disposition=final_disposition,
            memory_id=memory_id,
            memory_hash=memory_hash,
            supersedes_receipt_ids=supersedes_receipt_ids,
            invalidates_receipt_ids=invalidates_receipt_ids,
            contests_receipt_ids=contests_receipt_ids,
            expires_at=expires_at,
            effective_at=reviewed_at,
            reasons=reasons,
        )
        memory_lineage: PromotionMemoryLineageV1 | None = None
        memory: dict[str, Any] | None = None
        if final_disposition is PromotionDisposition.ACCEPTED:
            prior_lineages = [
                item
                for item in await self.store.list_records(PromotionMemoryLineageV1, product_id=product_id)
                if item.receipt_id in supersedes_receipt_ids
            ]
            memory_lineage = PromotionMemoryLineageV1(
                product_id=product_id,
                memory_id=str(memory_id),
                memory_hash=str(memory_hash),
                proposal_id=str(proposal.proposal_id),
                proposal_hash=str(proposal.proposal_hash),
                receipt_id=str(receipt.receipt_id),
                receipt_hash=str(receipt.receipt_hash),
                task_id=proposal.task_id,
                decision_receipt_id=proposal.decision_receipt_id,
                evidence_pack_id=proposal.evidence_pack_id,
                evidence_pack_hash=proposal.evidence_pack_hash,
                rollout_revision_id=proposal.rollout_revision_id,
                rollout_revision_hash=proposal.rollout_revision_hash,
                predecessor_memory_ids=tuple(item.memory_id for item in prior_lineages),
                correction_observation_id=proposal.correction_observation_id,
                created_at=reviewed_at,
            )
            memory = {
                "id": memory_id,
                "content": proposal.material.content,
                "insight_type": _insight_type(proposal.material.memory_meaning),
                "tier": "product",
                "clearance": "open",
                "confidence": 1.0 if authority is ReviewAuthority.HUMAN else 0.9,
                "source_domain": "state_engine_tp7",
                "domain_path": proposal.material.domain_path,
                # Existing runtime retrieval is tag-indexed by discipline. Keep
                # the exact promotion tags and add the bound domain path so the
                # ordinary loader can discover this existing insight row.
                "tags": sorted({*proposal.material.tags, proposal.material.domain_path}),
                "status": "active",
                "source_kind": "grounded_promotion",
                "source_ref": receipt.receipt_id,
                "trust": 1.0 if authority is ReviewAuthority.HUMAN else 0.9,
                "promotion_contract_version": receipt.contract_version,
                "promotion_receipt_id": receipt.receipt_id,
                "promotion_receipt_hash": receipt.receipt_hash,
                "promotion_proposal_id": proposal.proposal_id,
                "promotion_material_hash": memory_hash,
                "promotion_evidence_pack_id": proposal.evidence_pack_id,
                "promotion_evidence_pack_hash": proposal.evidence_pack_hash,
                "promotion_task_id": proposal.task_id,
                "promotion_decision_receipt_id": proposal.decision_receipt_id,
                "promotion_lineage_id": memory_lineage.lineage_id,
                "created_at": reviewed_at,
                "updated_at": reviewed_at,
                "last_confirmed": reviewed_at,
            }
        return await self.store.persist_disposition(
            review=review,
            receipt=receipt,
            lineage=memory_lineage,
            memory=memory,
        )

    async def retrieve(
        self,
        *,
        product_id: str,
        domain_path: str | None = None,
        limit: int = 20,
    ) -> list[PromotedMemoryProjectionV1]:
        await StateEngineOperationsService(self.store.pool).assert_active(product_id=product_id)
        return await self.store.list_authoritative_memories(
            product_id=product_id,
            domain_path=domain_path,
            limit=limit,
        )

    async def record_later_use(
        self,
        *,
        product_id: str,
        task_id: str,
        memories: list[PromotedMemoryProjectionV1],
        injected_ids: set[str] | None = None,
        reflected_ids: set[str] | None = None,
        comparison: dict[str, Any] | None = None,
        receiving_decision_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist existing I3 states on a real task; never infer use or benefit."""
        task = await self._task(task_id, product_id=product_id)
        injected_ids = injected_ids or set()
        reflected_ids = reflected_ids or set()
        receipt = build_intelligence_use_receipt(
            {
                "receiving": {
                    "product_id": product_id,
                    "task_id": task_id,
                    "decision_id": receiving_decision_id
                    or (normalize_decision_receipt(task.get("decision_receipt"), task=task).get("decision_id")),
                    "component": "grounded_state.promotion",
                    "stage": "later_reasoning",
                    "invocation_id": task_id,
                },
                "intelligence": [
                    {
                        "intelligence_id": item.memory_id,
                        "intelligence_type": item.memory_meaning.value,
                        "source_product_id": item.product_id,
                        "content_hash": item.content_hash,
                        "retrieval": {
                            "reason": "authoritative_promoted_memory",
                            "relevance": "relevant",
                            "receipt_id": item.receipt_id,
                            "lineage_id": item.lineage_id,
                        },
                        "validity": {"state": "active"},
                        "relevance": "relevant",
                        "trust": 1.0,
                        "provenance": {
                            "product_id": item.product_id,
                            "promotion_receipt_id": item.receipt_id,
                            "evidence_pack_id": item.evidence_pack_id,
                            "evidence_pack_hash": item.evidence_pack_hash,
                        },
                        "lifecycle": {"state": "active"},
                        "contestation": {},
                        "observed": {
                            "retrieved": True,
                            "injected": item.memory_id in injected_ids,
                            "reflected": item.memory_id in reflected_ids,
                        },
                        "reflection": {
                            "method": "bounded_attribution" if item.memory_id in reflected_ids else "unreported",
                            "evidence_refs": [item.receipt_id] if item.memory_id in reflected_ids else [],
                        },
                    }
                    for item in memories
                ],
                "comparison": comparison or {},
                "outcome": {"status": "not_observed"},
                "route": {"provider": None, "model": None, "billing_semantics": "no_provider_call"},
                "continuity": {"promotion_contract": "ace.grounded-state.promotion-receipt/v1"},
            }
        )
        async with self.pool.connection() as db:
            await db.query(
                "UPDATE <record>$task SET intelligence_use_receipt = $receipt, updated_at = time::now() "
                "WHERE product = $product",
                {
                    "task": parse_record_id(task_id),
                    "product": parse_record_id(product_id),
                    "receipt": receipt,
                },
            )
        return receipt


async def retrieve_promoted_memories(
    *,
    pool,
    product_id: str,
    domain_path: str | None = None,
    limit: int = 20,
) -> list[PromotedMemoryProjectionV1]:
    """Small integration helper for the existing ACE loaders and task runtime."""
    return await PromotionService(pool).retrieve(product_id=product_id, domain_path=domain_path, limit=limit)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
