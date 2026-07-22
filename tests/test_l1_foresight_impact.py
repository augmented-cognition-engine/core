from __future__ import annotations

import json
from pathlib import Path

from core.engine.evaluation.foresight_impact import (
    CONTRACT_VERSION,
    evaluate_foresight_impact,
)


def _case(index: int, *, ace: float = 0.0, control: float = 1.0, matching: str = "matched") -> dict:
    return {
        "case_id": f"case:{index}",
        "cluster_id": f"cluster:{index % 10}",
        "outcome": {
            "outcome_id": f"outcome:{index}",
            "value": 0.0,
            "observed_at": "sequence:03",
            "resolution_eligible": True,
            "evidence_refs": [f"evidence:{index}"],
        },
        "arms": {
            "ace_foresight": {
                "prediction": ace,
                "material_use": True,
                "source_resolutions": [
                    {
                        "resolution_id": f"resolution:{index}",
                        "resolved_at": "sequence:02",
                    }
                ],
            },
            "no_foresight": {"prediction": control},
            "naive_base_rate": {"prediction": control},
            "model_only": {"prediction": control},
        },
        "matching": {
            "state": matching,
            "provider": "test-provider",
            "model": "test-model",
            "configuration_hash": "sha256:test",
        },
    }


def _study(cases: list[dict], *, attribution: str = "randomized_verified") -> dict:
    return {
        "scenario_id": "l1-test",
        "score_contract": {
            "method": "continuous_absolute_error/v1",
            "metric": "quality",
        },
        "attribution": {
            "state": attribution,
            "assignment": "verified",
            "intervention_identity": "intervention:test",
        },
        "cases": cases,
    }


def test_supports_benefit_only_against_every_required_control() -> None:
    result = evaluate_foresight_impact(_study([_case(index) for index in range(40)]))

    assert result["contract_version"] == CONTRACT_VERSION
    assert result["state"] == "benefit_supported"
    assert result["beneficial_impact_supported"] is True
    assert {item["control"] for item in result["comparisons"]} == {
        "no_foresight",
        "naive_base_rate",
        "model_only",
    }
    assert all(item["benefit_supported"] for item in result["comparisons"])


def test_missing_matched_model_control_blocks_claim_but_preserves_other_comparisons() -> None:
    cases = [_case(index, matching="model_only_control_not_run") for index in range(40)]
    result = evaluate_foresight_impact(_study(cases))
    comparisons = {item["control"]: item for item in result["comparisons"]}

    assert result["beneficial_impact_supported"] is False
    assert comparisons["no_foresight"]["benefit_supported"] is True
    assert comparisons["naive_base_rate"]["benefit_supported"] is True
    assert comparisons["model_only"]["case_count"] == 0
    assert comparisons["model_only"]["reason"] == "insufficient_case_count"


def test_harmful_or_null_required_control_blocks_claim() -> None:
    cases = [_case(index, ace=0.5, control=0.0) for index in range(40)]
    result = evaluate_foresight_impact(_study(cases))

    assert result["beneficial_impact_supported"] is False
    assert all(item["mean_error_reduction"] < 0 for item in result["comparisons"])
    assert all(item["reason"] == "cluster_adjusted_interval_includes_no_benefit" for item in result["comparisons"])


def test_observational_attribution_blocks_even_strong_predictive_lift() -> None:
    result = evaluate_foresight_impact(
        _study([_case(index) for index in range(40)], attribution="retrospective_observational")
    )

    assert all(item["benefit_supported"] for item in result["comparisons"])
    assert result["beneficial_impact_supported"] is False
    assert "intervention_or_confounder_attribution_not_supported" in result["reason_codes"]


def test_missing_or_post_outcome_lineage_is_ineligible() -> None:
    cases = [_case(index) for index in range(40)]
    cases[0]["arms"]["ace_foresight"]["source_resolutions"] = []
    cases[1]["arms"]["ace_foresight"]["source_resolutions"][0]["resolved_at"] = "sequence:04"
    result = evaluate_foresight_impact(_study(cases))

    assert result["sample"]["ineligible_case_count"] == 2
    assert result["sample"]["invalid_reason_counts"] == {
        "missing_resolved_foresight_lineage": 1,
        "post_outcome_or_ambiguous_foresight_source": 1,
    }


def test_small_sample_and_cluster_count_never_force_a_ranking() -> None:
    cases = [_case(index) for index in range(7)]
    result = evaluate_foresight_impact(_study(cases))

    assert result["state"] == "benefit_not_established"
    assert all(item["reason"] == "insufficient_case_count" for item in result["comparisons"])


def test_public_projection_redacts_credentials_and_bounds_cases() -> None:
    cases = [_case(index) for index in range(300)]
    cases[0]["outcome"]["evidence_refs"] = ["api_key=top-secret"]
    study = _study(cases)
    study["attribution"]["confounders"] = ["Bearer secret-value"]
    result = evaluate_foresight_impact(study)

    assert len(result["cases"]) == 256
    assert "case_limit_exceeded" in result["reason_codes"]
    assert result["cases"][0]["outcome"]["evidence_refs"] == ["[REDACTED]"]
    assert result["attribution"]["confounders"] == ["[REDACTED]"]


def test_frozen_public_probe_remains_honestly_not_established() -> None:
    fixture = Path("evaluations/fixtures/l1_foresight_impact_v1.json")
    result_path = Path("evaluations/results/l1_foresight_impact_v1.json")
    assert fixture.exists()
    assert result_path.exists()
    study = json.loads(fixture.read_text(encoding="utf-8"))
    recorded = json.loads(result_path.read_text(encoding="utf-8"))

    assert evaluate_foresight_impact(study) == recorded
    assert recorded["beneficial_impact_supported"] is False
    assert recorded["state"] == "benefit_not_established"
