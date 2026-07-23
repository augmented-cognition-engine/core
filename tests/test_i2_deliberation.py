"""Deterministic contract and supported-path coverage for I2."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

from core.engine.cli.commands.run import run
from core.engine.orchestration.agent import AgentResult
from core.engine.product.deliberation import (
    CONTRACT_VERSION,
    build_deliberation_receipt,
    extract_attribution_artifact,
    normalize_deliberation_receipt,
    runtime_deliberation_receipt,
)
from core.engine.product.living_graph import _project_record
from scripts.verify_i2_deliberation import evaluate, render_markdown

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "evaluations/fixtures/i2_attributable_deliberation_v1.json"


def _receipts() -> dict[str, dict]:
    return {item["selection"]["reasoning_shape"]: item for item in evaluate(FIXTURE)["receipts"]}


def test_frozen_public_data_matrix_is_deterministic_and_covers_all_required_paths():
    first = evaluate(FIXTURE)
    second = evaluate(FIXTURE)
    assert first == second
    assert first["contract_version"] == CONTRACT_VERSION
    assert first["summary"] == {
        "receipts": 4,
        "reasoning_shapes": ["adversarial", "independent", "pipeline", "team"],
        "complete": 3,
        "degraded": 1,
        "conflicts": 3,
        "public_mcp_tools": 11,
    }
    assert first["scenario"]["public_source"] == "UCI Online Retail II"
    assert "doi:10.24432/C5F88Q" in first["scenario"]["evidence_catalog"]
    assert "hidden reasoning" in render_markdown(first)


def test_adversarial_synthesis_traces_every_disposition_to_positions_and_evidence():
    receipt = _receipts()["adversarial"]
    grouped = receipt["synthesis"]["by_disposition"]
    assert {name: len(items) for name, items in grouped.items()} == {
        "accepted": 1,
        "rejected": 1,
        "contested": 1,
        "bounded": 1,
    }
    assert receipt["synthesis"]["unresolved_contribution_ids"] == []
    assert all(item["position"] for item in receipt["synthesis"]["dispositions"])
    assert all(item["contributor_evidence_ids"] for item in receipt["synthesis"]["dispositions"])
    assert all(conflict["derived_from_persona_or_role_labels"] is False for conflict in receipt["conflicts"])
    contribution_ids = {item["contribution_id"] for item in receipt["contributors"]}
    assert all(set(conflict["contribution_ids"]) <= contribution_ids for conflict in receipt["conflicts"])


def test_partial_team_run_preserves_missing_failure_timeout_taint_and_degraded_synthesis():
    receipt = _receipts()["team"]
    coverage = receipt["coverage"]
    assert coverage["state"] == "partial"
    assert coverage["missing_contributors"] == ["planned-contributor-4"]
    assert len(coverage["failed_contribution_ids"]) == 1
    assert len(coverage["timed_out_contribution_ids"]) == 1
    assert coverage["tainted_phases"] == ["team_synthesis"]
    assert coverage["degraded_synthesis"] is True
    assert receipt["synthesis"]["unresolved_contribution_ids"]
    serialized = json.dumps(receipt)
    assert "fixture-secret" not in serialized
    assert "<redacted>" in serialized


def test_selection_uses_bounded_observable_signals_and_not_private_task_text():
    for receipt in _receipts().values():
        assert receipt["selection"]["reasoning_shape"]
        assert receipt["selection"]["selection_reasons"]
        assert receipt["selection"]["observable_classification_only"] is True
        assert "description" not in receipt["selection"]["signals"]
        for contributor in receipt["contributors"]:
            assert contributor["attribution"] == {
                "basis": "execution_identity",
                "persona_or_role_label_used_as_identity": False,
            }


def test_final_artifact_parser_strips_metadata_and_ignores_unapproved_fields():
    output = """Recommendation for the user.\n\n```ace-attribution
{"position":"Keep staged","assumptions":["C-prefix remains documented"],"evidence_ids":["doi:10.24432/C5F88Q"],"confidence":0.8,"gaps":[],"chain_of_thought":"must never survive","prompt":"private"}
```"""
    public, artifact = extract_attribution_artifact(output)
    assert public == "Recommendation for the user."
    assert artifact is not None
    assert artifact["position"] == "Keep staged"
    assert "chain_of_thought" not in artifact
    assert "prompt" not in artifact


def test_runtime_projection_uses_structured_final_artifacts_without_transcripts():
    contributor = AgentResult(
        agent_id="execution:runtime-a",
        status="completed",
        output="Full final answer remains on the ordinary output surface.",
        duration_ms=11,
        structured_output={
            "position": "Keep staged",
            "recommendation": "Measure both guardrails",
            "assumptions": ["Definitions are frozen"],
            "evidence_ids": ["metric:cancelled-invoice-rate"],
            "confidence": 0.8,
            "gaps": [],
        },
        metadata={"i2_artifact_kind": "contribution", "i2_phase": "team_position"},
    )
    synthesis = AgentResult(
        agent_id="execution:runtime-synthesis",
        status="completed",
        output="Keep staged.",
        structured_output={
            "summary": "Keep staged.",
            "dispositions": [
                {"contributor_id": "execution:runtime-a", "status": "accepted", "reason": "guardrail evidence"}
            ],
            "conflicts": [],
            "gaps": [],
        },
        metadata={"i2_artifact_kind": "synthesis", "i2_phase": "synthesis"},
    )
    result = SimpleNamespace(
        pattern_result=SimpleNamespace(pattern_name="team", agent_results=[contributor, synthesis]),
    )
    receipt = runtime_deliberation_receipt(
        task_id="task:runtime-i2",
        product_id="product:i2",
        result=result,
        reasoning_trace={
            "selection": {
                "reasoning_shape": "team",
                "mode": "deliberative",
                "signals": {"complexity": "complex"},
                "selection_reasons": ["Multiple bounded positions requested"],
            }
        },
        execution={"contributors": {"expected": 1}, "phases": {"tainted_ids": []}},
    )
    artifact = receipt["contributors"][0]["artifact"]
    assert artifact["position"] == "Keep staged"
    assert artifact["source"] == "structured_final_artifact"
    assert "Full final answer" not in json.dumps(receipt)
    assert receipt["synthesis"]["state"] == "complete"


def test_unknown_version_and_cross_product_receipt_fail_closed_without_leaking_artifacts():
    task = {"id": "task:i2", "product": "product:i2"}
    future = normalize_deliberation_receipt({"contract_version": "deliberation-receipt-v99"}, task=task)
    assert future["contributors"] == []
    assert future["completeness"]["missing_or_degraded"] == [
        "unsupported_deliberation_receipt_version:deliberation-receipt-v99"
    ]
    foreign = normalize_deliberation_receipt(
        {
            "contract_version": CONTRACT_VERSION,
            "receiving": {"task_id": "task:foreign", "product_id": "product:foreign"},
            "contributors": [{"artifact": {"position": "private foreign position"}}],
        },
        task=task,
    )
    assert foreign["receiving"] == {"task_id": "task:i2", "product_id": "product:i2"}
    assert foreign["contributors"] == []
    assert "private foreign position" not in json.dumps(foreign)


def test_same_product_stored_receipt_is_recanonicalized_to_the_public_allowlist():
    receipt = _receipts()["independent"]
    receipt["chain_of_thought"] = "top-level private reasoning"
    receipt["contributors"][0]["artifact"]["scratchpad"] = "nested private reasoning"
    receipt["synthesis"]["prompt"] = "private prompt"
    normalized = normalize_deliberation_receipt(
        receipt,
        task={"id": receipt["receiving"]["task_id"], "product": receipt["receiving"]["product_id"]},
    )
    serialized = json.dumps(normalized)
    assert "chain_of_thought" not in serialized
    assert "scratchpad" not in serialized
    assert "private prompt" not in serialized


def test_living_product_graph_projects_the_same_bounded_receipt():
    receipt = _receipts()["pipeline"]
    projected = _project_record(
        "tasks",
        {
            "id": "task:i2-pipeline",
            "product": "product:i2-public-retail",
            "status": "completed",
            "deliberation_receipt": receipt,
        },
    )
    assert projected["deliberation_receipt"] == receipt


def test_cli_offers_explicit_deliberation_inspection_without_new_command():
    help_result = CliRunner().invoke(run, ["--help"])
    assert help_result.exit_code == 0
    assert "--show-deliberation" in help_result.output


def test_schema_migration_is_additive_and_does_not_rewrite_legacy_tasks():
    migration = (ROOT / "core/schema/v156_i2_deliberation_receipt.surql").read_text(encoding="utf-8")
    assert "DEFINE FIELD IF NOT EXISTS deliberation_receipt ON TABLE task" in migration
    assert "UPDATE task" not in migration
    assert "DELETE" not in migration


def test_builder_never_accepts_role_labels_as_attribution_identity():
    case = {
        "receiving": {"task_id": "task:role-only", "product_id": "product:i2"},
        "selection": {"reasoning_shape": "team", "selection_reasons": ["fixture"]},
        "contributors": [{"role": "skeptic", "artifact": {"position": "A role is not an identity"}}],
    }
    try:
        build_deliberation_receipt(case)
    except ValueError as exc:
        assert "execution contributor_id" in str(exc)
    else:  # pragma: no cover - contract must fail closed
        raise AssertionError("role-only attribution was accepted")


def test_incomplete_execution_cannot_be_rendered_as_complete_synthesis():
    case = {
        "receiving": {"task_id": "task:failed-extension", "product_id": "product:i2"},
        "selection": {"reasoning_shape": "team", "selection_reasons": ["fixture"]},
        "expected_contributors": 2,
        "missing_contributors": ["execution:missing"],
        "contributors": [
            {
                "contributor_id": "execution:extension-failed",
                "execution": {"status": "failed", "route": "extension"},
                "artifact": {"gaps": ["Provider failed before a final artifact was produced"]},
            }
        ],
        "synthesis": {"state": "complete", "summary": "Caller claims completion", "dispositions": []},
    }
    receipt = build_deliberation_receipt(case)
    assert receipt["coverage"]["state"] == "partial"
    assert receipt["coverage"]["failed_contribution_ids"]
    assert receipt["synthesis"]["state"] == "degraded"
    assert receipt["synthesis"]["degraded"] is True
    assert "synthesis_based_on_partial_execution" in receipt["completeness"]["missing_or_degraded"]


def test_conflicts_require_artifact_lineage_not_role_names():
    case = {
        "receiving": {"task_id": "task:role-conflict", "product_id": "product:i2"},
        "selection": {"reasoning_shape": "adversarial", "selection_reasons": ["fixture"]},
        "contributors": [
            {"contributor_id": "execution:a", "artifact": {"position": "Stage the change"}},
            {"contributor_id": "execution:b", "artifact": {"position": "Reject the change"}},
        ],
        "conflicts": [{"contributor_ids": ["advocate", "skeptic"], "issue": "Release timing"}],
        "synthesis": {
            "summary": "Keep the issue contested",
            "dispositions": [
                {"contributor_id": "execution:a", "status": "contested"},
                {"contributor_id": "execution:b", "status": "contested"},
            ],
        },
    }
    receipt = build_deliberation_receipt(case)
    assert receipt["conflicts"] == []
    assert "conflicts[0]_missing_artifact_lineage" in receipt["completeness"]["missing_or_degraded"]
