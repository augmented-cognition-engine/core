"""Structural and failure-contract tests for the public R4 golden path."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from scripts import verify_product_builder_golden_path as golden


@pytest.fixture
def scenario() -> dict:
    return golden._scenario(golden.DEFAULT_SCENARIO)


def _output(sections: list[str]) -> str:
    values = {
        "RECOMMENDATION": "A bounded hybrid selected by the reasoning run.",
        "EVIDENCE": "SRC-UCI-468-DATASET and SRC-UCI-468-RETURNING support the observed reach claim.",
        "DISSENT": "The observational snapshot cannot establish causality.",
        "UNCERTAINTY": "Current intent and accessibility evidence are missing.",
        "REVERSAL_CRITERIA": "Reverse if a pre-registered experiment harms completion.",
        "DECISION": "Run one reversible experiment.",
        "PRIOR_CONSTRAINT_APPLIED": "R4-CORRECTION-PRIVACY-FIRST-V1",
        "MATERIAL_CHANGE": "The earlier targeted plan is replaced with a universal flow.",
        "REJECTED_OR_MODIFIED": "A_TARGETED_EXIT_RECOVERY is rejected because behavioral targeting is disallowed.",
        "NEXT_EXPERIMENT": "Test universal navigation for every session.",
    }
    return "\n".join(f"{section}: {values.get(section, 'bounded')}" for section in sections)


def _receipt(output: str) -> dict:
    return {
        "id": "task:test",
        "status": "completed",
        "output": output,
        "reasoning_trace": {
            "classification": {
                "domain_path": "product_strategy",
                "discipline": "product",
                "archetype": "advisor",
                "mode": "deliberative",
            },
            "dispatch": {"pattern": "pipeline", "agent_count": 3, "stages": ["frame", "challenge", "decide"]},
            "composition": {"roster": ["product", "user", "skeptic"], "phases": []},
            "provenance": {
                "task_id": "task:test",
                "provider": "TestProvider",
                "model": "test-model",
                "duration_ms": 100,
                "token_usage": None,
            },
        },
    }


def test_fixture_freezes_public_question_correction_license_and_checksums(scenario):
    assert scenario["scenario_id"] == "r4-online-shopper-release-v1"
    assert len(scenario["options"]) == 2
    assert scenario["human_correction"]["id"] == "R4-CORRECTION-PRIVACY-FIRST-V1"
    assert scenario["provenance"]["license"] == "Creative Commons Attribution 4.0 International (CC BY 4.0)"
    assert len(scenario["provenance"]["archive_sha256"]) == 64
    assert len(scenario["provenance"]["csv_sha256"]) == 64


def test_initial_prompt_starts_from_product_decision_and_cites_frozen_sources(scenario):
    prompt = golden._initial_prompt(scenario)
    assert prompt.startswith("Product decision:")
    assert "A_TARGETED_EXIT_RECOVERY" in prompt
    assert "B_UNIVERSAL_NAVIGATION" in prompt
    assert "SRC-UCI-468-DATASET" in prompt
    assert "RECOMMENDATION:" in prompt
    assert "kernel" not in prompt.lower()
    assert "surrealdb" not in prompt.lower()


def test_later_prompt_does_not_leak_correction_identifier_or_text(scenario):
    prompt = golden._later_prompt(scenario)
    correction = scenario["human_correction"]
    assert correction["id"] not in prompt
    assert correction["content"] not in prompt
    assert "NO_PRIOR_CONSTRAINT" in prompt


def test_all_persistence_reads_use_the_exact_capture_domain():
    assert golden._intelligence_params() == {
        "q": "product_strategy.online_conversion",
        "product": "product:default",
    }


def test_structural_assertions_accept_non_exact_recommendation(scenario):
    sections = scenario["acceptance_invariants"]["initial_output_sections"]
    result = golden._validate_reasoning_receipt(_receipt(_output(sections)), scenario, sections, "test")
    assert result["source_ids"] == ["SRC-UCI-468-DATASET", "SRC-UCI-468-RETURNING"]
    assert result["provenance"]["provider"] == "TestProvider"
    assert result["token_cost_posture"]["cost_usd"] is None


def test_structural_assertions_reject_missing_evidence_ids(scenario):
    sections = scenario["acceptance_invariants"]["initial_output_sections"]
    receipt = _receipt(_output(sections).replace("SRC-UCI-468-RETURNING", "uncited evidence"))
    with pytest.raises(golden.GoldenPathError, match="distinct frozen source IDs"):
        golden._validate_reasoning_receipt(receipt, scenario, sections, "test")


def test_structural_assertions_reject_missing_reasoning_shape(scenario):
    sections = scenario["acceptance_invariants"]["initial_output_sections"]
    receipt = _receipt(_output(sections))
    receipt["reasoning_trace"]["dispatch"] = {}
    receipt["reasoning_trace"]["composition"] = {}
    with pytest.raises(golden.GoldenPathError, match="no inspectable composition"):
        golden._validate_reasoning_receipt(receipt, scenario, sections, "test")


def test_structural_assertions_reject_missing_provider_provenance(scenario):
    sections = scenario["acceptance_invariants"]["initial_output_sections"]
    receipt = _receipt(_output(sections))
    receipt["reasoning_trace"]["provenance"]["provider"] = None
    with pytest.raises(golden.GoldenPathError, match="lacks provider"):
        golden._validate_reasoning_receipt(receipt, scenario, sections, "test")


@pytest.mark.parametrize("status", ["failed", "degraded", "running"])
def test_non_completed_receipts_fail_honestly(status, scenario):
    sections = scenario["acceptance_invariants"]["initial_output_sections"]
    receipt = _receipt(_output(sections))
    receipt["status"] = status
    with pytest.raises(golden.GoldenPathError, match="did not complete"):
        golden._validate_reasoning_receipt(receipt, scenario, sections, "test")


@pytest.mark.parametrize("status", [401, 403])
def test_missing_or_stale_authentication_names_login_recovery(status):
    request = httpx.Request("GET", "http://localhost:3000/intel/context")
    response = httpx.Response(status, request=request)
    error = golden._http_failure(httpx.HTTPStatusError("denied", request=request, response=response), "auth")
    assert "ace login" in error.action
    assert str(status) in str(error)


def test_database_or_api_unavailable_names_service_recovery():
    request = httpx.Request("GET", "http://localhost:3000/health")
    error = golden._http_failure(httpx.ConnectError("down", request=request), "health")
    assert "ace service start" in error.action


def test_malformed_source_fixture_fails_before_reasoning(tmp_path):
    fixture = tmp_path / "bad.json"
    fixture.write_text("{bad", encoding="utf-8")
    with pytest.raises(golden.GoldenPathError, match="malformed"):
        golden._scenario(fixture)


def test_source_checksum_mismatch_fails_before_derivation(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("VisitorType,Revenue,ExitRates,BounceRates,ProductRelated\n", encoding="utf-8")
    with pytest.raises(golden.GoldenPathError, match="checksum mismatch"):
        golden._verify_source(source, golden.DEFAULT_SCENARIO)


def test_failure_contract_exercises_all_required_cases(tmp_path):
    output = tmp_path / "failures.json"
    golden._failure_fixtures(output)
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["status"] == "passed"
    assert len(evidence["cases"]) == 7
    assert {item["case"] for item in evidence["cases"]} == {
        "provider_unavailable_or_timed_out",
        "missing_authentication",
        "database_unavailable",
        "stale_saved_login",
        "malformed_or_missing_source",
        "restart_before_completion",
        "prior_correction_unavailable",
    }
    assert evidence["silent_provider_substitution_allowed"] is False
    assert evidence["invented_evidence_allowed"] is False


def test_default_paths_follow_existing_evaluation_conventions():
    for path in (golden.DEFAULT_SCENARIO, golden.DEFAULT_STATE, golden.DEFAULT_LIVE, golden.DEFAULT_FAILURES):
        assert isinstance(path, Path)
        assert "evaluations" in path.parts
