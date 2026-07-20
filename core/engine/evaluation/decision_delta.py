"""Deterministic material-memory decision-delta receipts.

The receipt is an evaluation artifact, not a second task system.  It compares
structured decisions from a matched with-memory/no-memory pair and records the
strongest evidence level reached by each memory item.  Recorded fixtures keep
the evaluator reproducible without making a model judge its own output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "ace.decision-delta-receipt/v1"
SUITE_VERSION = 1

EVIDENCE_LEVELS = (
    "retrieved",
    "injected",
    "reflected",
    "decision-material",
    "outcome-supported",
    "invalidated",
)

DECISION_FIELDS = (
    "selected_option",
    "ranking",
    "constraints",
    "claims",
    "actions",
    "rejected_alternatives",
    "risk_classification",
    "next_action",
    "preserved_boundaries",
)

MATCH_FIELDS = (
    "task_hash",
    "prompt_contract_hash",
    "provider",
    "model",
    "access_class",
    "surface",
    "temperature",
    "configuration_hash",
    "toolset_hash",
    "evaluator_method",
)


class DecisionDeltaContractError(ValueError):
    """Raised when a recorded fixture cannot produce an honest receipt."""


def stable_hash(value: Any) -> str:
    """Return a full SHA-256 over canonical, JSON-safe content."""
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_decision_delta_suite(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        suite = json.load(handle)
    if suite.get("schema_version") != SUITE_VERSION:
        raise DecisionDeltaContractError("unsupported decision-delta suite schema_version")
    if not suite.get("cases"):
        raise DecisionDeltaContractError("decision-delta suite must contain at least one case")
    return suite


def _required(mapping: dict[str, Any], key: str, owner: str) -> Any:
    value = mapping.get(key)
    if value in (None, "", []):
        raise DecisionDeltaContractError(f"{owner}.{key} is required")
    return value


def _delta(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for field in DECISION_FIELDS:
        previous = before.get(field)
        current = after.get(field)
        if previous != current:
            changes.append({"field": field, "before": previous, "after": current})
    return changes


def _matched_control(case: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    treatment = case["with_memory"]["conditions"]
    control = case["without_memory"]["conditions"]
    mismatches = [
        {"field": field, "with_memory": treatment.get(field), "without_memory": control.get(field)}
        for field in MATCH_FIELDS
        if treatment.get(field) != control.get(field)
    ]
    return not mismatches, mismatches


def _validity_state(memory: dict[str, Any]) -> str:
    validity = memory.get("validity") or {}
    if validity.get("invalidated"):
        return "invalidated"
    if validity.get("stale"):
        return "stale"
    if validity.get("contested"):
        return "contested"
    return str(validity.get("state") or "active")


def _contested_handled(decision: dict[str, Any]) -> bool:
    return decision.get("contested_handling") in {"defer", "escalate", "preserve_disagreement"} and not decision.get(
        "presented_as_settled", False
    )


def _memory_evidence(
    memory: dict[str, Any],
    *,
    isolation_ok: bool,
    matched: bool,
    changes: list[dict[str, Any]],
    material_fields: set[str],
    decision: dict[str, Any],
    outcome: dict[str, Any],
) -> dict[str, Any]:
    observed = memory.get("observed") or {}
    validity_state = _validity_state(memory)
    retrieved = bool(observed.get("retrieved"))
    injected = retrieved and bool(observed.get("injected"))
    reflected = injected and bool(observed.get("reflected"))
    relevant = (memory.get("retrieval") or {}).get("relevance") == "relevant"
    changed_fields = {change["field"] for change in changes}
    meaningful_delta = bool(changed_fields & material_fields)
    valid_for_materiality = validity_state not in {"invalidated", "stale"}
    contested_ok = validity_state != "contested" or _contested_handled(decision)
    decision_material = bool(
        isolation_ok
        and matched
        and reflected
        and relevant
        and meaningful_delta
        and valid_for_materiality
        and contested_ok
    )
    outcome_supported = decision_material and outcome.get("status") == "supported"
    invalidated = validity_state in {"invalidated", "stale"}

    if invalidated:
        level = "invalidated"
    elif outcome_supported:
        level = "outcome-supported"
    elif decision_material:
        level = "decision-material"
    elif reflected:
        level = "reflected"
    elif injected:
        level = "injected"
    elif retrieved:
        level = "retrieved"
    else:
        level = None

    return {
        "id": str(_required(memory, "id", "memory")),
        "type": _required(memory, "type", "memory"),
        "content_hash": _required(memory, "content_hash", "memory"),
        "provenance": deepcopy(_required(memory, "provenance", "memory")),
        "captured_at": _required(memory, "captured_at", "memory"),
        "loaded_at": memory.get("loaded_at"),
        "trust": memory.get("trust"),
        "validity": deepcopy(memory.get("validity") or {"state": "active"}),
        "retrieval": deepcopy(_required(memory, "retrieval", "memory")),
        "receiving_stage": deepcopy(memory.get("receiving_stage")),
        "evidence": {
            "retrieved": retrieved,
            "injected": injected,
            "reflected": reflected,
            "decision_material": decision_material,
            "outcome_supported": outcome_supported,
            "invalidated": invalidated,
            "level": level,
            "level_number": EVIDENCE_LEVELS.index(level) + 1 if level else 0,
        },
    }


def build_decision_delta_receipt(case: dict[str, Any], *, suite_id: str) -> dict[str, Any]:
    """Build one bounded receipt from a recorded matched-comparison case."""
    case_id = str(_required(case, "case_id", "case"))
    task = deepcopy(_required(case, "task", "case"))
    _required(task, "id", "task")
    _required(task, "product_id", "task")
    _required(task, "workspace_id", "task")
    _required(task, "shape", "task")
    memories = _required(case, "memories", "case")
    with_memory = _required(case, "with_memory", "case")
    without_memory = _required(case, "without_memory", "case")
    evaluator = deepcopy(_required(case, "evaluator", "case"))
    outcome = deepcopy(case.get("outcome") or {"status": "not_observed"})
    material_fields = set(evaluator.get("materiality_fields") or DECISION_FIELDS)

    treatment_decision = deepcopy(_required(with_memory, "decision", "with_memory"))
    control_decision = deepcopy(_required(without_memory, "decision", "without_memory"))
    changes = _delta(control_decision, treatment_decision)
    matched, mismatches = _matched_control(case)
    isolation_mismatches = [
        str(item.get("id", ""))
        for item in memories
        if (item.get("provenance") or {}).get("product_id")
        and (item.get("provenance") or {}).get("product_id") != task["product_id"]
    ]
    isolation_ok = not isolation_mismatches
    intelligence = [
        _memory_evidence(
            item,
            isolation_ok=isolation_ok,
            matched=matched,
            changes=changes,
            material_fields=material_fields,
            decision=treatment_decision,
            outcome=outcome,
        )
        for item in memories
    ]
    material_ids = [item["id"] for item in intelligence if item["evidence"]["decision_material"]]
    reflected_ids = [item["id"] for item in intelligence if item["evidence"]["reflected"]]
    retrieved_ids = [item["id"] for item in intelligence if item["evidence"]["retrieved"]]
    degraded_reasons = list(case.get("degraded_reasons") or [])
    if not matched:
        degraded_reasons.append("counterfactual_conditions_mismatched")
    if not isolation_ok:
        degraded_reasons.append("product_isolation_mismatch")
    if not memories:
        degraded_reasons.append("no_target_intelligence")

    identity = {
        "contract_version": CONTRACT_VERSION,
        "suite_id": suite_id,
        "case_id": case_id,
        "task": task,
        "memory_ids": [item["id"] for item in intelligence],
        "treatment_output_hash": with_memory.get("output_hash"),
        "control_output_hash": without_memory.get("output_hash"),
        "conditions": with_memory.get("conditions"),
        "evaluator_version": evaluator.get("version"),
    }
    receipt_id = f"decision_delta:{stable_hash(identity)[:24]}"

    causal_claim = bool(material_ids and matched)
    return {
        "contract_version": CONTRACT_VERSION,
        "receipt_id": receipt_id,
        "suite_id": suite_id,
        "case_id": case_id,
        "task": task,
        "decision": {
            "identity": case.get("decision_identity") or f"decision:{case_id}",
            "under_examination": case.get("decision_under_examination"),
            "with_memory": treatment_decision,
            "without_memory": control_decision,
            "delta": changes,
            "material_fields": sorted(material_fields),
            "material_memory_ids": material_ids,
            "retrieved_memory_ids": retrieved_ids,
            "reflected_memory_ids": reflected_ids,
        },
        "intelligence": intelligence,
        "route": deepcopy(_required(case, "route", "case")),
        "capture_route": deepcopy(case.get("capture_route")),
        "counterfactual": {
            "matched": matched,
            "mismatches": mismatches,
            "with_memory_output_hash": _required(with_memory, "output_hash", "with_memory"),
            "without_memory_output_hash": _required(without_memory, "output_hash", "without_memory"),
            "conditions": deepcopy(with_memory.get("conditions")),
        },
        "isolation": {
            "status": "passed" if isolation_ok else "failed",
            "task_product_id": task["product_id"],
            "mismatched_memory_ids": isolation_mismatches,
        },
        "evaluator": evaluator,
        "outcome": outcome,
        "metrics": deepcopy(_required(case, "metrics", "case")),
        "persistence": deepcopy(case.get("persistence") or {}),
        "causal_assessment": {
            "memory_effect_supported": causal_claim,
            "cross_model_difference_used_as_causal_evidence": False,
            "limitations": list(case.get("causal_limitations") or []),
        },
        "completeness": {
            "status": "degraded" if degraded_reasons else "complete",
            "degraded_reasons": sorted(set(degraded_reasons)),
        },
        "replay": {
            "identity_hash": stable_hash(identity),
            "task_hash": with_memory["conditions"].get("task_hash"),
            "prompt_contract_hash": with_memory["conditions"].get("prompt_contract_hash"),
            "configuration_hash": with_memory["conditions"].get("configuration_hash"),
        },
    }


def evaluate_decision_delta_suite(suite: dict[str, Any]) -> dict[str, Any]:
    """Build all receipts while preserving null, negative, and degraded cases."""
    if suite.get("schema_version") != SUITE_VERSION:
        raise DecisionDeltaContractError("unsupported decision-delta suite schema_version")
    suite_id = str(_required(suite, "suite_id", "suite"))
    receipts = [build_decision_delta_receipt(case, suite_id=suite_id) for case in suite["cases"]]
    levels: dict[str, int] = {level: 0 for level in EVIDENCE_LEVELS}
    for receipt in receipts:
        for item in receipt["intelligence"]:
            level = item["evidence"]["level"]
            if level:
                levels[level] += 1

    routes = {
        (
            receipt["route"].get("provider"),
            receipt["route"].get("model"),
            receipt["route"].get("access_class"),
            receipt["route"].get("surface"),
        )
        for receipt in receipts
    }
    return {
        "schema_version": SUITE_VERSION,
        "contract_version": CONTRACT_VERSION,
        "suite_id": suite_id,
        "run_kind": suite.get("run_kind", "recorded_fixture"),
        "evidence_scope": deepcopy(suite.get("evidence_scope") or {}),
        "summary": {
            "tasks": len(receipts),
            "task_shapes": sorted({receipt["task"]["shape"] for receipt in receipts}),
            "complete_receipts": sum(receipt["completeness"]["status"] == "complete" for receipt in receipts),
            "degraded_receipts": sum(receipt["completeness"]["status"] == "degraded" for receipt in receipts),
            "material_receipts": sum(bool(receipt["decision"]["material_memory_ids"]) for receipt in receipts),
            "null_receipts": sum(not receipt["decision"]["delta"] for receipt in receipts),
            "evidence_levels": levels,
            "distinct_routes": len(routes),
            "surfaces": sorted({str(route[3]) for route in routes}),
            "access_classes": sorted({str(route[2]) for route in routes}),
        },
        "receipts": receipts,
        "unsupported_claims": list(suite.get("unsupported_claims") or []),
        "missing_live_evidence": list(suite.get("missing_live_evidence") or []),
    }


def render_decision_delta_markdown(result: dict[str, Any]) -> str:
    summary = result["summary"]
    lines = [
        f"# Decision-delta evaluation: {result['suite_id']}",
        "",
        f"Contract: `{result['contract_version']}`",
        "",
        (
            f"Recorded {summary['tasks']} tasks across {len(summary['task_shapes'])} task shapes. "
            f"Material: {summary['material_receipts']}; null: {summary['null_receipts']}; "
            f"degraded: {summary['degraded_receipts']}."
        ),
        "",
        "> Recorded-response conformance proves receipt behavior and portability of the contract. "
        "It is not live cross-model quality evidence and does not establish ACE superiority.",
        "",
        "| Case | Shape | Evidence | Exact changed fields | Control | Route | Surface | Status |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for receipt in result["receipts"]:
        levels = sorted({item["evidence"]["level"] or "none" for item in receipt["intelligence"]})
        fields = [change["field"] for change in receipt["decision"]["delta"]]
        route = receipt["route"]
        lines.append(
            f"| {receipt['case_id']} | {receipt['task']['shape']} | {', '.join(levels)} | "
            f"{', '.join(fields) or 'none'} | {'matched' if receipt['counterfactual']['matched'] else 'mismatched'} | "
            f"{route.get('provider')} / {route.get('model')} / {route.get('access_class')} | "
            f"{route.get('surface')} | {receipt['completeness']['status']} |"
        )

    lines += ["", "## Unsupported claims", ""]
    lines += [f"- {claim}" for claim in result["unsupported_claims"]] or ["- None recorded."]
    lines += ["", "## Missing live evidence", ""]
    lines += [f"- {item}" for item in result["missing_live_evidence"]] or ["- None recorded."]
    lines += ["", "## Receipt details", ""]
    for receipt in result["receipts"]:
        decision = receipt["decision"]
        lines += [
            f"### {receipt['case_id']}",
            "",
            f"Receipt: `{receipt['receipt_id']}`",
            "",
            f"Decision: {receipt.get('decision_under_examination') or decision.get('under_examination') or 'recorded in artifact'}",
            "",
            f"Material intelligence: {', '.join(decision['material_memory_ids']) or 'none'}.",
            "",
        ]
        for change in decision["delta"]:
            lines.append(
                f"- `{change['field']}`: `{json.dumps(change['before'], sort_keys=True)}` → "
                f"`{json.dumps(change['after'], sort_keys=True)}`"
            )
        if not decision["delta"]:
            lines.append("- Null result: the structured decision did not change.")
        if receipt["completeness"]["degraded_reasons"]:
            lines.append("- Degraded: " + ", ".join(receipt["completeness"]["degraded_reasons"]) + ".")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build deterministic ACE decision-delta receipts")
    parser.add_argument("suite", type=Path)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--markdown-out", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate_decision_delta_suite(load_decision_delta_suite(args.suite))
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.write_text(render_decision_delta_markdown(result) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
