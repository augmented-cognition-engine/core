from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.engine.grounded_state.baseline import (
    BaselineDisposition,
    RuntimeBaselineConfigV1,
    RuntimeBaselineResultV1,
    RuntimeCaseInputV1,
    inspect_thin_mcp_surface,
    load_runtime_baseline_config,
    load_temporal_corpus,
    render_runtime_baseline_markdown,
    run_current_ace_baseline,
)

ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "evaluations/fixtures/state_engine_tp0_runtime_baseline_v1.json"
CORPUS = ROOT / "tests/fixtures/grounded_state/temporal_reference_candidate_v1.json"
SURFACE = ROOT / "ace_mcp_client/server.py"
RESULT = ROOT / "evaluations/results/state_engine_tp0_runtime_baseline_v1.json"
EVIDENCE = ROOT / "docs/evidence/state-engine-tp0-runtime-baseline-v1.md"
ROADMAP = ROOT / "docs/design/state-engine-roadmap.md"
CORPUS_HASH = "4b029bff64564abc226d431b373a3d75cbf971c66aa6bb53e2cf29c7198c4b09"
SURFACE_HASH = "7bf2e0959cf19a9aa65d1b53d64e940346ddcc564eccee2d218ee0c616c9662c"
ADAPTER_HASH = "b42ec0dd7a25810ec2c923e3adf6811dbb84db22b9313f3abc86d6c2c6c9b88d"
UTC = timezone.utc


def _run():
    return run_current_ace_baseline(
        load_runtime_baseline_config(CONFIG),
        load_temporal_corpus(CORPUS),
        inspect_thin_mcp_surface(SURFACE),
        executed_at=datetime(2026, 8, 3, 18, tzinfo=UTC),
    )


def test_frozen_baseline_config_declares_zero_write_provider_free_rules():
    config = load_runtime_baseline_config(CONFIG)

    assert config.corpus_hash == CORPUS_HASH
    assert config.adapter_source_sha256 == ADAPTER_HASH
    assert config.public_surface_sha256 == SURFACE_HASH
    assert config.environment.public_surface == "thin_mcp_11_tool_contract"
    assert config.environment.provider_route == "none"
    assert config.environment.model is None
    assert config.environment.database_route == "none"
    assert config.budgets.max_cases == 40
    assert config.budgets.max_model_calls == 0
    assert config.budgets.max_input_tokens == 0
    assert config.budgets.max_output_tokens == 0
    assert config.budgets.max_estimated_cost_usd == 0
    assert config.budgets.max_database_writes == 0
    assert config.seeds.evaluation_seed == 1729
    assert config.rules.unsupported_counts_as_failure is True
    assert config.rules.reference_expectations_hidden_from_adapter is True
    assert config.rules.negative_controls_cannot_pass_vacuously is True
    assert config.rules.prose_is_not_structured_state is True


def test_adapter_input_contract_cannot_receive_the_reference_answers():
    assert "expected" not in RuntimeCaseInputV1.model_fields
    assert "case_key" not in RuntimeCaseInputV1.model_fields
    assert set(RuntimeCaseInputV1.model_fields) == {"input_id", "product_ids", "evidence", "as_of_times"}


def test_current_supported_surface_is_the_frozen_thin_11_tool_contract():
    surface = inspect_thin_mcp_surface(SURFACE)

    assert surface.source_sha256 == SURFACE_HASH
    assert [tool.name for tool in surface.tools] == [
        "ace_briefing",
        "ace_capture",
        "ace_capture_idea",
        "ace_history",
        "ace_impact",
        "ace_load",
        "ace_related",
        "ace_search",
        "ace_start",
        "ace_status",
        "ace_task",
    ]
    capture = next(tool for tool in surface.tools if tool.name == "ace_capture")
    assert not {
        "content_hash",
        "external_id",
        "ingested_at",
        "kind",
        "product_id",
        "source_id",
        "source_version",
        "temporal",
    }.issubset(capture.parameters)
    assert {tool.return_annotation for tool in surface.tools} <= {"dict", "str"}


def test_current_ace_baseline_records_all_cases_as_unsupported_without_vacuous_credit():
    result = _run()

    assert result.corpus_hash == CORPUS_HASH
    # TP0 is frozen historical evidence. It may be replayed from the exact
    # reference environment or from a later release candidate/CI runner. Only
    # machine facts and release identity may differ; execution mode, public
    # surface, provider/model/database routes, and Python implementation stay
    # bound to the frozen baseline.
    if result.environment_matches_reference:
        assert result.environment_differences == ()
    else:
        assert result.environment_differences
        drifted_fields = {difference.partition(":")[0] for difference in result.environment_differences}
        assert drifted_fields <= {
            "ace_version",
            "logical_cpu_count",
            "machine",
            "python_version",
            "release",
            "source_revision",
            "system",
        }
    assert result.summary.total_cases == 40
    assert result.summary.exact_matches == 0
    assert result.summary.unsupported == 40
    assert result.summary.mismatches == 0
    assert result.summary.errors == 0
    assert result.summary.matched_judgments == 0
    assert result.summary.expected_judgments == 247
    assert result.summary.model_calls == 0
    assert result.summary.input_tokens == 0
    assert result.summary.output_tokens == 0
    assert result.summary.estimated_cost_usd == 0
    assert result.summary.database_writes == 0
    assert result.conclusion == "capability_not_established"
    assert all(case.disposition is BaselineDisposition.UNSUPPORTED for case in result.cases)
    assert all(case.exact_match is False for case in result.cases)
    assert all(case.matched_judgments == 0 for case in result.cases)
    assert all(case.prohibited_violations == 0 for case in result.cases)
    assert all(
        case.reason_codes
        == (
            "unsupported_grounded_evidence_ingest_contract",
            "unsupported_structured_state_output_contract",
        )
        for case in result.cases
    )


def test_baseline_replay_has_stable_material_outcome_identity():
    first = _run()
    second = run_current_ace_baseline(
        load_runtime_baseline_config(CONFIG),
        load_temporal_corpus(CORPUS),
        inspect_thin_mcp_surface(SURFACE),
        executed_at=datetime(2026, 8, 4, 18, tzinfo=UTC),
    )

    assert first.executed_at != second.executed_at
    assert first.outcome_hash == second.outcome_hash
    assert [case.case_hash for case in first.cases] == [case.case_hash for case in second.cases]
    assert [case.adapter_input_hash for case in first.cases] == [case.adapter_input_hash for case in second.cases]


def test_baseline_refuses_a_different_corpus_identity():
    config = load_runtime_baseline_config(CONFIG)
    changed = config.model_dump(mode="json")
    changed["corpus_hash"] = "0" * 64

    with pytest.raises(ValueError, match="does not match"):
        run_current_ace_baseline(
            RuntimeBaselineConfigV1.model_validate(changed),
            load_temporal_corpus(CORPUS),
            inspect_thin_mcp_surface(SURFACE),
        )


def test_recorded_result_matches_a_fresh_replay_and_states_the_limitations():
    recorded = RuntimeBaselineResultV1.model_validate(json.loads(RESULT.read_text(encoding="utf-8")))
    replay = _run()

    assert recorded.config_hash == replay.config_hash
    assert recorded.corpus_hash == replay.corpus_hash
    assert recorded.public_surface == replay.public_surface
    assert recorded.summary == replay.summary
    assert recorded.outcome_hash == replay.outcome_hash
    assert recorded.conclusion == replay.conclusion
    documented = EVIDENCE.read_text(encoding="utf-8") + ROADMAP.read_text(encoding="utf-8")
    assert recorded.config_hash in documented
    assert recorded.corpus_hash in documented
    assert recorded.outcome_hash in documented
    markdown = render_runtime_baseline_markdown(recorded)
    assert "All 40 cases therefore remain unsupported" in markdown
    assert "not evidence" in markdown
    assert "TP1 or TP2 is complete" in markdown
