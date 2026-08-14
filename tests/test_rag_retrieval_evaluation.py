import json
from pathlib import Path

from core.engine.evaluation.rag_retrieval import evaluate_rag_fixture


def test_frozen_rag_retrieval_v1_passes() -> None:
    fixture = Path(__file__).parents[1] / "evaluations" / "fixtures" / "rag_retrieval_v1.json"
    result = evaluate_rag_fixture(fixture)

    assert result["passed"] is True
    assert result["cases_evaluated"] == 5
    assert result["recall_at_k"] == 1.0
    assert result["mrr"] == 1.0
    assert result["false_associations"] == 0
    assert len(result["fixture_hash"]) == 64
    assert len(result["result_hash"]) == 64


def test_recorded_rag_result_matches_frozen_fixture() -> None:
    root = Path(__file__).parents[1]
    generated = evaluate_rag_fixture(root / "evaluations" / "fixtures" / "rag_retrieval_v1.json")
    recorded = json.loads((root / "evaluations" / "results" / "rag_retrieval_v1.json").read_text())

    assert recorded == generated
