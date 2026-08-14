"""Frozen, provider-free relevance evaluation for the v1 RAG rank policy."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from core.engine.search.intelligence import reciprocal_rank_fusion


def _hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def evaluate_rag_fixture(path: str | Path) -> dict[str, Any]:
    fixture = json.loads(Path(path).read_text())
    if fixture.get("contract_version") != "ace.rag-evaluation-config/v1":
        raise ValueError("unsupported RAG evaluation contract")

    top_k = int(fixture["top_k"])
    cases: list[dict[str, Any]] = []
    expected_total = 0
    expected_found = 0
    reciprocal_ranks: list[float] = []
    false_associations = 0

    for case in fixture["cases"]:
        lexical = [{"id": record_id} for record_id in case["lexical_ranking"]]
        vector = [
            {"id": item["id"], "vector_distance": item["distance"]}
            for item in case["vector_ranking"]
            if item["distance"] <= fixture["maximum_vector_distance"]
        ]
        ranked = reciprocal_rank_fusion(lexical, vector, limit=top_k)
        selected = [row["id"] for row in ranked]
        expected = list(case["expected_ids"])
        forbidden = set(case.get("forbidden_ids", []))
        found = [record_id for record_id in expected if record_id in selected]
        false = [record_id for record_id in selected if record_id in forbidden]
        expected_total += len(expected)
        expected_found += len(found)
        false_associations += len(false)
        ranks = [selected.index(record_id) + 1 for record_id in expected if record_id in selected]
        if expected:
            reciprocal_ranks.append(1 / min(ranks) if ranks else 0.0)
        cases.append(
            {
                "case_id": case["case_id"],
                "selected_ids": selected,
                "expected_found": found,
                "false_associations": false,
            }
        )

    recall = expected_found / expected_total if expected_total else 1.0
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 1.0
    passed = (
        recall >= fixture["thresholds"]["minimum_recall_at_k"]
        and mrr >= fixture["thresholds"]["minimum_mrr"]
        and false_associations <= fixture["thresholds"]["maximum_false_associations"]
    )
    result = {
        "contract_version": "ace.rag-evaluation-result/v1",
        "fixture_hash": _hash(fixture),
        "ranking_policy_version": fixture["ranking_policy_version"],
        "top_k": top_k,
        "cases_evaluated": len(cases),
        "expected_total": expected_total,
        "expected_found": expected_found,
        "recall_at_k": round(recall, 6),
        "mrr": round(mrr, 6),
        "false_associations": false_associations,
        "passed": passed,
        "cases": cases,
    }
    return {**result, "result_hash": _hash(result)}
