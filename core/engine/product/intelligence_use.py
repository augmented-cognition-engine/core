"""Bounded I3 receipts for retained-intelligence continuity and decision effect.

The receipt is a read projection over existing task, decision, and intelligence
identities.  It never reconstructs a missing control from prose and never treats
retrieval, attribution, or a decision delta as evidence of beneficial impact.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any

CONTRACT_VERSION = "intelligence-use-receipt-v1"
DECISION_SCHEMA_VERSION = "decision-receipt-v1"

# These are the structured I1 decision fields.  Free-form rationale and model
# output are deliberately outside the comparison contract.
DECISION_FIELDS = (
    "selected_option",
    "scope",
    "assumptions",
    "alternatives",
    "reconsideration_conditions",
    "evidence_refs",
)

MATCH_DIMENSIONS = (
    "task_hash",
    "prompt_contract_hash",
    "provider",
    "model",
    "configuration_hash",
    "decision_schema",
    "toolset_hash",
)

MAX_INTELLIGENCE_ITEMS = 64
MAX_LIST_ITEMS = 64
_CREDENTIAL = re.compile(r"(?i)\b(bearer|api[_-]?key|token|password|secret)\b\s*[:=]?\s*[^\s,;]+")
_MATERIAL_REFLECTION_METHODS = frozenset(
    {"bounded_attribution", "structured_field_attribution", "declared_field_attribution"}
)
_REFLECTION_METHODS = _MATERIAL_REFLECTION_METHODS | frozenset(
    {"structural_attribution", "model_attribution", "identifier_mention", "verbatim_overlap"}
)


class IntelligenceUseContractError(ValueError):
    """Raised when an I3 input cannot be represented honestly."""


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _text(value: object, limit: int = 1_000) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).split())
    normalized = _CREDENTIAL.sub(r"\1=<redacted>", normalized)
    return normalized[:limit] if normalized else None


def _bounded(value: Any, *, depth: int = 0) -> Any:
    """Return JSON-safe, credential-redacted, size-bounded public data."""
    if depth >= 6:
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _text(value, 2_000)
    if isinstance(value, dict):
        return {str(key)[:120]: _bounded(item, depth=depth + 1) for key, item in list(value.items())[:MAX_LIST_ITEMS]}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_bounded(item, depth=depth + 1) for item in list(value)[:MAX_LIST_ITEMS]]
    return _text(value, 2_000)


def exact_decision_delta(with_context: dict, without_context: dict) -> dict:
    """Compare only the declared structured I1 decision fields."""
    changed: list[dict[str, Any]] = []
    unchanged: list[str] = []
    for field in DECISION_FIELDS:
        treatment = deepcopy(with_context.get(field))
        control = deepcopy(without_context.get(field))
        if treatment == control:
            unchanged.append(field)
        else:
            changed.append(
                {
                    "field": field,
                    "without_context": _bounded(control),
                    "with_context": _bounded(treatment),
                }
            )
    return {"changed_fields": changed, "unchanged_fields": unchanged}


def _comparison(value: object) -> dict:
    raw = value if isinstance(value, dict) else {}
    treatment = raw.get("with_context") if isinstance(raw.get("with_context"), dict) else {}
    control = raw.get("without_context") if isinstance(raw.get("without_context"), dict) else {}
    treatment_decision = treatment.get("decision") if isinstance(treatment.get("decision"), dict) else {}
    control_decision = control.get("decision") if isinstance(control.get("decision"), dict) else {}
    treatment_conditions = treatment.get("conditions") if isinstance(treatment.get("conditions"), dict) else {}
    control_conditions = control.get("conditions") if isinstance(control.get("conditions"), dict) else {}
    failures = list(raw.get("failures") or [])[:MAX_LIST_ITEMS]

    missing: list[str] = []
    if not treatment_decision:
        missing.append("with_context.decision")
    if not control_decision:
        missing.append("without_context.decision")
    for variant_name, conditions in (
        ("with_context", treatment_conditions),
        ("without_context", control_conditions),
    ):
        for field in MATCH_DIMENSIONS:
            if conditions.get(field) in (None, ""):
                missing.append(f"{variant_name}.conditions.{field}")

    mismatches = [
        {
            "field": field,
            "with_context": _bounded(treatment_conditions.get(field)),
            "without_context": _bounded(control_conditions.get(field)),
        }
        for field in MATCH_DIMENSIONS
        if treatment_conditions.get(field) != control_conditions.get(field)
        and f"with_context.conditions.{field}" not in missing
        and f"without_context.conditions.{field}" not in missing
    ]
    if failures:
        state = "failed"
    elif missing:
        state = "unknown"
    elif mismatches:
        state = "mismatched"
    else:
        state = "matched"

    delta = (
        exact_decision_delta(treatment_decision, control_decision)
        if treatment_decision and control_decision
        else {
            "changed_fields": [],
            "unchanged_fields": [],
        }
    )
    comparison_identity = {
        "with_context_invocation_id": treatment.get("invocation_id"),
        "without_context_invocation_id": control.get("invocation_id"),
        "target_intelligence_ids": list(raw.get("target_intelligence_ids") or []),
        "conditions": treatment_conditions if state == "matched" else None,
        "with_context_decision": treatment_decision,
        "without_context_decision": control_decision,
    }
    return {
        "comparison_id": _text(raw.get("comparison_id"), 200)
        or f"intelligence_comparison:{_stable_hash(comparison_identity)[:24]}",
        "state": state,
        "target_intelligence_ids": [
            item
            for value in list(raw.get("target_intelligence_ids") or [])[:MAX_INTELLIGENCE_ITEMS]
            if (item := _text(value, 200))
        ],
        "matching": {
            "dimensions": list(MATCH_DIMENSIONS),
            "mismatches": mismatches,
            "missing_fields": sorted(set(missing)),
        },
        "with_context": {
            "invocation_id": _text(treatment.get("invocation_id"), 200),
            "decision": {field: _bounded(treatment_decision.get(field)) for field in DECISION_FIELDS},
            "conditions": _bounded(treatment_conditions),
            "metrics": _bounded(treatment.get("metrics") or {}),
            "output_hash": _text(treatment.get("output_hash"), 200),
        },
        "without_context": {
            "invocation_id": _text(control.get("invocation_id"), 200),
            "decision": {field: _bounded(control_decision.get(field)) for field in DECISION_FIELDS},
            "conditions": _bounded(control_conditions),
            "metrics": _bounded(control.get("metrics") or {}),
            "output_hash": _text(control.get("output_hash"), 200),
        },
        "delta": delta,
        "failures": [_text(item, 400) for item in failures],
        "limitations": [_text(item, 500) for item in list(raw.get("limitations") or [])[:MAX_LIST_ITEMS]],
    }


def _valid_for_use(item: dict, *, receiving_product: str | None) -> tuple[bool, list[str]]:
    validity = item.get("validity") if isinstance(item.get("validity"), dict) else {}
    lifecycle = item.get("lifecycle") if isinstance(item.get("lifecycle"), dict) else {}
    contestation = item.get("contestation") if isinstance(item.get("contestation"), dict) else {}
    state = str(validity.get("state") or "unknown")
    lifecycle_state = str(lifecycle.get("state") or "active")
    source_product = _text(item.get("source_product_id") or (item.get("provenance") or {}).get("product_id"), 200)
    reasons: list[str] = []
    if state in {"stale", "invalidated", "expired", "unusable", "unknown"}:
        reasons.append(f"validity_{state}")
    if lifecycle_state not in {"active", "contested"}:
        reasons.append(f"lifecycle_{lifecycle_state}")
    if source_product and receiving_product and source_product != receiving_product:
        reasons.append("product_mismatch")
    if state == "contested" or contestation.get("state") == "contested":
        handling = contestation.get("handling")
        if handling not in {"defer", "escalate", "preserve_disagreement"}:
            reasons.append("contestation_not_safely_handled")
    return not reasons, reasons


def _intelligence_item(
    item: dict,
    *,
    receiving: dict,
    comparison: dict,
    material_fields: set[str],
) -> tuple[dict, list[str]]:
    intelligence_id = _text(item.get("intelligence_id") or item.get("id"), 200)
    if not intelligence_id:
        raise IntelligenceUseContractError("intelligence item requires a stable intelligence_id")
    observed = item.get("observed") if isinstance(item.get("observed"), dict) else {}
    reflection = item.get("reflection") if isinstance(item.get("reflection"), dict) else {}
    reflection_method = str(reflection.get("method") or "unreported")
    retrieved = bool(observed.get("retrieved"))
    injected = retrieved and bool(observed.get("injected"))
    reflection_observed = injected and bool(observed.get("reflected"))
    reflected = reflection_observed and reflection_method in _REFLECTION_METHODS
    reflection_materiality_eligible = reflected and reflection_method in _MATERIAL_REFLECTION_METHODS
    relevance = item.get("relevance")
    if relevance is None and isinstance(item.get("retrieval"), dict):
        relevance = item["retrieval"].get("relevance")
    relevant = relevance in {True, "relevant", "high"}
    valid_for_use, validity_reasons = _valid_for_use(item, receiving_product=receiving.get("product_id"))
    changed_fields = [entry["field"] for entry in comparison["delta"]["changed_fields"]]
    meaningful_fields = sorted(set(changed_fields) & material_fields)
    targeted = comparison["target_intelligence_ids"] == [intelligence_id]

    material_reasons: list[str] = []
    if not valid_for_use:
        material_reasons.extend(validity_reasons)
    if not injected:
        material_reasons.append("not_injected")
    if not reflected:
        material_reasons.append("not_reflected")
    elif not reflection_materiality_eligible:
        material_reasons.append("reflection_method_not_materiality_eligible")
    if not relevant:
        material_reasons.append("not_relevant")
    if comparison["state"] != "matched":
        material_reasons.append(f"comparison_{comparison['state']}")
    if not targeted:
        material_reasons.append("comparison_not_isolated_to_intelligence_item")
    if not meaningful_fields:
        material_reasons.append("no_qualifying_structured_decision_delta")
    if any(
        value in (None, "", {})
        for value in (
            item.get("content_hash"),
            item.get("trust"),
            item.get("provenance"),
            item.get("source_product_id") or (item.get("provenance") or {}).get("product_id"),
            receiving.get("task_id"),
            receiving.get("decision_id"),
            receiving.get("component"),
            receiving.get("stage"),
            receiving.get("invocation_id"),
        )
    ):
        material_reasons.append("partial_or_missing_lineage")
    decision_material = not material_reasons

    reasons = {
        "injected": [] if injected else (["not_retrieved"] if not retrieved else ["not_injected"]),
        "reflected": [] if reflected else (["not_injected"] if not injected else [f"reflection_{reflection_method}"]),
        "decision_material": sorted(set(material_reasons)),
    }
    evidence = {
        "retrieved": retrieved,
        "injected": injected,
        "reflected": reflected,
        "decision_material": decision_material,
        "highest_state": (
            "decision-material"
            if decision_material
            else "reflected"
            if reflected
            else "injected"
            if injected
            else "retrieved"
            if retrieved
            else "not-established"
        ),
        "changed_fields": meaningful_fields if decision_material else [],
        "not_established_reasons": reasons,
    }
    result = {
        "intelligence_id": intelligence_id,
        "intelligence_type": _text(item.get("intelligence_type") or item.get("type"), 120),
        "source_product_id": _text(
            item.get("source_product_id") or (item.get("provenance") or {}).get("product_id"), 200
        ),
        "receiving_product_id": receiving.get("product_id"),
        "content_hash": _text(item.get("content_hash"), 200),
        "retrieval": _bounded(item.get("retrieval") or {}),
        "validity": _bounded(item.get("validity") or {"state": "unknown"}),
        "relevance": _bounded(relevance),
        "trust": _bounded(item.get("trust")),
        "provenance": _bounded(item.get("provenance") or {}),
        "lifecycle": _bounded(item.get("lifecycle") or {"state": "active"}),
        "contestation": _bounded(item.get("contestation") or {}),
        "receiving": {
            "task_id": receiving.get("task_id"),
            "decision_id": receiving.get("decision_id"),
            "component": _text(item.get("receiving_component") or receiving.get("component"), 160),
            "stage": _text(item.get("receiving_stage") or receiving.get("stage"), 160),
            "invocation_id": _text(item.get("receiving_invocation_id") or receiving.get("invocation_id"), 200),
        },
        "reflection": {
            "method": reflection_method,
            "evidence_refs": _bounded(reflection.get("evidence_refs") or []),
            "materiality_eligible": reflection_materiality_eligible,
        },
        "evidence": evidence,
    }
    completeness_gaps = [
        name
        for name, value in (
            ("intelligence_type", result["intelligence_type"]),
            ("source_product_id", result["source_product_id"]),
            ("content_hash", result["content_hash"]),
            ("retrieval", result["retrieval"]),
            ("trust", result["trust"]),
            ("provenance", result["provenance"]),
            ("receiving.task_id", result["receiving"]["task_id"]),
            ("receiving.decision_id", result["receiving"]["decision_id"]),
            ("receiving.component", result["receiving"]["component"]),
            ("receiving.stage", result["receiving"]["stage"]),
            ("receiving.invocation_id", result["receiving"]["invocation_id"]),
        )
        if value in (None, "")
    ]
    if (result["validity"] or {}).get("state") in (None, "unknown"):
        completeness_gaps.append("validity.state")
    if not result["retrieval"]:
        completeness_gaps.append("retrieval")
    if not result["provenance"]:
        completeness_gaps.append("provenance")
    if result["relevance"] in (None, "unknown"):
        completeness_gaps.append("relevance")
    if (result["lifecycle"] or {}).get("state") in (None, "unknown"):
        completeness_gaps.append("lifecycle.state")
    return result, completeness_gaps


def build_intelligence_use_receipt(case: dict) -> dict:
    """Build one deterministic I3 receipt from recorded or runtime facts."""
    receiving_raw = case.get("receiving") if isinstance(case.get("receiving"), dict) else {}
    receiving = {
        "product_id": _text(receiving_raw.get("product_id"), 200),
        "task_id": _text(receiving_raw.get("task_id"), 200),
        "decision_id": _text(receiving_raw.get("decision_id"), 200),
        "component": _text(receiving_raw.get("component"), 160),
        "stage": _text(receiving_raw.get("stage"), 160),
        "invocation_id": _text(receiving_raw.get("invocation_id"), 200),
    }
    if not receiving["product_id"] or not receiving["task_id"]:
        raise IntelligenceUseContractError("receiving.product_id and receiving.task_id are required")
    comparison = _comparison(case.get("comparison"))
    declared_material_fields = set(case.get("material_fields") or DECISION_FIELDS)
    if not declared_material_fields <= set(DECISION_FIELDS):
        raise IntelligenceUseContractError("material_fields must be structured I1 decision fields")

    raw_items = case.get("intelligence")
    if not isinstance(raw_items, list):
        raise IntelligenceUseContractError("intelligence must be a list")
    truncated = len(raw_items) > MAX_INTELLIGENCE_ITEMS
    items: list[dict] = []
    gaps: list[str] = []
    for index, raw in enumerate(raw_items[:MAX_INTELLIGENCE_ITEMS]):
        if not isinstance(raw, dict):
            gaps.append(f"intelligence[{index}]")
            continue
        projected, item_gaps = _intelligence_item(
            raw,
            receiving=receiving,
            comparison=comparison,
            material_fields=declared_material_fields,
        )
        items.append(projected)
        gaps.extend(f"{projected['intelligence_id']}.{gap}" for gap in item_gaps)
    if truncated:
        gaps.append("intelligence_items_truncated")
    if comparison["state"] != "matched":
        gaps.append(f"comparison_{comparison['state']}")

    material_ids = [item["intelligence_id"] for item in items if item["evidence"]["decision_material"]]
    outcome = case.get("outcome") if isinstance(case.get("outcome"), dict) else {}
    outcome_status = str(outcome.get("status") or "not_observed")
    harmful = outcome_status in {"harmful", "contradicted", "negative"}
    impact_state = "harmful" if material_ids and harmful else "outcome_unsupported"
    identity = {
        "contract_version": CONTRACT_VERSION,
        "receiving": receiving,
        "intelligence_ids": [item["intelligence_id"] for item in items],
        "comparison_id": comparison["comparison_id"],
        "comparison_state": comparison["state"],
    }
    return {
        "contract_version": CONTRACT_VERSION,
        "receipt_id": _text(case.get("receipt_id"), 200) or f"intelligence_use:{_stable_hash(identity)[:24]}",
        "receiving": receiving,
        "material_fields": sorted(declared_material_fields),
        "intelligence": items,
        "comparison": comparison,
        "material_intelligence_ids": material_ids,
        "impact": {
            "material_influence_established": bool(material_ids),
            "beneficial_impact": impact_state,
            "beneficial_impact_supported": False,
            "outcome": _bounded(outcome),
            "boundary": "Material influence is not beneficial impact; benefit requires later L1 outcome evidence.",
        },
        "route": _bounded(case.get("route") or {}),
        "continuity": _bounded(case.get("continuity") or {}),
        "completeness": {
            "state": "complete" if not gaps else "degraded",
            "missing_or_degraded": sorted(set(gaps)),
        },
        "authority": {"mode": "read_only_projection", "execution_authority": False},
    }


def normalize_intelligence_use_receipt(receipt: object, *, task: dict) -> dict:
    """Normalize a stored receipt without interpreting unknown future versions."""
    if not isinstance(receipt, dict):
        return build_intelligence_use_receipt(
            {
                "receiving": {
                    "product_id": task.get("product"),
                    "task_id": task.get("id"),
                    "decision_id": (task.get("decision_receipt") or {}).get("decision_id"),
                    "component": "orchestration",
                    "stage": "result",
                    "invocation_id": task.get("id"),
                },
                "intelligence": [],
                "comparison": {},
            }
        )
    version = receipt.get("contract_version")
    if version != CONTRACT_VERSION:
        degraded = normalize_intelligence_use_receipt(None, task=task)
        degraded["completeness"] = {
            "state": "degraded",
            "missing_or_degraded": [f"unsupported_intelligence_use_receipt_version:{_text(version, 120) or 'missing'}"],
        }
        return degraded
    # Stored v1 rows are already projections, not builder inputs.  Preserve the
    # evidence booleans while reapplying public bounds/redaction and stable
    # defaults; never attempt to infer missing facts from the task or output.
    bounded = _bounded(receipt)
    assert isinstance(bounded, dict)
    bounded["contract_version"] = CONTRACT_VERSION
    bounded.setdefault("receipt_id", None)
    bounded.setdefault("receiving", {})
    bounded.setdefault("material_fields", list(DECISION_FIELDS))
    bounded["intelligence"] = list(bounded.get("intelligence") or [])[:MAX_INTELLIGENCE_ITEMS]
    bounded.setdefault("comparison", {"state": "unknown"})
    bounded.setdefault("material_intelligence_ids", [])
    bounded.setdefault(
        "impact",
        {
            "material_influence_established": False,
            "beneficial_impact": "outcome_unsupported",
            "beneficial_impact_supported": False,
            "boundary": "Material influence is not beneficial impact; benefit requires later L1 outcome evidence.",
        },
    )
    bounded.setdefault("completeness", {"state": "degraded", "missing_or_degraded": ["missing_completeness"]})
    bounded.setdefault("authority", {"mode": "read_only_projection", "execution_authority": False})
    return bounded


def runtime_intelligence_use_receipt(
    *,
    task_id: str,
    product_id: str,
    decision_receipt: dict,
    trace: dict | None,
    route: dict | None = None,
) -> dict:
    """Project observed runtime loading/attribution with an explicit missing control."""
    trace = trace if isinstance(trace, dict) else {}
    items = []
    reflected_ids = set(trace.get("reflected_ids") or [])
    reflection_method = str(trace.get("reflection_method") or "unreported")
    for rank, raw in enumerate(list(trace.get("items") or [])[:MAX_INTELLIGENCE_ITEMS], start=1):
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        intelligence_id = str(raw["id"])
        retrieved = bool(raw.get("retrieved", True))
        injected = retrieved and bool(raw.get("injected", True))
        items.append(
            {
                "intelligence_id": intelligence_id,
                "intelligence_type": raw.get("intelligence_type"),
                "source_product_id": raw.get("source_product_id") or product_id,
                "content_hash": raw.get("content_hash"),
                "retrieval": {
                    "rank": rank,
                    "query": raw.get("retrieval_query"),
                    "reason": raw.get("retrieval_reason") or "runtime_context_selection",
                    "score": raw.get("retrieval_score"),
                    "relevance": raw.get("relevance", "unknown"),
                },
                "validity": raw.get("validity") or {"state": "active"},
                "relevance": raw.get("relevance", "unknown"),
                "trust": raw.get("trust"),
                "provenance": raw.get("provenance") or {"source": raw.get("source_graph")},
                "lifecycle": raw.get("lifecycle") or {"state": "active"},
                "contestation": raw.get("contestation") or {},
                "observed": {
                    "retrieved": retrieved,
                    "injected": injected,
                    "reflected": injected and intelligence_id in reflected_ids,
                },
                "reflection": {
                    "method": reflection_method if intelligence_id in reflected_ids else "unreported",
                    "evidence_refs": [f"task:{task_id}:bounded_output_attribution"]
                    if intelligence_id in reflected_ids
                    else [],
                },
            }
        )
    recorded_comparison = trace.get("comparison") if isinstance(trace.get("comparison"), dict) else None
    comparison = recorded_comparison or {
        "target_intelligence_ids": [],
        "with_context": {
            "invocation_id": task_id,
            "decision": {field: decision_receipt.get(field) for field in DECISION_FIELDS},
            "conditions": {},
        },
    }
    return build_intelligence_use_receipt(
        {
            "receiving": {
                "product_id": product_id,
                "task_id": task_id,
                "decision_id": decision_receipt.get("decision_id"),
                "component": trace.get("component") or "orchestration.executor",
                "stage": trace.get("stage") or "reasoning_context",
                "invocation_id": trace.get("invocation_id") or task_id,
            },
            "intelligence": items,
            "comparison": comparison,
            "route": route or {},
            "continuity": trace.get("continuity") or {},
        }
    )
