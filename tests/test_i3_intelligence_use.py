from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from core.engine.evaluation.decision_delta import evaluate_decision_delta_suite, load_decision_delta_suite
from core.engine.orchestrator.context_assembler import ContextAssembler
from core.engine.product.intelligence_use import (
    CONTRACT_VERSION,
    DECISION_FIELDS,
    build_intelligence_use_receipt,
    exact_decision_delta,
    normalize_intelligence_use_receipt,
    runtime_intelligence_use_receipt,
)
from core.engine.product.living_graph import LivingProductGraphRecords, project_product_snapshot

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "evaluations" / "fixtures" / "i3_intelligence_use_v1.json"
LIVE_RESULT = REPO / "evaluations" / "results" / "i3_live_provider_v1.json"


def _result() -> dict:
    return evaluate_decision_delta_suite(load_decision_delta_suite(FIXTURE))


def _receipts() -> dict[str, dict]:
    return {receipt["receiving"]["task_id"]: receipt for receipt in _result()["receipts"]}


def test_i3_matrix_is_deterministic_and_uses_the_product_contract():
    first = _result()
    second = _result()
    assert first == second
    assert first["contract_version"] == CONTRACT_VERSION
    assert first["summary"]["receipts"] == 13
    assert first["summary"]["material_receipts"] == 4
    assert first["summary"]["comparison_states"] == {
        "matched": 11,
        "mismatched": 1,
        "failed": 1,
        "unknown": 0,
    }
    assert {receipt["receipt_id"] for receipt in first["receipts"]} == {
        receipt["receipt_id"] for receipt in second["receipts"]
    }


def test_frozen_live_provider_receipt_is_exactly_matched_and_outcome_unsupported():
    result = json.loads(LIVE_RESULT.read_text(encoding="utf-8"))
    receipt = result["receipt"]
    assert result["stopping_rule"] == "exactly_one_treatment_and_one_control"
    assert receipt["contract_version"] == CONTRACT_VERSION
    assert receipt["comparison"]["state"] == "matched"
    assert receipt["comparison"]["matching"]["mismatches"] == []
    assert receipt["comparison"]["matching"]["missing_fields"] == []
    assert receipt["route"]["provider"] == "CodexCLIProvider"
    assert receipt["route"]["model"] == "gpt-5.6-terra"
    assert receipt["route"]["calls"] == 2
    assert receipt["route"]["failures"] == []
    assert receipt["material_intelligence_ids"] == ["observation:i3-public-retail-cancellation-gate-v1"]
    assert {item["field"] for item in receipt["comparison"]["delta"]["changed_fields"]} == {
        "selected_option",
        "assumptions",
        "alternatives",
        "reconsideration_conditions",
        "evidence_refs",
    }
    assert receipt["impact"]["beneficial_impact"] == "outcome_unsupported"
    assert receipt["impact"]["beneficial_impact_supported"] is False


def test_exact_delta_is_limited_to_existing_i1_fields():
    delta = exact_decision_delta(
        {"selected_option": "staged", "scope": "cohort", "rationale": "private treatment prose"},
        {"selected_option": "rollout", "scope": "cohort", "rationale": "private control prose"},
    )
    assert delta["changed_fields"] == [
        {"field": "selected_option", "without_context": "rollout", "with_context": "staged"}
    ]
    assert set(delta["unchanged_fields"]) == set(DECISION_FIELDS) - {"selected_option"}


def test_material_null_irrelevant_and_reflected_states_remain_distinct():
    receipts = _receipts()
    material = receipts["task:i3-material"]
    assert material["material_intelligence_ids"] == ["observation:i3-material"]
    assert material["intelligence"][0]["evidence"]["decision_material"] is True
    assert material["impact"]["beneficial_impact"] == "outcome_unsupported"
    assert material["impact"]["beneficial_impact_supported"] is False

    null = receipts["task:i3-null"]
    assert null["comparison"]["delta"]["changed_fields"] == []
    assert null["intelligence"][0]["evidence"]["highest_state"] == "reflected"
    assert (
        "no_qualifying_structured_decision_delta"
        in null["intelligence"][0]["evidence"]["not_established_reasons"]["decision_material"]
    )

    irrelevant = receipts["task:i3-irrelevant"]["intelligence"][0]
    assert irrelevant["evidence"]["highest_state"] == "retrieved"
    assert irrelevant["evidence"]["injected"] is False

    reflected = receipts["task:i3-reflected"]["intelligence"][0]
    assert reflected["evidence"]["highest_state"] == "reflected"
    assert (
        "reflection_method_not_materiality_eligible"
        in reflected["evidence"]["not_established_reasons"]["decision_material"]
    )


def test_stale_invalidated_contested_and_harmful_cases_are_honest():
    receipts = _receipts()
    stale = receipts["task:i3-stale"]["intelligence"][0]
    assert stale["evidence"]["decision_material"] is False
    assert "validity_stale" in stale["evidence"]["not_established_reasons"]["decision_material"]

    invalidated = receipts["task:i3-invalidated"]["intelligence"][0]
    assert invalidated["evidence"]["highest_state"] == "retrieved"
    assert "validity_invalidated" in invalidated["evidence"]["not_established_reasons"]["decision_material"]

    contested = receipts["task:i3-contested"]
    assert contested["intelligence"][0]["contestation"]["handling"] == "preserve_disagreement"
    assert contested["intelligence"][0]["evidence"]["decision_material"] is True

    harmful = receipts["task:i3-harmful"]
    assert harmful["intelligence"][0]["evidence"]["decision_material"] is True
    assert harmful["impact"]["beneficial_impact"] == "harmful"
    assert harmful["impact"]["beneficial_impact_supported"] is False


def test_isolation_mismatch_route_mismatch_failure_and_partial_lineage_block_materiality():
    receipts = _receipts()
    foreign = receipts["task:i3-product-mismatch"]["intelligence"][0]
    assert "product_mismatch" in foreign["evidence"]["not_established_reasons"]["decision_material"]

    mismatch = receipts["task:i3-route-mismatch"]
    assert mismatch["comparison"]["state"] == "mismatched"
    assert {item["field"] for item in mismatch["comparison"]["matching"]["mismatches"]} == {
        "provider",
        "model",
        "configuration_hash",
    }
    assert mismatch["material_intelligence_ids"] == []

    failed = receipts["task:i3-evaluation-failure"]
    assert failed["comparison"]["state"] == "failed"
    assert failed["material_intelligence_ids"] == []

    partial = receipts["task:i3-partial-lineage"]
    assert partial["completeness"]["state"] == "degraded"
    assert partial["material_intelligence_ids"] == []
    assert (
        "partial_or_missing_lineage"
        in partial["intelligence"][0]["evidence"]["not_established_reasons"]["decision_material"]
    )


def test_restart_case_preserves_fresh_invocation_and_receipt_identity():
    first = _receipts()["task:i3-restart"]
    second = _receipts()["task:i3-restart"]
    assert first["receipt_id"] == second["receipt_id"]
    assert first["continuity"] == {
        "fresh_client_invocation": True,
        "runtime_restart": "real_supported_api_database_restart",
        "database_identity_preserved": True,
        "receipt_identity_replayed": True,
    }
    assert first["material_intelligence_ids"] == ["observation:i3-restart"]


def test_missing_control_and_unknown_version_degrade_without_reconstruction():
    task = {
        "id": "task:missing-control",
        "product": "product:i3-public-retail",
        "decision_receipt": {"decision_id": "decision:missing-control"},
    }
    missing = normalize_intelligence_use_receipt(None, task=task)
    assert missing["comparison"]["state"] == "unknown"
    assert missing["material_intelligence_ids"] == []
    assert missing["completeness"]["state"] == "degraded"

    future = normalize_intelligence_use_receipt({"contract_version": "intelligence-use-receipt-v99"}, task=task)
    assert future["contract_version"] == CONTRACT_VERSION
    assert future["intelligence"] == []
    assert future["comparison"]["state"] == "unknown"
    assert future["completeness"]["missing_or_degraded"] == [
        "unsupported_intelligence_use_receipt_version:intelligence-use-receipt-v99"
    ]


def test_runtime_projection_records_injection_and_reflection_but_not_materiality():
    receipt = runtime_intelligence_use_receipt(
        task_id="task:runtime",
        product_id="product:i3-public-retail",
        decision_receipt={"decision_id": "decision:runtime", "selected_option": "keep_staged"},
        trace={
            "reflection_method": "structural_attribution",
            "reflected_ids": ["insight:runtime"],
            "items": [
                {
                    "id": "insight:runtime",
                    "intelligence_type": "pattern",
                    "source_product_id": "product:i3-public-retail",
                    "content_hash": "sha256:runtime",
                    "trust": 0.8,
                    "relevance": "relevant",
                    "validity": {"state": "active"},
                    "lifecycle": {"state": "active"},
                    "provenance": {"source": "insight"},
                }
            ],
        },
    )
    item = receipt["intelligence"][0]
    assert item["evidence"]["retrieved"] is True
    assert item["evidence"]["injected"] is True
    assert item["evidence"]["reflected"] is True
    assert item["evidence"]["decision_material"] is False
    assert receipt["comparison"]["state"] == "unknown"


def test_legacy_context_markers_distinguish_retrieval_from_actual_injection():
    context, marker_map = ContextAssembler(max_tokens=500).build_with_markers(
        {
            "insights": [
                {
                    "id": "insight:legacy",
                    "insight_type": "correction",
                    "content": "Keep the cohort staged",
                    "confidence": 1.0,
                }
            ]
        }
    )
    assert "[I-1]" in context
    assert marker_map == {"[I-1]": "insight:legacy"}

    receipt = runtime_intelligence_use_receipt(
        task_id="task:retrieved-only",
        product_id="product:i3-public-retail",
        decision_receipt={"decision_id": "decision:retrieved-only"},
        trace={
            "items": [
                {
                    "id": "insight:retrieved-only",
                    "intelligence_type": "pattern",
                    "source_product_id": "product:i3-public-retail",
                    "content_hash": "sha256:retrieved-only",
                    "trust": 0.7,
                    "relevance": "relevant",
                    "validity": {"state": "active"},
                    "lifecycle": {"state": "active"},
                    "provenance": {"source": "insight"},
                    "injected": False,
                }
            ]
        },
    )
    item = receipt["intelligence"][0]
    assert item["evidence"]["retrieved"] is True
    assert item["evidence"]["injected"] is False
    assert item["evidence"]["highest_state"] == "retrieved"


def test_redaction_bounds_and_living_graph_read_only_projection():
    receipt = deepcopy(_receipts()["task:i3-material"])
    receipt["route"]["failure"] = "Bearer top-secret-value"
    receipt["intelligence"] *= 3
    task = {
        "id": "task:i3-material",
        "product": "product:i3-public-retail",
        "status": "completed",
        "decision_receipt": {"decision_id": "decision:i3-material"},
        "intelligence_use_receipt": receipt,
    }
    snapshot = project_product_snapshot(
        "product:i3-public-retail",
        LivingProductGraphRecords(
            product={"id": "product:i3-public-retail", "name": "Public retail fixture"},
            records={"tasks": [task]},
        ),
    )
    projected = snapshot["work"]["tasks"][0]["intelligence_use_receipt"]
    assert projected["authority"] == {"mode": "read_only_projection", "execution_authority": False}
    assert projected["route"]["failure"] == "Bearer=<redacted>"
    assert len(projected["intelligence"]) <= 64
    assert snapshot["authority"]["writes_permitted"] is False


def test_receipt_identity_is_idempotent_and_changes_with_comparison_identity():
    suite = load_decision_delta_suite(FIXTURE)
    defaults = suite["defaults"]
    case = deepcopy(suite["cases"][0])

    def merge(base: dict, override: dict) -> dict:
        result = deepcopy(base)
        for key, value in override.items():
            result[key] = (
                merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else value
            )
        return result

    merged = merge(defaults, case)
    first = build_intelligence_use_receipt(merged)
    second = build_intelligence_use_receipt(merged)
    assert first == second
    merged["comparison"]["with_context"]["invocation_id"] = "invocation:different"
    assert build_intelligence_use_receipt(merged)["receipt_id"] != first["receipt_id"]
