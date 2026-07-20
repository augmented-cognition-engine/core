from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from core.engine.evaluation.decision_delta import (
    CONTRACT_VERSION,
    EVIDENCE_LEVELS,
    build_decision_delta_receipt,
    evaluate_decision_delta_suite,
    load_decision_delta_suite,
    render_decision_delta_markdown,
)

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "evaluations" / "fixtures" / "decision_delta_contract_v1.json"


def _result() -> dict:
    return evaluate_decision_delta_suite(load_decision_delta_suite(FIXTURE))


def _receipts() -> dict[str, dict]:
    return {receipt["case_id"]: receipt for receipt in _result()["receipts"]}


def test_suite_is_deterministic_bounded_and_covers_all_levels():
    first = _result()
    second = _result()
    assert first == second
    assert first["contract_version"] == CONTRACT_VERSION
    assert first["summary"]["tasks"] == 8
    assert len(first["summary"]["task_shapes"]) >= 3
    assert set(first["summary"]["surfaces"]) == {"cli", "mcp"}
    assert set(first["summary"]["access_classes"]) == {"local", "subscription_backed"}
    assert all(first["summary"]["evidence_levels"][level] >= 1 for level in EVIDENCE_LEVELS)
    assert len({receipt["receipt_id"] for receipt in first["receipts"]}) == 8
    json.dumps(first)


def test_relevant_correction_records_exact_delta_and_outcome_support():
    receipt = _receipts()["architecture-relevant-correction"]
    changed = {item["field"] for item in receipt["decision"]["delta"]}
    assert {"selected_option", "constraints", "rejected_alternatives", "next_action"} <= changed
    memory = receipt["intelligence"][0]
    assert memory["evidence"]["decision_material"] is True
    assert memory["evidence"]["outcome_supported"] is True
    assert memory["evidence"]["level"] == "outcome-supported"
    assert receipt["causal_assessment"]["memory_effect_supported"] is True


def test_irrelevant_retrieval_and_injection_receive_no_materiality_credit():
    receipt = _receipts()["release-irrelevant-memory"]
    assert receipt["decision"]["delta"] == []
    assert [item["evidence"]["level"] for item in receipt["intelligence"]] == ["retrieved", "injected"]
    assert receipt["decision"]["material_memory_ids"] == []


def test_contested_memory_preserves_disagreement_instead_of_settling_truth():
    receipt = _receipts()["risk-contested-guidance"]
    assert all(item["validity"]["contested"] for item in receipt["intelligence"])
    assert all(item["evidence"]["decision_material"] for item in receipt["intelligence"])
    decision = receipt["decision"]["with_memory"]
    assert decision["contested_handling"] == "preserve_disagreement"
    assert decision["presented_as_settled"] is False
    assert decision["selected_option"] == "defer_for_human_resolution"


def test_invalidated_memory_is_filtered_and_null_reflection_is_not_material():
    receipts = _receipts()
    invalidated = receipts["implementation-invalidated-memory"]["intelligence"][0]
    assert invalidated["evidence"]["level"] == "invalidated"
    assert invalidated["evidence"]["injected"] is False
    assert invalidated["evidence"]["decision_material"] is False

    null_receipt = receipts["planning-null-relevant-memory"]
    assert null_receipt["decision"]["delta"] == []
    assert null_receipt["intelligence"][0]["evidence"]["level"] == "reflected"
    assert null_receipt["causal_assessment"]["memory_effect_supported"] is False


def test_harmful_memory_remains_material_without_outcome_support():
    receipt = _receipts()["research-harmful-memory"]
    evidence = receipt["intelligence"][0]["evidence"]
    assert evidence["decision_material"] is True
    assert evidence["outcome_supported"] is False
    assert evidence["level"] == "decision-material"
    assert receipt["outcome"]["status"] == "contradicted"


def test_cross_path_case_separates_portability_from_causal_comparison():
    receipt = _receipts()["cross-path-portability"]
    assert receipt["capture_route"]["surface"] == "mcp"
    assert receipt["capture_route"]["model"] == "gpt-5.6"
    assert receipt["route"]["surface"] == "cli"
    assert receipt["route"]["model"] == "qwen3:4b"
    assert receipt["counterfactual"]["matched"] is True
    assert receipt["causal_assessment"]["cross_model_difference_used_as_causal_evidence"] is False
    assert receipt["persistence"]["fresh_client_process"] is True
    assert receipt["persistence"]["cross_surface"] is True


def test_mismatched_counterfactual_degrades_without_false_causal_credit():
    receipt = _receipts()["degraded-mismatched-counterfactual"]
    assert receipt["counterfactual"]["matched"] is False
    assert {item["field"] for item in receipt["counterfactual"]["mismatches"]} >= {
        "provider",
        "model",
        "access_class",
    }
    assert receipt["decision"]["delta"]
    assert receipt["decision"]["material_memory_ids"] == []
    assert receipt["causal_assessment"]["memory_effect_supported"] is False
    assert receipt["completeness"]["status"] == "degraded"


def test_product_isolation_mismatch_degrades_and_blocks_materiality():
    suite = load_decision_delta_suite(FIXTURE)
    case = suite["cases"][0]
    case["memories"][0]["provenance"]["product_id"] = "product:other"
    receipt = build_decision_delta_receipt(case, suite_id=suite["suite_id"])
    assert receipt["isolation"] == {
        "status": "failed",
        "task_product_id": "product:fixture-a",
        "mismatched_memory_ids": ["observation:fixture-correction-1"],
    }
    assert receipt["decision"]["material_memory_ids"] == []
    assert receipt["causal_assessment"]["memory_effect_supported"] is False
    assert "product_isolation_mismatch" in receipt["completeness"]["degraded_reasons"]


def test_fresh_process_replay_preserves_receipt_identity(tmp_path):
    first_json = tmp_path / "first.json"
    second_json = tmp_path / "second.json"
    first_md = tmp_path / "first.md"
    second_md = tmp_path / "second.md"
    command = [sys.executable, "-m", "core.engine.evaluation.decision_delta", str(FIXTURE)]
    for json_out, markdown_out in ((first_json, first_md), (second_json, second_md)):
        result = subprocess.run(
            [*command, "--json-out", str(json_out), "--markdown-out", str(markdown_out)],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
    first = json.loads(first_json.read_text(encoding="utf-8"))
    second = json.loads(second_json.read_text(encoding="utf-8"))
    assert [item["receipt_id"] for item in first["receipts"]] == [item["receipt_id"] for item in second["receipts"]]
    assert first_md.read_text(encoding="utf-8") == second_md.read_text(encoding="utf-8")


def test_human_report_names_limits_and_exact_changes():
    report = render_decision_delta_markdown(_result())
    assert "not live cross-model quality evidence" in report
    assert "Cross-model differences prove a memory effect" in report
    assert "`selected_option`" in report
    assert "degraded-mismatched-counterfactual" in report
