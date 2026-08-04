"""Frozen TP8 benchmark, contract, migration, and runner checks."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.engine.grounded_state.operational_contracts import (
    OperationalReceiptV1,
    OperationalStatus,
    ProductLifecycleReceiptV1,
    ProductLifecycleState,
)
from evaluations.state_engine_tp8 import compute_dataset_hashes, load_tp8_manifest

ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "evaluations/fixtures/state_engine_tp8_scale_stability_v1.json"


def test_tp8_benchmark_is_frozen_before_scale_execution_and_reconciles_exactly():
    manifest = load_tp8_manifest(MANIFEST)
    raw_hash, manifest_hash, count = compute_dataset_hashes(manifest.dataset)

    assert raw_hash == manifest.dataset.raw_dataset_sha256
    assert manifest_hash == manifest.dataset.manifest_set_sha256
    assert count == manifest.dataset.expected_manifest_count == 63
    assert manifest.dataset.claim_count == 200_000
    assert manifest.dataset.expected_semantic_counts.total() == 236_000
    assert max(manifest.dataset.daily_claim_counts) == 34_000
    assert manifest.reference_workload["sustained_target_claims_per_day"] == 68_000
    assert manifest.provider_budget["bulk_ingestion_primary_model_calls"] == 0
    assert manifest.thresholds["provider_calls_max"] == 0
    assert manifest.versions["schema_head_before_tp8"] == 167
    assert manifest.versions["expected_schema_head"] == 168


def test_tp8_operational_contracts_are_material_derived_and_terminal_states_are_honest():
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    lifecycle = ProductLifecycleReceiptV1(
        product_id="product:tp8-contract",
        state=ProductLifecycleState.ARCHIVED,
        actor_ref="maintainer:tp8",
        reason="Disposable lifecycle proof.",
        occurred_at=now,
    )
    assert lifecycle.receipt_id.startswith("grounded_product_lifecycle:")
    assert len(lifecycle.receipt_hash) == 64

    operation = OperationalReceiptV1(
        product_id="product:tp8-contract",
        run_id="state-engine-tp8-scale-stability-v1",
        operation_id="failure-1",
        operation_kind="failure_injection",
        status=OperationalStatus.FAILED,
        started_at=now,
        finished_at=now,
        failures=("injected_failure",),
    )
    assert operation.receipt_id.startswith("grounded_operational_receipt:")
    assert operation.receipt_hash != lifecycle.receipt_hash


def test_tp8_migration_is_additive_append_only_and_runner_is_packaged_source():
    migration = (ROOT / "core/schema/v168_state_engine_tp8_operations.surql").read_text()
    assert "grounded_product_lifecycle" in migration
    assert "grounded_operational_receipt" in migration
    assert "FOR update NONE" in migration
    assert "FOR delete NONE" in migration
    assert "UPDATE " not in migration
    assert "DELETE " not in migration
    runner = (ROOT / "scripts/run_state_engine_tp8.py").read_text()
    assert "compute_dataset_hashes" in runner
    assert "GroundedStateIngestionService" in runner
    assert "primary_model" not in runner


@pytest.mark.asyncio
async def test_tp8_n_minus_one_extension_envelope_passes_current_core_conformance():
    from core.engine.extensions import (
        ExtensionActorContext,
        ExtensionInvocationEnvelope,
        run_task_action_conformance,
    )
    from core.engine.extensions.invocation import RegisteredTaskAction
    from extensions.reference.invocation import (
        OUTCOME_CONTRACT,
        prepare_product_check,
        project_product_check,
    )

    action = RegisteredTaskAction(
        extension_id="product",
        extension_version="0.1.4",
        action="product-check",
        prepare=prepare_product_check,
        project_outcome=project_product_check,
        output_contract=OUTCOME_CONTRACT,
        lifecycle_operations=["submit", "retrieve", "history", "retry", "cancel"],
        cancellation_supported=True,
        resolver_capabilities=["declared-reference-identities"],
    )
    result = await run_task_action_conformance(
        action,
        ExtensionInvocationEnvelope(
            extension_id="product",
            extension_version="0.1.4",
            action="product-check",
            workspace_id="workspace:tp8-n-minus-one",
            question="Does the N-1 envelope preserve the supported lifecycle?",
            references=[
                {
                    "namespace": "example",
                    "kind": "record",
                    "id": "record:tp8-n-minus-one",
                    "version": "1",
                }
            ],
        ),
        ExtensionActorContext(
            product_id="product:tp8-n-minus-one",
            workspace_id="workspace:tp8-n-minus-one",
            user_id="user:tp8-n-minus-one",
        ),
    )
    assert result["passed"] is True
