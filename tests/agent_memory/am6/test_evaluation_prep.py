"""AM6 provider-free measurement contracts and deterministic harness conformance."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from ace.intelligence.agent_memory_evaluation import compare_memory_conditions
from ace.intelligence.contracts.agent_memory_evaluation import (
    BenefitDisposition,
    CausalityDisposition,
    EvaluationCaseGate,
    MaterialInfluenceDisposition,
    MeasureAvailability,
    MeasureDirection,
    MemoryEvaluationCondition,
    MemoryEvaluationProtocolV1Alpha1,
    MemoryMatchedComparisonV1Alpha1,
    MemoryMeasure,
    MemoryRunObservationV1Alpha1,
)
from evaluations.source.agent_memory_am6_evaluation import (
    FIXTURE_PATH,
    _build_assignment,
    _build_corpus,
    _build_observation,
    _build_protocol,
    run_provider_free_fixture,
)

pytestmark = pytest.mark.unit
REPO = Path(__file__).resolve().parents[3]
RESULT_PATH = REPO / "evaluations/results/agent_memory_am6_evaluation_prep_v1.json"
CONTRACT_PATH = REPO / "ace/intelligence/contracts/agent_memory_evaluation.py"
EVALUATOR_PATH = REPO / "ace/intelligence/agent_memory_evaluation.py"
THIN_MCP_PATH = REPO / "ace_mcp_client/server.py"


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def _scenario(case_id: str):
    fixture = _fixture()
    corpus = _build_corpus(fixture)
    protocol = _build_protocol(fixture, corpus)
    raw_case = next(item for item in fixture["cases"] if item["case_id"] == case_id)
    assigned_at = protocol.preregistered_at + timedelta(minutes=1)
    assignment = _build_assignment(fixture, corpus, protocol, raw_case, assigned_at=assigned_at)
    observations = tuple(
        _build_observation(
            corpus,
            protocol,
            assignment,
            raw_case,
            condition,
            observed_at=assigned_at + timedelta(seconds=index + 1),
        )
        for index, condition in enumerate(MemoryEvaluationCondition)
    )
    return corpus, protocol, assignment, observations


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_corpus_covers_am0_am3_measurement_families_and_exact_am4_placeholders() -> None:
    corpus = _build_corpus(_fixture())
    tags = {tag for case in corpus.cases for tag in case.coverage_tags}
    assert {
        "episodic_experience",
        "identity",
        "learned_fact",
        "active_context",
        "preference",
        "instruction_policy_proposal",
        "uncertainty",
        "correction",
        "conflict",
        "ledger_time",
        "knowledge_time",
        "world_time",
        "scope",
        "privacy",
        "authorization_denial",
        "stale",
        "superseded",
        "context_manifest",
        "degraded_retrieval",
        "restart",
        "decision_material",
    }.issubset(tags)
    gated = [case for case in corpus.cases if case.gate is EvaluationCaseGate.FUTURE_ACCEPTED_AM4]
    assert {case.case_id for case in gated} == {
        "am4_export_import_placeholder",
        "am4_hard_erasure_placeholder",
        "am4_retention_expiry_placeholder",
    }
    assert all(case.future_required_coordinate == "future_accepted_am4_coordinate" for case in gated)


def test_protocol_freezes_complete_measure_registry_controls_and_policy_inertness() -> None:
    corpus = _build_corpus(_fixture())
    protocol = _build_protocol(_fixture(), corpus)
    assert set(protocol.conditions) == set(MemoryEvaluationCondition)
    assert {item.measure for item in protocol.measure_definitions} == set(MemoryMeasure)
    unauthorized = next(
        item for item in protocol.measure_definitions if item.measure is MemoryMeasure.UNAUTHORIZED_RETRIEVAL_COUNT
    )
    assert unauthorized.direction is MeasureDirection.ZERO_TOLERANCE
    assert protocol.provider_required is False
    assert protocol.network_required is False
    assert not any(
        (
            protocol.changes_rank_policy,
            protocol.changes_retention_policy,
            protocol.changes_consolidation_policy,
            protocol.changes_promotion_policy,
            protocol.changes_roster_or_authority,
            protocol.delivers_or_sends_effect,
        )
    )


def test_assignment_holds_provider_model_prompt_task_schema_toolset_and_configuration_constant() -> None:
    _, _, assignment, _ = _scenario("am3_manifest_selection_omission")
    assert {item.condition for item in assignment.condition_plans} == set(MemoryEvaluationCondition)
    coordinates = assignment.matched_coordinates
    assert coordinates.provider.artifact_id == "provider:deterministic-fixture"
    assert coordinates.model.artifact_id == "model:none"
    assert coordinates.task.artifact_id == "task:am3_manifest_selection_omission"
    assert coordinates.prompt_contract.artifact_id == "prompt:am6-frozen-v1"
    assert coordinates.decision_schema.artifact_id == "decision-schema:bounded-choice-v1"
    assert coordinates.toolset.artifact_id == "toolset:eleven-thin-mcp-unchanged"
    assert coordinates.configuration.artifact_id == "configuration:am6-provider-free-v1"


def test_provider_free_fixture_reports_beneficial_harmful_neutral_and_underpowered_without_causality() -> None:
    result = run_provider_free_fixture()
    assert result["outcome_counts"] == {"beneficial": 8, "harmful": 1, "neutral": 4, "underpowered": 5}
    assert result["case_count"] == 18
    assert result["condition_count"] == 3
    assert result["observation_count"] == 54
    assert result["measure_count"] == len(MemoryMeasure)
    assert result["network_used"] is False
    assert result["provider_credentials_used"] is False
    assert result["policy_changes_emitted"] == 0
    assert result["restart_reconstruction_identical"] is True
    assert {item["causality"] for item in result["results"]} == {CausalityDisposition.NOT_ESTABLISHED.value}


def test_material_influence_is_distinct_from_neutral_benefit_and_correctness() -> None:
    corpus, protocol, assignment, observations = _scenario("am3_material_but_neutral")
    comparison = compare_memory_conditions(
        corpus=corpus,
        protocol=protocol,
        assignment=assignment,
        observations=observations,
        compared_at=assignment.assigned_at + timedelta(seconds=10),
    )
    assert comparison.material_influence is MaterialInfluenceDisposition.OBSERVED
    assert comparison.benefit is BenefitDisposition.NEUTRAL
    assert comparison.correctness.value == "correct"
    assert comparison.causality is CausalityDisposition.NOT_ESTABLISHED


def test_zero_tolerance_unauthorized_retrieval_is_harmful_and_never_policy_applying() -> None:
    corpus, protocol, assignment, observations = _scenario("am3_authorization_denial")
    memory = next(item for item in observations if item.condition is MemoryEvaluationCondition.MEMORY)
    changed = memory.model_dump(mode="python")
    changed["observation_id"] = None
    changed["observation_digest"] = None
    measurements = []
    for item in changed["measurements"]:
        if item["measure"] is MemoryMeasure.UNAUTHORIZED_RETRIEVAL_COUNT and item["stratum"] is None:
            item["value"] = 1
        measurements.append(item)
    changed["measurements"] = tuple(measurements)
    unauthorized = MemoryRunObservationV1Alpha1.model_validate(changed)
    mutated = tuple(
        unauthorized if item.condition is MemoryEvaluationCondition.MEMORY else item for item in observations
    )
    comparison = compare_memory_conditions(
        corpus=corpus,
        protocol=protocol,
        assignment=assignment,
        observations=mutated,
        compared_at=assignment.assigned_at + timedelta(seconds=10),
    )
    assert comparison.benefit is BenefitDisposition.HARMFUL
    assert comparison.correctness.value == "incorrect"
    assert comparison.changes_any_policy is False
    assert comparison.changes_authority_or_roster is False


def test_missing_telemetry_and_optional_signals_are_explicitly_underpowered() -> None:
    result = run_provider_free_fixture()
    by_case = {item["case_id"]: item for item in result["results"]}
    for case_id in ("am3_degraded_retrieval_signal", "am3_missing_resource_telemetry"):
        item = by_case[case_id]
        assert item["benefit_disposition"] == "underpowered"
        assert item["material_influence"] == "underpowered"
        assert item["paired_and_controlled"] is False
        assert item["missing_measurements"]


def test_am4_placeholders_are_unavailable_and_do_not_mint_runtime_contracts() -> None:
    result = run_provider_free_fixture()
    gated = [item for item in result["results"] if item["gate"] == "future_accepted_am4"]
    assert len(gated) == 3
    assert all(item["benefit_disposition"] == "underpowered" for item in gated)
    assert all("future_accepted_am4_coordinate:required" in item["missing_measurements"] for item in gated)
    source = CONTRACT_PATH.read_text() + EVALUATOR_PATH.read_text()
    assert "agent_memory_am4" not in source
    assert "RetentionPolicy" not in source
    assert "ErasureService" not in source
    assert "ExportService" not in source


def test_contracts_are_provider_host_extension_and_am4_runtime_free() -> None:
    forbidden = ("ace_mcp_client", "core.engine", "extensions", "fastapi", "httpx", "surrealdb")
    offenders = [
        f"{path.relative_to(REPO)}:{name}"
        for path in (CONTRACT_PATH, EVALUATOR_PATH)
        for name in _imports(path)
        if name.startswith(forbidden)
    ]
    assert offenders == []


def test_unknown_or_mutated_protocol_material_fails_strictly() -> None:
    corpus = _build_corpus(_fixture())
    protocol = _build_protocol(_fixture(), corpus)
    changed = protocol.model_dump(mode="python")
    changed["contract"] = "ace.intelligence.agent-memory-evaluation-protocol/v9"
    changed["protocol_id"] = None
    changed["protocol_digest"] = None
    with pytest.raises(ValidationError):
        MemoryEvaluationProtocolV1Alpha1.model_validate(changed)


def test_frozen_result_matches_fresh_fixture_and_subprocess_reconstruction() -> None:
    expected = json.loads(RESULT_PATH.read_text())
    assert run_provider_free_fixture() == expected
    environment = {**os.environ, "ACE_DISABLE_EXTENSIONS": "1"}
    command = (
        "import json; "
        "from evaluations.source.agent_memory_am6_evaluation import run_provider_free_fixture; "
        "print(json.dumps(run_provider_free_fixture(),sort_keys=True,separators=(',',':')))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", command],
        cwd=REPO,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == expected


def test_route_tier_frequency_and_exact_eleven_mcp_boundary_remain_visible() -> None:
    result = run_provider_free_fixture()
    assert sum(result["route_frequency"].values()) == result["observation_count"]
    assert sum(result["tier_frequency"].values()) == result["observation_count"]
    tree = ast.parse(THIN_MCP_PATH.read_text(), filename=str(THIN_MCP_PATH))
    names = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if decorator.func.attr == "tool":
                for keyword in decorator.keywords:
                    if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                        names.append(str(keyword.value.value))
    assert len(names) == 11
    assert len(names) == len(set(names))


def test_underpowered_contract_requires_explicit_missing_coordinates() -> None:
    corpus, protocol, assignment, observations = _scenario("am3_missing_resource_telemetry")
    comparison = compare_memory_conditions(
        corpus=corpus,
        protocol=protocol,
        assignment=assignment,
        observations=observations,
        compared_at=assignment.assigned_at + timedelta(seconds=10),
    )
    changed = comparison.model_dump(mode="python")
    changed["missing_measurements"] = ()
    changed["comparison_id"] = None
    changed["comparison_digest"] = None
    with pytest.raises(ValidationError, match="underpowered benefit disposition"):
        MemoryMatchedComparisonV1Alpha1.model_validate(changed)


def test_unavailable_measurement_cannot_silently_default_to_zero() -> None:
    _, _, _, observations = _scenario("am3_missing_resource_telemetry")
    memory = next(item for item in observations if item.condition is MemoryEvaluationCondition.MEMORY)
    cost = next(item for item in memory.measurements if item.measure is MemoryMeasure.COST_MICROUNITS)
    assert cost.availability is MeasureAvailability.UNAVAILABLE
    assert cost.value is None
    assert cost.unavailable_reason == "cost_telemetry_unavailable"
