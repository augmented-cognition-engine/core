"""Frozen, provider-free TP7 evaluator over the real promotion memory path."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field, ValidationError, field_validator, model_validator

from core.engine.core.db import parse_record_id, parse_rows
from core.engine.grounded_state.belief_contracts import ReviewAuthority
from core.engine.grounded_state.contracts import FrozenContract, canonical_hash
from core.engine.grounded_state.promotion import PromotionService
from core.engine.grounded_state.promotion_contracts import (
    PromotionDisposition,
    PromotionMaterialV1,
    PromotionMemoryLineageV1,
    PromotionProposalV1,
    PromotionReceiptV1,
    PromotionReviewV1,
    PromotionTargetKind,
)
from core.engine.grounded_state.promotion_persistence import (
    PromotionProductScopeError,
    PromotionReplayConflict,
    PromotionStore,
)

TP7_EVALUATION_CONFIG_VERSION = "ace.grounded-state.promotion-evaluation-config/v1"
TP7_EVALUATION_RESULT_VERSION = "ace.grounded-state.promotion-evaluation-result/v1"

ROOT = Path(__file__).parents[3]
DEFAULT_CONFIG = ROOT / "evaluations/fixtures/state_engine_tp7_promotion_feedback_v1.json"
DEFAULT_RESULT = ROOT / "evaluations/results/state_engine_tp7_promotion_feedback_v1.json"

# Capture the production callables once. Sabotage tests that replace any of
# these paths must make the evaluator fail instead of merely changing a trace.
_REAL_PROMOTER = PromotionService.propose
_REAL_REVIEW = PromotionService.review
_REAL_PERSISTENCE = PromotionStore.persist_disposition
_REAL_RETRIEVAL = PromotionService.retrieve


class TP7PromotionEvaluationConfigV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.promotion-evaluation-config/v1"] = TP7_EVALUATION_CONFIG_VERSION
    fixture_id: Literal["state-engine-tp7-promotion-feedback-v1"]
    fixture_status: Literal["frozen_before_implementation"]
    frozen_at: str
    reference_corpus: dict[str, Any]
    tp6_acceptance: dict[str, Any]
    versions: dict[str, str]
    positive_cases: dict[str, dict[str, Any]]
    adversarial_cases: dict[str, dict[str, Any]]
    lifecycle_dispositions: tuple[PromotionDisposition, ...]
    required_checks: tuple[str, ...]
    sabotage_checks: tuple[str, ...]
    bounds: dict[str, Any]
    provider_budget: dict[str, Any]
    thresholds: dict[str, Any]
    target_corrections: tuple[str, ...]

    @field_validator("lifecycle_dispositions", mode="before")
    @classmethod
    def normalize_dispositions(cls, value: Any) -> tuple[PromotionDisposition, ...]:
        return tuple(sorted({PromotionDisposition(item) for item in value}, key=lambda item: item.value))

    @field_validator("required_checks", "sabotage_checks", "target_corrections", mode="before")
    @classmethod
    def normalize_strings(cls, value: Any) -> tuple[str, ...]:
        return tuple(sorted({str(item) for item in value}))

    @model_validator(mode="after")
    def validate_frozen_target(self) -> Self:
        if len(self.positive_cases) != 4 or len(self.adversarial_cases) != 14:
            raise ValueError("TP7 evaluator must bind the frozen four positive and fourteen adversarial cases")
        if len(self.required_checks) != 26 or len(self.sabotage_checks) != 3:
            raise ValueError("TP7 evaluator check set drifted from the frozen target")
        if set(self.lifecycle_dispositions) != set(PromotionDisposition):
            raise ValueError("TP7 evaluator must bind every append-only lifecycle disposition")
        if any(value not in {0, 0.0} for value in self.provider_budget.values()):
            raise ValueError("TP7 frozen evaluation is provider-free")
        return self

    def config_hash(self) -> str:
        return canonical_hash(self)


class TP7PromotionEvaluationResultV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.promotion-evaluation-result/v1"] = TP7_EVALUATION_RESULT_VERSION
    config_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    positive_case_results: dict[str, bool]
    adversarial_case_results: dict[str, bool]
    lifecycle_dispositions_observed: tuple[PromotionDisposition, ...]
    required_checks: dict[str, bool]
    sabotage_checks: dict[str, bool]
    product_isolation_violations: int = Field(ge=0)
    unauthorized_memory_writes: int = Field(ge=0)
    simulated_observation_violations: int = Field(ge=0)
    beneficial_impact_claims: int = Field(ge=0)
    provider_budget_violations: int = Field(ge=0)
    primary_model_calls: Literal[0] = 0
    input_tokens: Literal[0] = 0
    output_tokens: Literal[0] = 0
    latency_ms: Literal[0] = 0
    retries: Literal[0] = 0
    estimated_cost_usd: Literal[0.0] = 0.0
    billing_semantics: Literal["no_provider_call"] = "no_provider_call"
    failures: tuple[str, ...] = ()
    passed: bool
    outcome_hash: str | None = None

    @model_validator(mode="after")
    def reconcile(self) -> Self:
        expected_pass = (
            len(self.positive_case_results) == 4
            and len(self.adversarial_case_results) == 14
            and all(self.positive_case_results.values())
            and all(self.adversarial_case_results.values())
            and set(self.lifecycle_dispositions_observed) == set(PromotionDisposition)
            and len(self.required_checks) == 26
            and all(self.required_checks.values())
            and len(self.sabotage_checks) == 3
            and all(self.sabotage_checks.values())
            and self.product_isolation_violations == 0
            and self.unauthorized_memory_writes == 0
            and self.simulated_observation_violations == 0
            and self.beneficial_impact_claims == 0
            and self.provider_budget_violations == 0
            and not self.failures
        )
        if self.passed is not expected_pass:
            raise ValueError("TP7 result disposition does not reconcile the frozen thresholds")
        expected_hash = canonical_hash(self.model_dump(mode="json", exclude={"outcome_hash"}))
        if self.outcome_hash is not None and self.outcome_hash != expected_hash:
            raise ValueError("TP7 result outcome hash does not match exact evaluation material")
        object.__setattr__(self, "outcome_hash", expected_hash)
        return self


def load_tp7_config(path: str | Path = DEFAULT_CONFIG) -> TP7PromotionEvaluationConfigV1:
    return TP7PromotionEvaluationConfigV1.model_validate_json(Path(path).read_text(encoding="utf-8"))


def load_tp7_result(path: str | Path = DEFAULT_RESULT) -> TP7PromotionEvaluationResultV1:
    return TP7PromotionEvaluationResultV1.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _rejects_material(*, origin_meaning: str, memory_meaning: str) -> bool:
    try:
        PromotionMaterialV1(
            target_kind="durable_conclusion",
            origin_meaning=origin_meaning,
            memory_meaning=memory_meaning,
            content="Untrusted source material must not become memory.",
            domain_path="product",
        )
    except ValidationError:
        return True
    return False


def _model_cannot_review(proposal: PromotionProposalV1) -> bool:
    try:
        PromotionReviewV1(
            product_id=proposal.product_id,
            proposal_id=str(proposal.proposal_id),
            proposal_hash=str(proposal.proposal_hash),
            disposition=PromotionDisposition.ACCEPTED,
            authority=ReviewAuthority.MODEL,
            reviewer_ref="model:tp7-sabotage",
            authority_scope="self_asserted",
            rationale="A model cannot authorize itself.",
            reviewed_at=proposal.proposed_at,
        )
    except ValidationError:
        return True
    return False


def _promotion_method_is(instance: object, expected) -> bool:
    method = getattr(instance, "__func__", instance)
    return method is expected


async def evaluate_tp7_promotion_feedback(
    config: TP7PromotionEvaluationConfigV1,
    *,
    pool,
    original_proposal: PromotionProposalV1,
    original_review: dict[str, Any],
    original_receipt_id: str,
    corrected_receipt_id: str,
) -> TP7PromotionEvaluationResultV1:
    """Re-audit durable TP7 state while executing the production path.

    The supplied database must already contain the completed frozen scenario.
    The evaluator then performs an exact proposal/review replay, a real process
    restart, and a fresh production retrieval before scoring persisted cases.
    """
    service = PromotionService(pool)
    failures: list[str] = []
    promoter_real = _promotion_method_is(service.propose, _REAL_PROMOTER)
    review_real = _promotion_method_is(service.review, _REAL_REVIEW)
    persistence_real = _promotion_method_is(service.store.persist_disposition, _REAL_PERSISTENCE)
    replay_ok = False
    persistence_ok = False
    before_counts = (
        len(await service.store.list_records(PromotionReceiptV1, product_id=original_proposal.product_id)),
        len(await service.store.list_records(PromotionMemoryLineageV1, product_id=original_proposal.product_id)),
    )
    try:
        replayed_proposal = await service.propose(original_proposal)
        replayed_receipt = await service.review(**original_review)
        after_counts = (
            len(await service.store.list_records(PromotionReceiptV1, product_id=original_proposal.product_id)),
            len(await service.store.list_records(PromotionMemoryLineageV1, product_id=original_proposal.product_id)),
        )
        replay_ok = replayed_proposal == original_proposal and str(replayed_receipt.receipt_id) == original_receipt_id
        persistence_ok = before_counts == after_counts
    except Exception as exc:  # fail closed and preserve a bounded category
        failures.append(f"production_replay:{type(exc).__name__}")

    conflict_visible = False
    try:
        original = await service.store.require(
            PromotionReceiptV1,
            original_receipt_id,
            product_id=original_proposal.product_id,
        )
        await service.store.persist(original.model_copy(update={"reasons": ("conflicting replay",)}))
    except PromotionReplayConflict:
        conflict_visible = True
    except Exception as exc:
        failures.append(f"conflict_probe:{type(exc).__name__}")

    await pool.restart()
    fresh = PromotionService(pool)
    retrieval_real = _promotion_method_is(fresh.retrieve, _REAL_RETRIEVAL)
    try:
        authoritative = await fresh.retrieve(product_id=original_proposal.product_id, domain_path="product")
        foreign = await fresh.retrieve(product_id="product:tp7-foreign", domain_path="product")
    except Exception as exc:
        failures.append(f"fresh_retrieval:{type(exc).__name__}")
        authoritative, foreign = [], ["unavailable"]

    proposals = await fresh.store.list_records(PromotionProposalV1, product_id=original_proposal.product_id)
    reviews = await fresh.store.list_records(PromotionReviewV1, product_id=original_proposal.product_id)
    receipts = await fresh.store.list_records(PromotionReceiptV1, product_id=original_proposal.product_id)
    lineages = await fresh.store.list_records(PromotionMemoryLineageV1, product_id=original_proposal.product_id)
    states = await fresh.store.effective_states(product_id=original_proposal.product_id)
    proposals_by_id = {str(item.proposal_id): item for item in proposals}
    reviews_by_id = {str(item.review_id): item for item in reviews}
    receipt_by_id = {str(item.receipt_id): item for item in receipts}
    lineage_receipts = {item.receipt_id for item in lineages}

    def receipts_for(kind: PromotionTargetKind) -> list[PromotionReceiptV1]:
        return [
            item
            for item in receipts
            if proposals_by_id.get(item.proposal_id) and proposals_by_id[item.proposal_id].material.target_kind is kind
        ]

    conclusions = receipts_for(PromotionTargetKind.DURABLE_CONCLUSION)
    preferences = receipts_for(PromotionTargetKind.STABLE_PREFERENCE)
    patterns = receipts_for(PromotionTargetKind.REUSABLE_REASONING_PATTERN)
    accepted_conclusion = any(
        item.disposition is PromotionDisposition.ACCEPTED and item.memory_id for item in conclusions
    )
    deterministic_preference = any(
        item.disposition is PromotionDisposition.ACCEPTED
        and item.memory_id
        and (review := reviews_by_id.get(item.review_id)) is not None
        and review.authority is ReviewAuthority.DETERMINISTIC_POLICY
        and review.deterministic_rule_id == "tp7-stable-preference-v1"
        for item in preferences
    )
    rejected_pattern = any(
        item.disposition is PromotionDisposition.REJECTED and item.memory_id is None for item in patterns
    )
    corrected = receipt_by_id.get(corrected_receipt_id)
    correction_active = (
        corrected is not None
        and corrected.disposition is PromotionDisposition.ACCEPTED
        and getattr(states.get(corrected_receipt_id), "value", None) == "active"
        and getattr(states.get(original_receipt_id), "value", None) == "superseded"
    )

    degraded_reasons = {reason for item in proposals for reason in (*item.degraded_reasons, *item.failures)}
    contested_present = any(item.contested_input_refs for item in proposals)
    disposition_set = {item.disposition for item in receipts}

    async with pool.connection() as db:
        memories = parse_rows(
            await db.query(
                "SELECT id, product, source_kind, source_ref, promotion_receipt_id, promotion_lineage_id "
                "FROM insight WHERE product = <record>$product AND source_kind = 'grounded_promotion'",
                {"product": parse_record_id(original_proposal.product_id)},
            )
        )
        tasks = parse_rows(
            await db.query(
                "SELECT id, intelligence_use_receipt FROM task WHERE product = <record>$product AND id IN $tasks",
                {
                    "product": parse_record_id(original_proposal.product_id),
                    "tasks": [
                        parse_record_id("task:tp7-later-retrieval"),
                        parse_record_id("task:tp7-later-material"),
                    ],
                },
            )
        )
    memory_receipts = {str(row.get("source_ref")) for row in memories}
    atomic = all(
        item.receipt_id in lineage_receipts and item.receipt_id in memory_receipts
        for item in receipts
        if item.memory_id
    )
    unauthorized = sum(1 for row in memories if str(row.get("source_ref")) not in receipt_by_id)
    retrieval_task = next((row for row in tasks if str(row.get("id")) == "task:tp7-later-retrieval"), {})
    material_task = next((row for row in tasks if str(row.get("id")) == "task:tp7-later-material"), {})
    retrieval_receipt = retrieval_task.get("intelligence_use_receipt") or {}
    material_receipt = material_task.get("intelligence_use_receipt") or {}
    retrieval_items = retrieval_receipt.get("intelligence") or []
    material_items = material_receipt.get("intelligence") or []
    retrieved_not_used = (
        bool(retrieval_items)
        and retrieval_items[0].get("evidence", {}).get("highest_state") == "retrieved"
        and retrieval_items[0].get("evidence", {}).get("decision_material") is False
    )
    material_without_benefit = (
        bool(material_items)
        and material_items[0].get("evidence", {}).get("highest_state") == "decision-material"
        and material_items[0].get("evidence", {}).get("decision_material") is True
        and material_receipt.get("impact", {}).get("beneficial_impact_supported") is False
    )

    product_isolated = not foreign
    try:
        await fresh.store.require(PromotionReceiptV1, original_receipt_id, product_id="product:tp7-foreign")
    except PromotionProductScopeError:
        pass
    else:
        product_isolated = False

    model_non_authority = _model_cannot_review(original_proposal)
    raw_rejected = _rejects_material(origin_meaning="source_claim", memory_meaning="durable_conclusion")
    retrieved_rejected = _rejects_material(origin_meaning="retrieved_evidence", memory_meaning="durable_conclusion")
    simulation_rejected = _rejects_material(
        origin_meaning="grounded_reasoning_conclusion",
        memory_meaning="observed_fact",
    )
    source_instruction_rejected = False
    try:
        PromotionProposalV1.model_validate(
            {**original_proposal.model_dump(mode="python"), "source_instruction_authority": True}
        )
    except ValidationError:
        source_instruction_rejected = True
    try:
        from ace_mcp_client.server import mcp as thin_client_mcp

        public_mcp_tool_count_eleven = len(await thin_client_mcp.list_tools()) == 11
    except Exception:
        public_mcp_tool_count_eleven = False

    positive = {
        "accepted_correction_supersedes_conclusion": correction_active,
        "accepted_grounded_durable_conclusion": accepted_conclusion,
        "deterministic_policy_stable_preference": deterministic_preference,
        "human_rejected_reasoning_pattern": rejected_pattern,
    }
    adversarial = {
        "conflicting_replay": conflict_visible,
        "contested_support": contested_present and PromotionDisposition.CONTESTED in disposition_set,
        "exact_replay": replay_ok and persistence_ok,
        "foreign_product_lineage": product_isolated,
        "ingested_or_retrieved_claim_only": retrieved_rejected,
        "material_use_without_benefit": material_without_benefit,
        "model_self_authorization": model_non_authority,
        "raw_source_claim": raw_rejected,
        "rejected_support": "rejected_support" in degraded_reasons and PromotionDisposition.FAILED in disposition_set,
        "retrieval_without_use": retrieved_not_used,
        "simulated_state_as_observed_fact": simulation_rejected,
        "source_text_instruction": source_instruction_rejected,
        "stale_support": "stale_support" in degraded_reasons and PromotionDisposition.DEGRADED in disposition_set,
        "truncated_support": "truncated_support" in degraded_reasons
        and PromotionDisposition.DEGRADED in disposition_set,
    }
    fresh_corrected_only = [item.receipt_id for item in authoritative] == [corrected_receipt_id]
    required = {
        "accepted_grounded_conclusion_enters_existing_memory": accepted_conclusion,
        "atomic_receipt_and_memory_lineage": atomic,
        "authoritative_disposition_required": all(item.review_id in reviews_by_id for item in receipts),
        "conflicting_replay_visible": conflict_visible,
        "corrected_state_retrieved_after_restart": fresh_corrected_only,
        "correction_preserves_original_lineage": bool(
            corrected and original_receipt_id in corrected.supersedes_receipt_ids
        ),
        "cross_product_inputs_denied": product_isolated,
        "decision_and_task_receipt_lineage_exact": replay_ok,
        "degraded_inputs_fail_closed": adversarial["truncated_support"] and adversarial["stale_support"],
        "deterministic_ordering": tuple(item.receipt_id for item in authoritative)
        == tuple(sorted(item.receipt_id for item in authoritative)),
        "evidence_versions_and_pack_hash_exact": all(
            item.evidence_pack_hash and all(version.product_id == item.product_id for version in item.evidence_versions)
            for item in proposals
        ),
        "exact_replay_idempotent": replay_ok and persistence_ok,
        "fresh_invocation_retrieves_promoted_memory": fresh_corrected_only,
        "l1_readiness_unchanged": any(
            f"| L1 | {status} |" in (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
            for status in ("candidate", "passed")
        ),
        "lifecycle_dispositions_inspectable": disposition_set == set(PromotionDisposition),
        "model_proposal_non_authority": model_non_authority,
        "no_evidence_without_promotion_receipt": unauthorized == 0 and atomic,
        "no_raw_claim_promotion": raw_rejected and retrieved_rejected,
        "no_rejected_or_retrieved_memory_leak": fresh_corrected_only,
        "no_simulation_relabeling": simulation_rejected,
        "product_isolation": product_isolated,
        "promotion_survives_real_restart": fresh_corrected_only,
        "public_mcp_tool_count_eleven": public_mcp_tool_count_eleven,
        "retrieval_injection_reflection_materiality_distinct": retrieved_not_used and material_without_benefit,
        "source_instruction_no_authority": source_instruction_rejected,
        "use_is_not_beneficial_impact": material_without_benefit,
    }
    sabotage = {
        "real_later_retrieval_required": retrieval_real and fresh_corrected_only,
        "real_persistence_required": review_real and persistence_real and persistence_ok,
        "real_promoter_required": promoter_real and replay_ok,
    }
    if set(required) != set(config.required_checks):
        failures.append("required_check_set_drift")
    if set(sabotage) != set(config.sabotage_checks):
        failures.append("sabotage_check_set_drift")
    passed = (
        all(positive.values())
        and all(adversarial.values())
        and disposition_set == set(PromotionDisposition)
        and all(required.values())
        and all(sabotage.values())
        and product_isolated
        and unauthorized == 0
        and not failures
    )
    return TP7PromotionEvaluationResultV1(
        config_hash=config.config_hash(),
        positive_case_results=dict(sorted(positive.items())),
        adversarial_case_results=dict(sorted(adversarial.items())),
        lifecycle_dispositions_observed=tuple(sorted(disposition_set, key=lambda item: item.value)),
        required_checks=dict(sorted(required.items())),
        sabotage_checks=dict(sorted(sabotage.items())),
        product_isolation_violations=0 if product_isolated else 1,
        unauthorized_memory_writes=unauthorized,
        simulated_observation_violations=0 if simulation_rejected else 1,
        beneficial_impact_claims=0 if material_without_benefit else 1,
        provider_budget_violations=0,
        failures=tuple(sorted(failures)),
        passed=passed,
    )
