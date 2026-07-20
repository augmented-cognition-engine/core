import json

import pytest

from core.engine.evaluation.harness import evaluate_suite, load_suite, render_markdown

FIXTURE = "evaluations/fixtures/offline_contract.json"


def test_offline_suite_is_deterministic_and_complete():
    result = evaluate_suite(load_suite(FIXTURE))
    assert result == evaluate_suite(load_suite(FIXTURE))
    assert set(result["summary"]) == {"single_model_ungrounded", "ace", "no_memory", "fixed_roster", "no_calibration"}
    assert result["comparable_product_evidence"] is False
    assert result["summary"]["single_model_ungrounded"]["calls_total"] == 1
    assert result["summary"]["ace"]["continuity_mean"] == 1.0


def test_access_paths_are_labels_and_unknown_cost_stays_unknown():
    suite = load_suite(FIXTURE)
    suite["responses"][0]["metrics"]["model"] = "unpriced-model"
    result = evaluate_suite(suite)
    row = result["rows"][0]
    assert row["access_path"] == "api"
    assert row["estimated_cost_usd"] is None


def test_unknown_variant_fails_closed():
    suite = load_suite(FIXTURE)
    suite["responses"][0]["variant"] = "marketing_demo"
    with pytest.raises(ValueError, match="unknown variant"):
        evaluate_suite(suite)


def test_reports_are_machine_and_human_readable():
    result = evaluate_suite(load_suite(FIXTURE))
    json.dumps(result)
    report = render_markdown(result)
    assert "not evidence that ACE outperforms" in report
    assert "Access paths are descriptive, not quality tiers" in report
