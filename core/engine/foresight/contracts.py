"""Versioned, bounded projections for foresight forecasts, interventions, and resolutions.

The canonical records remain ``decision_prediction``, intervention-shaped ``observation`` rows,
and ``prediction_outcome``. This module normalizes their inspectable contract projections without
reconstructing missing facts from prose. Legacy and unknown-version rows remain readable, but their
compatibility and completeness gaps are explicit.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any

FORECAST_CONTRACT_VERSION = "ace.foresight.forecast/v1"
INTERVENTION_OBSERVATION_CONTRACT_VERSION = "ace.foresight.intervention-observation/v1"
INDICATOR_OBSERVATION_CONTRACT_VERSION = "ace.foresight.indicator-observation/v1"
INDICATOR_STATE_VERSION = "ace.foresight.indicator-state/v1"
COMPARATOR_OBSERVATION_CONTRACT_VERSION = "ace.foresight.comparator-observation/v1"
COMPARATOR_STATE_VERSION = "ace.foresight.comparator-state/v1"
COMPARATOR_PLAN_VERSION = "ace.foresight.comparator-plan/v1"
MEASUREMENT_OBSERVATION_CONTRACT_VERSION = "ace.foresight.measurement-observation/v1"
MEASUREMENT_INGESTION_VERSION = "ace.foresight.measurement-ingestion/v1"
OUTSIDE_VIEW_BASELINE_VERSION = "ace.foresight.outside-view-baseline/v1"
PREDICTION_SCORE_VERSION = "ace.foresight.prediction-score/v1"
RESOLUTION_CONTRACT_VERSION = "ace.foresight.resolution/v1"

INTERVENTION_STATUSES = frozenset({"proposed", "authorized", "started", "partial", "completed", "cancelled", "unknown"})
RESOLUTION_STATES = frozenset({"open", "confirmed", "contradicted", "mixed", "unresolved", "invalid"})
SCORABLE_INTERVENTION_STATUSES = frozenset({"started", "partial", "completed"})
INDICATOR_EFFECTS = frozenset({"supports", "weakens", "falsifies", "inconclusive"})
INDICATOR_OPERATORS = frozenset({"gte", "lte", "delta_gte", "delta_lte"})
COMPARATOR_TYPES = frozenset({"no_action", "holdout", "phased_rollout", "alternative_intervention"})
COMPARATOR_DESIGNS = frozenset({"randomized", "matched", "quasi_experimental", "observational", "unknown"})
COMPARATOR_PLAN_FEASIBILITY = frozenset({"conditional", "not_feasible", "unknown"})

_CREDENTIAL_RE = re.compile(r"(?i)\b(bearer|api[_-]?key|token|password|secret)\b\s*[:=]?\s*[^\s,;]+")


def _bounded_text(value: object, limit: int = 2_000) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    text = _CREDENTIAL_RE.sub(r"\1=<redacted>", text)
    return text[:limit] if text else None


def _bounded_list(value: object, *, limit: int = 25, item_limit: int = 1_000) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for raw in value[:limit] if (item := _bounded_text(raw, item_limit)) is not None]


def _bounded_float(value: object, *, low: float | None = None, high: float | None = None) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if low is not None:
        number = max(low, number)
    if high is not None:
        number = min(high, number)
    return number


def _bounded_json(value: object, *, depth: int = 0) -> Any:
    """Bound and redact stored contract data before returning it through a read projection."""
    if depth > 8:
        return None
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return _bounded_text(value, 4_000)
    if isinstance(value, dict):
        bounded: dict[str, Any] = {}
        for raw_key, raw_value in list(value.items())[:100]:
            key = _bounded_text(raw_key, 160)
            if key is not None:
                bounded[key] = _bounded_json(raw_value, depth=depth + 1)
        return bounded
    if isinstance(value, (list, tuple)):
        return [_bounded_json(item, depth=depth + 1) for item in value[:100]]
    return _bounded_text(value, 4_000)


def _compatibility(state: str, reason: str | None, stored_version: object) -> dict[str, Any]:
    return {
        "state": state,
        "reason": reason,
        "stored_contract_version": _bounded_text(stored_version, 120),
    }


def _condition_observation(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    condition = _bounded_text(value.get("condition"), 1_000)
    if condition is None:
        return None
    met = value.get("met")
    if not isinstance(met, bool):
        met = None
    return {
        "condition": condition,
        "met": met,
        "evidence_refs": _bounded_list(value.get("evidence_refs"), limit=25),
    }


def _indicator_catalog(raw: dict) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    descriptions = _bounded_list(raw.get("leading_indicators"), limit=25, item_limit=1_000)
    raw_rules = raw.get("indicator_rules") if isinstance(raw.get("indicator_rules"), list) else []
    rules_by_index: dict[int, dict[str, Any]] = {}
    for raw_rule in raw_rules[:25]:
        if not isinstance(raw_rule, dict):
            continue
        try:
            indicator_index = int(raw_rule.get("indicator_index")) - 1
        except (TypeError, ValueError):
            continue
        operator = _bounded_text(raw_rule.get("operator"), 40)
        effect_when_met = _bounded_text(raw_rule.get("effect_when_met"), 40)
        capability_id = _bounded_text(raw_rule.get("capability_id"), 240)
        threshold = _bounded_float(raw_rule.get("threshold"), low=-1.0, high=1.0)
        if (
            indicator_index < 0
            or indicator_index >= len(descriptions)
            or operator not in INDICATOR_OPERATORS
            or effect_when_met not in INDICATOR_EFFECTS - {"inconclusive"}
            or capability_id is None
            or threshold is None
        ):
            continue
        effect_when_not_met = _bounded_text(raw_rule.get("effect_when_not_met"), 40)
        if effect_when_not_met not in INDICATOR_EFFECTS:
            effect_when_not_met = "inconclusive"
        if operator in {"gte", "lte"}:
            threshold = max(0.0, min(1.0, threshold))
        rules_by_index[indicator_index] = {
            "metric": "capability_quality",
            "capability_id": capability_id,
            "dimension": _bounded_text(raw_rule.get("dimension"), 160),
            "operator": operator,
            "threshold": threshold,
            "effect_when_met": effect_when_met,
            "effect_when_not_met": effect_when_not_met,
        }

    indicators = []
    for index, description in enumerate(descriptions):
        rule = rules_by_index.get(index)
        indicators.append(
            {
                "local_id": f"indicator:{index + 1}",
                "description": description,
                "monitoring": "automatic" if rule else "manual",
                "rule": rule,
            }
        )
    automatic = sum(item["monitoring"] == "automatic" for item in indicators)
    if not indicators:
        state = "absent"
    elif automatic == len(indicators):
        state = "automatic"
    elif automatic:
        state = "mixed"
    else:
        state = "manual"
    monitoring = {
        "state": state,
        "automatic_count": automatic,
        "manual_count": len(indicators) - automatic,
    }
    return indicators, monitoring


def build_indicator_observation_contract(
    *,
    observation_id: str,
    request_id: str,
    decision_id: str,
    prediction_id: str,
    product_id: str,
    indicator_id: str,
    indicator_description: str,
    effect: str,
    observed_at: object,
    value: object,
    unit: str | None,
    baseline_value: object = None,
    rule: dict | None = None,
    evidence_refs: list[str] | None = None,
    reason: str | None = None,
    source_kind: str = "manual_observation",
    source_surface: str = "api",
    actor_ref: str = "ace",
) -> dict[str, Any]:
    """Build one immutable indicator-evidence record."""
    if effect not in INDICATOR_EFFECTS:
        raise ValueError(f"unsupported indicator effect: {effect}")
    rule = rule if isinstance(rule, dict) else None
    observed_value = _bounded_float(value)
    baseline = _bounded_float(baseline_value)
    contract: dict[str, Any] = {
        "contract_version": INDICATOR_OBSERVATION_CONTRACT_VERSION,
        "observation_id": _bounded_text(observation_id, 240),
        "request_id": _bounded_text(request_id, 240),
        "decision_id": _bounded_text(decision_id, 240),
        "prediction_id": _bounded_text(prediction_id, 240),
        "product_id": _bounded_text(product_id, 240),
        "indicator_id": _bounded_text(indicator_id, 120),
        "indicator_description": _bounded_text(indicator_description, 1_000),
        "effect": effect,
        "observed_at": _bounded_text(observed_at, 120),
        "measurement": {
            "value": observed_value,
            "unit": _bounded_text(unit, 120),
            "baseline_value": baseline,
            "delta": observed_value - baseline if observed_value is not None and baseline is not None else None,
        },
        "rule": _bounded_json(rule),
        "evidence_refs": _bounded_list(evidence_refs, limit=100),
        "reason": _bounded_text(reason, 2_000),
        "provenance": {
            "source_kind": _bounded_text(source_kind, 120),
            "source_surface": _bounded_text(source_surface, 80),
            "actor_ref": _bounded_text(actor_ref, 240),
        },
        "compatibility": _compatibility("current", None, INDICATOR_OBSERVATION_CONTRACT_VERSION),
    }
    missing = [
        field
        for field in (
            "observation_id",
            "request_id",
            "decision_id",
            "prediction_id",
            "product_id",
            "indicator_id",
            "observed_at",
        )
        if not contract.get(field)
    ]
    if observed_value is None and not contract["reason"]:
        missing.append("measurement.value_or_reason")
    if not contract["evidence_refs"]:
        missing.append("evidence_refs")
    contract["completeness"] = {
        "state": "complete" if not missing else "partial",
        "missing_fields": missing,
    }
    return contract


def normalize_indicator_observation(record: dict | None) -> dict[str, Any]:
    """Return a bounded indicator observation or an explicit degraded projection."""
    record = record if isinstance(record, dict) else {}
    stored = record.get("indicator_contract")
    stored_version = (
        stored.get("contract_version") if isinstance(stored, dict) else record.get("indicator_contract_version")
    )
    if not isinstance(stored, dict) or stored_version != INDICATOR_OBSERVATION_CONTRACT_VERSION:
        reason = (
            "legacy_missing_indicator_contract"
            if not isinstance(stored, dict)
            else "unsupported_indicator_contract_version"
        )
        return {
            "contract_version": INDICATOR_OBSERVATION_CONTRACT_VERSION,
            "observation_id": _bounded_text(record.get("id"), 240),
            "request_id": _bounded_text(record.get("indicator_idempotency_key"), 240),
            "decision_id": _bounded_text(record.get("affected_decision"), 240),
            "prediction_id": _bounded_text(record.get("affected_prediction"), 240),
            "product_id": _bounded_text(record.get("product"), 240),
            "indicator_id": _bounded_text(record.get("indicator_local_id"), 120),
            "indicator_description": None,
            "effect": "inconclusive",
            "observed_at": _bounded_text(record.get("observed_at") or record.get("created_at"), 120),
            "measurement": {"value": None, "unit": None, "baseline_value": None, "delta": None},
            "rule": None,
            "evidence_refs": [],
            "reason": None,
            "provenance": {"source_kind": "legacy", "source_surface": None, "actor_ref": None},
            "completeness": {"state": "partial", "missing_fields": ["contract_version", "effect"]},
            "compatibility": _compatibility("degraded", reason, stored_version),
        }
    contract = _bounded_json(stored)
    if not isinstance(contract, dict):
        return normalize_indicator_observation(
            {key: value for key, value in record.items() if key != "indicator_contract"}
        )
    contract["observation_id"] = _bounded_text(record.get("id") or contract.get("observation_id"), 240)
    contract["decision_id"] = _bounded_text(record.get("affected_decision") or contract.get("decision_id"), 240)
    contract["prediction_id"] = _bounded_text(record.get("affected_prediction") or contract.get("prediction_id"), 240)
    contract["product_id"] = _bounded_text(record.get("product") or contract.get("product_id"), 240)
    malformed = contract.get("effect") not in INDICATOR_EFFECTS or not isinstance(contract.get("measurement"), dict)
    contract["contract_version"] = INDICATOR_OBSERVATION_CONTRACT_VERSION
    contract["compatibility"] = _compatibility(
        "degraded" if malformed else "current",
        "malformed_indicator_contract" if malformed else None,
        stored_version,
    )
    if malformed:
        contract["effect"] = "inconclusive"
        contract["completeness"] = {
            "state": "partial",
            "missing_fields": ["effect", "measurement"],
        }
    return contract


def build_intervention_observation_contract(
    *,
    observation_id: str,
    request_id: str,
    decision_id: str,
    prediction_id: str,
    product_id: str,
    status: str,
    observed_at: object,
    applicability_conditions_met: bool | None,
    conditions: list[dict] | None,
    exposure: dict | None,
    evidence_refs: list[str] | None,
    confounders: list[str] | None,
    missing_evidence: list[str] | None,
    reason: str | None,
    source_surface: str,
    actor_ref: str,
    actor_class: str = "authenticated_user",
) -> dict[str, Any]:
    """Build the immutable, provenance-bearing Intervention Observation v1 projection."""
    if status not in INTERVENTION_STATUSES:
        raise ValueError(f"unsupported intervention status: {status}")
    condition_items = [item for raw in (conditions or [])[:50] if (item := _condition_observation(raw)) is not None]
    exposure = exposure if isinstance(exposure, dict) else {}
    missing = _bounded_list(missing_evidence, limit=50)
    resolved_evidence_refs = sorted(
        {
            *_bounded_list(evidence_refs, limit=100),
            *(ref for item in condition_items for ref in item["evidence_refs"]),
        }
    )
    contract: dict[str, Any] = {
        "contract_version": INTERVENTION_OBSERVATION_CONTRACT_VERSION,
        "observation_id": _bounded_text(observation_id, 240),
        "request_id": _bounded_text(request_id, 240),
        "decision_id": _bounded_text(decision_id, 240),
        "prediction_id": _bounded_text(prediction_id, 240),
        "product_id": _bounded_text(product_id, 240),
        "status": status,
        "observed_at": _bounded_text(observed_at, 120),
        "exposure": {
            "degree": _bounded_float(exposure.get("degree"), low=0.0, high=1.0),
            "scope": _bounded_text(exposure.get("scope"), 1_000),
            "unit": _bounded_text(exposure.get("unit"), 120),
        },
        "applicability": {
            "conditions_met": applicability_conditions_met,
            "conditions": condition_items,
        },
        "evidence_refs": resolved_evidence_refs,
        "confounders": _bounded_list(confounders, limit=50),
        "missing_evidence": missing,
        "reason": _bounded_text(reason, 2_000),
        "provenance": {
            "source_surface": _bounded_text(source_surface, 80),
            "actor_ref": _bounded_text(actor_ref, 240),
            "actor_class": _bounded_text(actor_class, 120),
        },
        "compatibility": _compatibility("current", None, INTERVENTION_OBSERVATION_CONTRACT_VERSION),
    }
    missing_fields: list[str] = []
    for field in ("observation_id", "request_id", "decision_id", "prediction_id", "product_id", "observed_at"):
        if not contract.get(field):
            missing_fields.append(field)
    if status in SCORABLE_INTERVENTION_STATUSES and applicability_conditions_met is None:
        missing_fields.append("applicability.conditions_met")
    if status in SCORABLE_INTERVENTION_STATUSES and contract["exposure"]["degree"] is None:
        missing_fields.append("exposure.degree")
    if not contract["evidence_refs"]:
        missing_fields.append("evidence_refs")
    if missing:
        missing_fields.append("missing_evidence")
    contract["completeness"] = {
        "state": "complete" if not missing_fields else "partial",
        "missing_fields": missing_fields,
    }
    return contract


def normalize_intervention_observation(record: dict | None) -> dict[str, Any]:
    """Normalize an intervention observation while refusing to infer missing legacy facts."""
    record = record if isinstance(record, dict) else {}
    stored = record.get("intervention_contract")
    stored_version = (
        stored.get("contract_version") if isinstance(stored, dict) else record.get("intervention_contract_version")
    )
    if not isinstance(stored, dict) or stored_version != INTERVENTION_OBSERVATION_CONTRACT_VERSION:
        reason = (
            "legacy_missing_intervention_contract"
            if not isinstance(stored, dict)
            else "unsupported_intervention_contract_version"
        )
        return {
            "contract_version": INTERVENTION_OBSERVATION_CONTRACT_VERSION,
            "observation_id": _bounded_text(record.get("id"), 240),
            "request_id": _bounded_text(record.get("intervention_idempotency_key"), 240),
            "decision_id": _bounded_text(record.get("affected_decision"), 240),
            "prediction_id": _bounded_text(record.get("affected_prediction"), 240),
            "product_id": _bounded_text(record.get("product"), 240),
            "status": "unknown",
            "observed_at": _bounded_text(record.get("observed_at") or record.get("created_at"), 120),
            "exposure": {"degree": None, "scope": None, "unit": None},
            "applicability": {"conditions_met": None, "conditions": []},
            "evidence_refs": [],
            "confounders": [],
            "missing_evidence": ["legacy_intervention_provenance"],
            "reason": None,
            "provenance": {"source_surface": "legacy", "actor_ref": None, "actor_class": None},
            "completeness": {
                "state": "partial",
                "missing_fields": ["contract_version", "status", "applicability", "evidence_refs"],
            },
            "compatibility": _compatibility("degraded", reason, stored_version),
        }

    contract = _bounded_json(stored)
    if not isinstance(contract, dict):
        return normalize_intervention_observation(
            {key: value for key, value in record.items() if key != "intervention_contract"}
        )
    contract["contract_version"] = INTERVENTION_OBSERVATION_CONTRACT_VERSION
    contract["observation_id"] = _bounded_text(record.get("id") or contract.get("observation_id"), 240)
    contract["decision_id"] = _bounded_text(record.get("affected_decision") or contract.get("decision_id"), 240)
    contract["prediction_id"] = _bounded_text(record.get("affected_prediction") or contract.get("prediction_id"), 240)
    contract["product_id"] = _bounded_text(record.get("product") or contract.get("product_id"), 240)
    malformed = (
        contract.get("status") not in INTERVENTION_STATUSES
        or not isinstance(contract.get("applicability"), dict)
        or not isinstance(contract.get("exposure"), dict)
    )
    if malformed:
        contract["status"] = "unknown"
        contract["compatibility"] = _compatibility("degraded", "malformed_intervention_contract", stored_version)
        contract["completeness"] = {
            "state": "partial",
            "missing_fields": ["status", "applicability", "exposure"],
        }
    else:
        contract["compatibility"] = _compatibility("current", None, stored_version)
    return contract


def build_comparator_observation_contract(
    *,
    observation_id: str,
    request_id: str,
    decision_id: str,
    prediction_id: str,
    product_id: str,
    comparator_type: str,
    design: str,
    observed_at: object,
    measurements: list[dict] | None,
    comparator_label: str | None = None,
    window_start: object = None,
    window_end: object = None,
    evidence_refs: list[str] | None = None,
    confounders: list[str] | None = None,
    missing_evidence: list[str] | None = None,
    reason: str | None = None,
    source_surface: str = "api",
    actor_ref: str = "authenticated_user",
) -> dict[str, Any]:
    """Build immutable observed-comparator evidence with deterministic effect calculations."""
    if comparator_type not in COMPARATOR_TYPES:
        raise ValueError(f"unsupported comparator type: {comparator_type}")
    if design not in COMPARATOR_DESIGNS:
        raise ValueError(f"unsupported comparator design: {design}")

    normalized_measurements: list[dict[str, Any]] = []
    measurement_missing: list[str] = []
    all_evidence = set(_bounded_list(evidence_refs, limit=100))
    for index, raw in enumerate((measurements or [])[:25]):
        if not isinstance(raw, dict):
            measurement_missing.append(f"measurements:{index}:malformed")
            continue
        capability_id = _bounded_text(raw.get("capability_id"), 240)
        intervention_before = _bounded_float(raw.get("intervention_before"))
        intervention_after = _bounded_float(raw.get("intervention_after"))
        comparator_before = _bounded_float(raw.get("comparator_before"))
        comparator_after = _bounded_float(raw.get("comparator_after"))
        refs = _bounded_list(raw.get("evidence_refs"), limit=50)
        all_evidence.update(refs)
        values = (intervention_before, intervention_after, comparator_before, comparator_after)
        intervention_delta = (
            intervention_after - intervention_before
            if intervention_before is not None and intervention_after is not None
            else None
        )
        comparator_delta = (
            comparator_after - comparator_before
            if comparator_before is not None and comparator_after is not None
            else None
        )
        effect_delta = (
            intervention_delta - comparator_delta
            if intervention_delta is not None and comparator_delta is not None
            else None
        )
        if capability_id is None:
            measurement_missing.append(f"measurements:{index}:capability_id")
        if any(value is None for value in values):
            measurement_missing.append(f"measurements:{index}:before_after_values")
        if not refs and not evidence_refs:
            measurement_missing.append(f"measurements:{index}:evidence_refs")
        normalized_measurements.append(
            {
                "local_id": f"measurement:{index + 1}",
                "target": {
                    "entity_id": capability_id,
                    "metric": _bounded_text(raw.get("metric"), 160) or "capability_quality",
                    "unit": _bounded_text(raw.get("unit"), 80) or "score_delta",
                },
                "intervention": {
                    "before": intervention_before,
                    "after": intervention_after,
                    "delta": intervention_delta,
                },
                "comparator": {
                    "before": comparator_before,
                    "after": comparator_after,
                    "delta": comparator_delta,
                },
                "effect_delta": effect_delta,
                "evidence_refs": refs,
            }
        )

    missing = _bounded_list(missing_evidence, limit=50) + measurement_missing
    if not normalized_measurements:
        missing.append("measurements")
    if design == "unknown":
        missing.append("design")
    if not all_evidence:
        missing.append("evidence_refs")
    missing = list(dict.fromkeys(missing))
    eligible = bool(normalized_measurements) and not missing
    attribution_strength = {
        "randomized": "stronger",
        "matched": "moderate",
        "quasi_experimental": "moderate",
        "observational": "limited",
        "unknown": "unknown",
    }[design]
    contract: dict[str, Any] = {
        "contract_version": COMPARATOR_OBSERVATION_CONTRACT_VERSION,
        "observation_id": _bounded_text(observation_id, 240),
        "request_id": _bounded_text(request_id, 240),
        "decision_id": _bounded_text(decision_id, 240),
        "prediction_id": _bounded_text(prediction_id, 240),
        "product_id": _bounded_text(product_id, 240),
        "comparator": {
            "type": comparator_type,
            "label": _bounded_text(comparator_label, 500),
            "design": design,
            "attribution_strength": attribution_strength,
            "causal_claim": False,
            "causal_identification": (
                "design_supports_bounded_claim_but_is_not_independently_verified"
                if design == "randomized"
                else "not_identified"
            ),
        },
        "observed_at": _bounded_text(observed_at, 120),
        "observation_window": {
            "start": _bounded_text(window_start, 120),
            "end": _bounded_text(window_end, 120),
        },
        "measurements": normalized_measurements,
        "effect_method": "difference_in_differences/v1",
        "resolution_eligible": eligible,
        "non_eligibility_reasons": missing,
        "evidence_refs": sorted(all_evidence),
        "confounders": _bounded_list(confounders, limit=50),
        "missing_evidence": _bounded_list(missing_evidence, limit=50),
        "reason": _bounded_text(reason, 2_000),
        "provenance": {
            "source_surface": _bounded_text(source_surface, 80),
            "actor_ref": _bounded_text(actor_ref, 240),
            "actor_class": "authenticated_user",
        },
        "compatibility": _compatibility("current", None, COMPARATOR_OBSERVATION_CONTRACT_VERSION),
    }
    identity_missing = [
        field
        for field in ("observation_id", "request_id", "decision_id", "prediction_id", "product_id", "observed_at")
        if not contract.get(field)
    ]
    if identity_missing:
        contract["resolution_eligible"] = False
        contract["non_eligibility_reasons"] = list(
            dict.fromkeys(contract["non_eligibility_reasons"] + identity_missing)
        )
    contract["completeness"] = {
        "state": "complete" if contract["resolution_eligible"] else "partial",
        "missing_fields": contract["non_eligibility_reasons"],
    }
    return contract


def normalize_comparator_observation(record: dict | None) -> dict[str, Any]:
    """Return a bounded comparator contract, degrading legacy or malformed rows explicitly."""
    record = record if isinstance(record, dict) else {}
    stored = record.get("comparator_contract")
    stored_version = (
        stored.get("contract_version") if isinstance(stored, dict) else record.get("comparator_contract_version")
    )
    if not isinstance(stored, dict) or stored_version != COMPARATOR_OBSERVATION_CONTRACT_VERSION:
        reason = (
            "legacy_missing_comparator_contract"
            if not isinstance(stored, dict)
            else "unsupported_comparator_contract_version"
        )
        return {
            "contract_version": COMPARATOR_OBSERVATION_CONTRACT_VERSION,
            "observation_id": _bounded_text(record.get("id"), 240),
            "request_id": _bounded_text(record.get("comparator_idempotency_key"), 240),
            "decision_id": _bounded_text(record.get("affected_decision"), 240),
            "prediction_id": _bounded_text(record.get("affected_prediction"), 240),
            "product_id": _bounded_text(record.get("product"), 240),
            "comparator": {
                "type": None,
                "label": None,
                "design": "unknown",
                "attribution_strength": "unknown",
                "causal_claim": False,
            },
            "measurements": [],
            "effect_method": "difference_in_differences/v1",
            "resolution_eligible": False,
            "non_eligibility_reasons": [reason],
            "evidence_refs": [],
            "confounders": [],
            "missing_evidence": ["legacy_comparator_provenance"],
            "execution": {"plan_id": None},
            "plan_alignment": {
                "state": "unlinked",
                "plan_id": None,
                "effective_attribution_strength": "unknown",
                "causal_claim": False,
            },
            "completeness": {"state": "partial", "missing_fields": ["contract_version"]},
            "compatibility": _compatibility("degraded", reason, stored_version),
        }
    contract = _bounded_json(stored)
    if not isinstance(contract, dict):
        return normalize_comparator_observation(
            {key: value for key, value in record.items() if key != "comparator_contract"}
        )
    contract["contract_version"] = COMPARATOR_OBSERVATION_CONTRACT_VERSION
    contract["observation_id"] = _bounded_text(record.get("id") or contract.get("observation_id"), 240)
    contract["decision_id"] = _bounded_text(record.get("affected_decision") or contract.get("decision_id"), 240)
    contract["prediction_id"] = _bounded_text(record.get("affected_prediction") or contract.get("prediction_id"), 240)
    contract["product_id"] = _bounded_text(record.get("product") or contract.get("product_id"), 240)
    comparator = contract.get("comparator")
    measurements = contract.get("measurements")
    malformed = (
        not isinstance(comparator, dict)
        or comparator.get("type") not in COMPARATOR_TYPES
        or comparator.get("design") not in COMPARATOR_DESIGNS
        or not isinstance(measurements, list)
    )
    if malformed:
        contract["resolution_eligible"] = False
        contract["non_eligibility_reasons"] = ["malformed_comparator_contract"]
        contract["completeness"] = {"state": "partial", "missing_fields": ["comparator", "measurements"]}
    else:
        contract["resolution_eligible"] = bool(contract.get("resolution_eligible"))
        contract.setdefault("execution", {"plan_id": None})
        contract.setdefault(
            "plan_alignment",
            {
                "state": "unlinked",
                "plan_id": None,
                "effective_attribution_strength": comparator.get("attribution_strength", "unknown"),
                "causal_claim": False,
            },
        )
    contract["compatibility"] = _compatibility(
        "degraded" if malformed else "current",
        "malformed_comparator_contract" if malformed else None,
        stored_version,
    )
    return contract


def _consequence(change: dict, index: int) -> dict[str, Any]:
    point = _bounded_float(change.get("score_delta"), low=-1.0, high=1.0)
    lower = _bounded_float(change.get("lower_bound"), low=-1.0, high=1.0)
    upper = _bounded_float(change.get("upper_bound"), low=-1.0, high=1.0)
    if lower is not None and upper is not None and lower > upper:
        lower, upper = upper, lower
    interval_coverage = _bounded_float(change.get("interval_coverage"))
    if interval_coverage is None or not 0.0 < interval_coverage < 1.0:
        interval_coverage = None
    return {
        "local_id": f"consequence:{index + 1}",
        "target": {
            "entity_id": _bounded_text(change.get("capability_id"), 240),
            "metric": _bounded_text(change.get("metric"), 160) or "capability_quality",
            "unit": _bounded_text(change.get("unit"), 80) or "score_delta",
        },
        "estimate": {
            "kind": "continuous",
            "point": point,
            "lower": lower,
            "upper": upper,
            "interval_coverage": interval_coverage,
            "probability": _bounded_float(change.get("probability", change.get("confidence")), low=0.0, high=1.0),
        },
        "order": max(1, int(_bounded_float(change.get("order"), low=1.0, high=9.0) or 1)),
        "lag_days": _bounded_float(change.get("lag_days"), low=0.0),
        "mechanism": _bounded_text(change.get("mechanism"), 2_000),
        "assumptions": _bounded_list(change.get("assumptions")),
        "dependencies": _bounded_list(change.get("dependencies")),
        "confounders": _bounded_list(change.get("confounders")),
        "evidence_refs": _bounded_list(change.get("evidence_refs"), limit=50),
    }


def build_comparator_plan(
    raw_plan: object,
    *,
    consequences: list[dict],
    horizon_days: int,
    decision_id: str | None = None,
    product_id: str | None = None,
) -> dict[str, Any]:
    """Build an optional plan that can generate evidence without being mistaken for evidence."""
    targets: dict[str, dict[str, Any]] = {}
    for consequence in consequences[:25]:
        if not isinstance(consequence, dict):
            continue
        target = consequence.get("target")
        if not isinstance(target, dict):
            continue
        entity_id = _bounded_text(target.get("entity_id"), 240)
        if entity_id:
            targets[entity_id] = target

    if not isinstance(raw_plan, dict):
        return {
            "contract_version": COMPARATOR_PLAN_VERSION,
            "plan_id": None,
            "local_id": "comparator-plan:1",
            "status": "not_proposed",
            "feasibility": {
                "state": "unknown",
                "reason": "forecaster_did_not_propose_comparator",
                "required_conditions": [],
                "operator_confirmation_required": True,
            },
            "comparator": {"type": None, "assignment_design": "unknown", "label": None},
            "measurements": [],
            "timing": {"start_before_intervention": True, "minimum_duration_days": None},
            "assignment": {"unit": None, "allocation": None, "eligibility_criteria": []},
            "guardrails": [],
            "sample_size": {
                "state": "not_estimated",
                "reason": "no_variance_or_minimum_effect_inputs",
            },
            "fallback": {
                "method": "pre_post_observation",
                "limitation": "Without a concurrent comparator, change cannot be attributed to the intervention.",
            },
            "evidence_status": "plan_only_not_observed",
            "resolution_eligible": False,
            "limitations": [
                "A proposed design is not evidence that assignment or measurement occurred.",
                "Operational, ethical, privacy, and safety approval remains external to ACE.",
            ],
            "completeness": {"state": "absent", "missing_fields": ["comparator_plan"]},
            "compatibility": _compatibility("current", None, COMPARATOR_PLAN_VERSION),
        }

    comparator_type = _bounded_text(raw_plan.get("comparator_type"), 80)
    if comparator_type not in COMPARATOR_TYPES:
        comparator_type = None
    assignment_design = _bounded_text(raw_plan.get("assignment_design"), 80)
    if assignment_design not in COMPARATOR_DESIGNS:
        assignment_design = "unknown"
    requested_feasibility = _bounded_text(raw_plan.get("feasibility"), 80)
    # Model output can suggest conditional feasibility, never establish it. A claimed `feasible`
    # plan is deliberately downgraded until an operator confirms real operational constraints.
    if requested_feasibility == "feasible":
        feasibility = "conditional"
    elif requested_feasibility in COMPARATOR_PLAN_FEASIBILITY:
        feasibility = requested_feasibility
    else:
        feasibility = "unknown"

    raw_measurements = raw_plan.get("measurements")
    raw_by_target: dict[str, dict] = {}
    if isinstance(raw_measurements, list):
        for item in raw_measurements[:25]:
            if not isinstance(item, dict):
                continue
            capability_id = _bounded_text(item.get("capability_id"), 240)
            if capability_id in targets and capability_id not in raw_by_target:
                raw_by_target[capability_id] = item
    measurements = []
    for index, (capability_id, target) in enumerate(targets.items()):
        raw = raw_by_target.get(capability_id, {})
        measurements.append(
            {
                "local_id": f"measurement-plan:{index + 1}",
                "target": {
                    "entity_id": capability_id,
                    "metric": _bounded_text(raw.get("metric"), 160)
                    or _bounded_text(target.get("metric"), 160)
                    or "capability_quality",
                    "unit": _bounded_text(raw.get("unit"), 80)
                    or _bounded_text(target.get("unit"), 80)
                    or "score_delta",
                },
                "baseline_source": _bounded_text(raw.get("baseline_source"), 500),
                "outcome_source": _bounded_text(raw.get("outcome_source"), 500),
                "cadence": _bounded_text(raw.get("cadence"), 160),
            }
        )

    minimum_duration = _bounded_float(raw_plan.get("minimum_duration_days"), low=1.0, high=float(max(1, horizon_days)))
    required_conditions = _bounded_list(raw_plan.get("required_conditions"), limit=25)
    missing: list[str] = []
    if comparator_type is None:
        missing.append("comparator.type")
    if assignment_design == "unknown":
        missing.append("comparator.assignment_design")
    if not measurements:
        missing.append("measurements")
    for index, measurement in enumerate(measurements):
        if not measurement.get("baseline_source"):
            missing.append(f"measurements.{index}.baseline_source")
        if not measurement.get("outcome_source"):
            missing.append(f"measurements.{index}.outcome_source")
    assignment_unit = _bounded_text(raw_plan.get("assignment_unit"), 240)
    if assignment_unit is None:
        missing.append("assignment.unit")
    if not required_conditions:
        missing.append("feasibility.required_conditions")
    feasibility_reason = _bounded_text(raw_plan.get("feasibility_reason"), 1_000)
    if feasibility_reason is None:
        missing.append("feasibility.reason")
    if minimum_duration is None:
        missing.append("timing.minimum_duration_days")
    guardrails = _bounded_list(raw_plan.get("guardrails"), limit=25)
    if not guardrails:
        missing.append("guardrails")
    if feasibility == "not_feasible":
        status = "not_feasible"
    elif missing or feasibility == "unknown":
        status = "needs_operator_review"
    else:
        status = "proposed"
    plan = {
        "contract_version": COMPARATOR_PLAN_VERSION,
        "local_id": "comparator-plan:1",
        "status": status,
        "feasibility": {
            "state": feasibility,
            "reason": feasibility_reason,
            "required_conditions": required_conditions,
            "operator_confirmation_required": True,
        },
        "comparator": {
            "type": comparator_type,
            "assignment_design": assignment_design,
            "label": _bounded_text(raw_plan.get("comparator_label"), 500),
        },
        "measurements": measurements,
        "timing": {
            "start_before_intervention": True,
            "minimum_duration_days": int(minimum_duration) if minimum_duration is not None else None,
        },
        "assignment": {
            "unit": assignment_unit,
            "allocation": _bounded_text(raw_plan.get("allocation"), 500),
            "eligibility_criteria": _bounded_list(raw_plan.get("eligibility_criteria"), limit=25),
        },
        "guardrails": guardrails,
        "sample_size": {
            "state": "not_estimated",
            "reason": "no_variance_or_minimum_effect_inputs",
        },
        "fallback": {
            "method": "pre_post_observation",
            "limitation": "Without a concurrent comparator, change cannot be attributed to the intervention.",
        },
        "evidence_status": "plan_only_not_observed",
        "resolution_eligible": False,
        "limitations": [
            "A proposed design is not evidence that assignment or measurement occurred.",
            "Model-suggested feasibility requires operator confirmation.",
            "Operational, ethical, privacy, and safety approval remains external to ACE.",
            "Sample size is not estimated without variance and minimum-effect inputs.",
        ],
        "completeness": {
            "state": "complete" if not missing else "partial",
            "missing_fields": missing,
        },
        "compatibility": _compatibility("current", None, COMPARATOR_PLAN_VERSION),
    }
    identity_payload = json.dumps(
        {
            "contract_version": COMPARATOR_PLAN_VERSION,
            "decision_id": _bounded_text(decision_id, 240),
            "product_id": _bounded_text(product_id, 240),
            "plan": plan,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    plan["plan_id"] = f"comparator_plan:{hashlib.sha256(identity_payload.encode()).hexdigest()[:24]}"
    return plan


def normalize_comparator_plan(record: dict | None) -> dict[str, Any]:
    """Read a current plan from the row or frozen forecast without promoting legacy prose."""
    record = record if isinstance(record, dict) else {}
    plan = record.get("comparator_plan")
    if not isinstance(plan, dict):
        forecast = record.get("forecast_contract")
        evaluation = forecast.get("evaluation") if isinstance(forecast, dict) else None
        plan = evaluation.get("comparator_plan") if isinstance(evaluation, dict) else None
    version = plan.get("contract_version") if isinstance(plan, dict) else record.get("comparator_plan_version")
    if not isinstance(plan, dict) or version != COMPARATOR_PLAN_VERSION:
        degraded = build_comparator_plan(
            None,
            consequences=[],
            horizon_days=int(record.get("horizon_days") or 14),
        )
        degraded["compatibility"] = _compatibility(
            "degraded",
            "legacy_missing_comparator_plan" if not isinstance(plan, dict) else "unsupported_comparator_plan_version",
            version,
        )
        return degraded
    normalized = _bounded_json(plan)
    if not isinstance(normalized, dict):
        return normalize_comparator_plan({})
    normalized["contract_version"] = COMPARATOR_PLAN_VERSION
    normalized["resolution_eligible"] = False
    normalized["evidence_status"] = "plan_only_not_observed"
    normalized["compatibility"] = _compatibility("current", None, version)
    return normalized


def _forecast_missing_fields(contract: dict) -> list[str]:
    missing: list[str] = []
    intervention = contract.get("intervention") if isinstance(contract.get("intervention"), dict) else {}
    baseline = contract.get("baseline") if isinstance(contract.get("baseline"), dict) else {}
    resolution = contract.get("resolution_rule") if isinstance(contract.get("resolution_rule"), dict) else {}
    consequences = contract.get("consequences") if isinstance(contract.get("consequences"), list) else []

    if not intervention.get("conditions"):
        missing.append("intervention.conditions")
    if baseline.get("current_state") is None:
        missing.append("baseline.current_state")
    if not baseline.get("observation_refs"):
        missing.append("baseline.observation_refs")
    if baseline.get("no_action") is None:
        missing.append("baseline.no_action")
    if not consequences:
        missing.append("consequences")
    for index, consequence in enumerate(consequences):
        if not isinstance(consequence, dict):
            missing.append(f"consequences.{index}")
            continue
        estimate = consequence.get("estimate") or {}
        if not isinstance(estimate, dict):
            estimate = {}
        if estimate.get("lower") is None or estimate.get("upper") is None:
            missing.append(f"consequences.{index}.estimate.range")
        if estimate.get("interval_coverage") is None:
            missing.append(f"consequences.{index}.estimate.interval_coverage")
        if consequence.get("mechanism") is None:
            missing.append(f"consequences.{index}.mechanism")
        if not consequence.get("evidence_refs"):
            missing.append(f"consequences.{index}.evidence_refs")
    if not resolution.get("falsification_condition"):
        missing.append("resolution_rule.falsification_condition")
    return missing


def build_forecast_contract(
    raw: dict,
    *,
    decision_id: str,
    product_id: str,
    archetype: str,
    discipline: str,
    model: str | None,
    intervention_status: str = "authorized",
    current_state_baseline: dict | None = None,
    baseline_observed_at: object = None,
    baseline_observation_refs: list[str] | None = None,
    outside_view_baseline: dict | None = None,
) -> dict[str, Any]:
    """Build the immutable v1 forecast projection from structured forecaster output."""
    if intervention_status not in INTERVENTION_STATUSES:
        raise ValueError(f"unsupported intervention status: {intervention_status}")
    changes = [change for change in (raw.get("expected_changes") or []) if isinstance(change, dict)]
    consequences = [_consequence(change, index) for index, change in enumerate(changes[:25])]
    horizon_days = int(_bounded_float(raw.get("horizon_days"), low=1.0, high=3650.0) or 14)
    comparator_plan = build_comparator_plan(
        raw.get("comparator_plan"),
        consequences=consequences,
        horizon_days=horizon_days,
        decision_id=decision_id,
        product_id=product_id,
    )
    indicators, indicator_monitoring = _indicator_catalog(raw)
    evidence_refs = sorted({ref for consequence in consequences for ref in consequence.get("evidence_refs", [])})
    contract: dict[str, Any] = {
        "contract_version": FORECAST_CONTRACT_VERSION,
        "forecast_id": None,
        "decision_id": _bounded_text(decision_id, 240),
        "product_id": _bounded_text(product_id, 240),
        "status": "open",
        "intervention": {
            "status": intervention_status,
            "conditions": _bounded_list(raw.get("applicability_conditions")),
            "expected_start_at": None,
            "exposure": None,
        },
        "baseline": {
            "current_state": _bounded_json(current_state_baseline),
            "observed_at": _bounded_text(baseline_observed_at, 120),
            "observation_refs": _bounded_list(baseline_observation_refs, limit=100),
            "no_action": _bounded_text(raw.get("no_action_baseline"), 2_000),
            "no_action_grounding": {
                "state": "model_inference_only",
                "empirically_identified": False,
                "reason": "no_observed_no_action_comparator",
            },
            "compared_alternatives": _bounded_list(raw.get("compared_alternatives")),
            "outside_view": _bounded_json(outside_view_baseline),
        },
        "consequences": consequences,
        "evaluation": {"comparator_plan": comparator_plan},
        "resolution_rule": {
            "horizon_days": horizon_days,
            "due_at": None,
            "leading_indicators": _bounded_list(raw.get("leading_indicators")),
            "indicators": indicators,
            "indicator_monitoring": indicator_monitoring,
            "falsification_condition": _bounded_text(raw.get("falsification_condition"), 2_000),
            "observation_required": True,
        },
        "risk": _bounded_text(raw.get("primary_risk"), 2_000),
        "contributors": [
            {
                "archetype": _bounded_text(archetype, 120) or "ace",
                "discipline": _bounded_text(discipline, 160) or "general",
            }
        ],
        "provenance": {
            "source_kind": "model_inference",
            "model": _bounded_text(model, 300),
            "evidence_refs": evidence_refs,
        },
        "compatibility": _compatibility("current", None, FORECAST_CONTRACT_VERSION),
    }
    missing = _forecast_missing_fields(contract)
    contract["completeness"] = {
        "state": "complete" if not missing else "partial",
        "missing_fields": missing,
    }
    return contract


def _legacy_forecast_contract(record: dict, *, reason: str, stored_version: object = None) -> dict[str, Any]:
    raw = {
        "horizon_days": record.get("horizon_days"),
        "expected_changes": record.get("expected_changes") or [],
        "primary_risk": record.get("primary_risk"),
        "leading_indicators": record.get("leading_indicators") or [],
        "falsification_condition": record.get("falsification_condition"),
    }
    contract = build_forecast_contract(
        raw,
        decision_id=str(record.get("decision", "")),
        product_id=str(record.get("product", "")),
        archetype=str(record.get("archetype", "ace")),
        discipline=str(record.get("discipline", "general")),
        model=None,
        intervention_status="unknown",
    )
    contract["forecast_id"] = _bounded_text(record.get("id"), 240)
    contract["status"] = "resolved" if bool(record.get("closed")) else "open"
    contract["compatibility"] = _compatibility("degraded", reason, stored_version)
    missing = list(contract["completeness"]["missing_fields"])
    if "contract_version" not in missing:
        missing.insert(0, "contract_version")
    contract["completeness"] = {"state": "partial", "missing_fields": missing}
    return contract


def normalize_forecast_record(record: dict | None) -> dict[str, Any]:
    """Return a bounded v1 projection while preserving legacy/version gaps."""
    record = record if isinstance(record, dict) else {}
    stored = record.get("forecast_contract")
    stored_version = None
    if isinstance(stored, dict):
        stored_version = stored.get("contract_version")
    if stored_version is None:
        stored_version = record.get("contract_version")
    if not isinstance(stored, dict):
        return _legacy_forecast_contract(
            record,
            reason="legacy_missing_forecast_contract",
            stored_version=stored_version,
        )
    if stored_version != FORECAST_CONTRACT_VERSION:
        return _legacy_forecast_contract(
            record,
            reason="unsupported_forecast_contract_version",
            stored_version=stored_version,
        )

    contract = _bounded_json(stored)
    if not isinstance(contract, dict):
        return _legacy_forecast_contract(
            record,
            reason="malformed_forecast_contract",
            stored_version=stored_version,
        )
    contract["contract_version"] = FORECAST_CONTRACT_VERSION
    contract["forecast_id"] = _bounded_text(record.get("id") or contract.get("forecast_id"), 240)
    contract["decision_id"] = _bounded_text(record.get("decision") or contract.get("decision_id"), 240)
    contract["product_id"] = _bounded_text(record.get("product") or contract.get("product_id"), 240)
    contract["status"] = "resolved" if bool(record.get("closed")) else "open"
    baseline = contract.get("baseline")
    if isinstance(baseline, dict):
        baseline.setdefault(
            "no_action_grounding",
            {
                "state": "legacy_unknown",
                "empirically_identified": False,
                "reason": "forecast_predates_explicit_no_action_grounding",
            },
        )
        baseline.setdefault("outside_view", None)
    resolution_rule = contract.get("resolution_rule")
    if isinstance(resolution_rule, dict) and not isinstance(resolution_rule.get("indicators"), list):
        indicators, monitoring = _indicator_catalog(
            {"leading_indicators": resolution_rule.get("leading_indicators") or []}
        )
        resolution_rule["indicators"] = indicators
        resolution_rule["indicator_monitoring"] = monitoring
    evaluation = contract.get("evaluation")
    if not isinstance(evaluation, dict) or not isinstance(evaluation.get("comparator_plan"), dict):
        plan_horizon_days = int(resolution_rule.get("horizon_days") or 14) if isinstance(resolution_rule, dict) else 14
        contract["evaluation"] = {
            "comparator_plan": build_comparator_plan(
                None,
                consequences=contract.get("consequences") or [],
                horizon_days=plan_horizon_days,
            )
        }
    missing = _forecast_missing_fields(contract)
    malformed = any(
        not isinstance(contract.get(field), expected)
        for field, expected in (
            ("intervention", dict),
            ("baseline", dict),
            ("consequences", list),
            ("resolution_rule", dict),
        )
    )
    contract["compatibility"] = _compatibility(
        "degraded" if malformed else "current",
        "malformed_forecast_contract" if malformed else None,
        stored_version,
    )
    contract["completeness"] = {
        "state": "complete" if not missing else "partial",
        "missing_fields": missing,
    }
    return contract


@dataclass(frozen=True)
class ResolutionAssessment:
    state: str
    score_eligible: bool
    non_score_reason: str | None


def assess_resolution(
    *,
    requested_state: str | None,
    intervention_status: str,
    applicability_conditions_met: bool | None,
    actual_deltas: dict[str, float],
    calibration_scores: list[float],
    missing_evidence: list[str],
) -> ResolutionAssessment:
    """Classify a resolution without converting absence or inapplicability into a score."""
    if requested_state is not None and requested_state not in RESOLUTION_STATES:
        raise ValueError(f"unsupported resolution state: {requested_state}")
    if intervention_status not in INTERVENTION_STATUSES:
        raise ValueError(f"unsupported intervention status: {intervention_status}")
    if intervention_status == "cancelled":
        return ResolutionAssessment("invalid", False, "intervention_cancelled")
    if applicability_conditions_met is False:
        return ResolutionAssessment("invalid", False, "applicability_conditions_failed")
    if requested_state in {"open", "unresolved", "invalid"}:
        return ResolutionAssessment(requested_state, False, f"resolution_marked_{requested_state}")
    if intervention_status not in SCORABLE_INTERVENTION_STATUSES:
        return ResolutionAssessment("unresolved", False, "intervention_not_observed")
    if applicability_conditions_met is not True:
        return ResolutionAssessment("unresolved", False, "applicability_conditions_unverified")
    if missing_evidence:
        return ResolutionAssessment("unresolved", False, "missing_resolution_evidence")
    if not actual_deltas or not calibration_scores:
        return ResolutionAssessment("unresolved", False, "missing_observation")
    if requested_state in {"confirmed", "contradicted", "mixed"}:
        return ResolutionAssessment(requested_state, True, None)
    score = sum(calibration_scores) / len(calibration_scores)
    if score >= 0.8:
        state = "confirmed"
    elif score <= 0.5:
        state = "contradicted"
    else:
        state = "mixed"
    return ResolutionAssessment(state, True, None)


def build_resolution_contract(
    *,
    prediction_id: str,
    decision_id: str,
    product_id: str,
    assessment: ResolutionAssessment,
    intervention_status: str,
    applicability_conditions_met: bool | None,
    predicted_deltas: dict[str, float],
    actual_deltas: dict[str, float],
    calibration_score: float | None,
    observation_refs: list[str] | None,
    confounders: list[str] | None,
    missing_evidence: list[str] | None,
    resolution_reason: str | None,
    outside_view_comparison: dict | None = None,
    prediction_score: dict | None = None,
    comparator_context: dict | None = None,
) -> dict[str, Any]:
    """Build a v1 resolution record without mutating or embedding the original forecast."""
    missing = _bounded_list(missing_evidence)
    contract = {
        "contract_version": RESOLUTION_CONTRACT_VERSION,
        "resolution_id": None,
        "prediction_id": _bounded_text(prediction_id, 240),
        "decision_id": _bounded_text(decision_id, 240),
        "product_id": _bounded_text(product_id, 240),
        "state": assessment.state,
        "score_eligible": assessment.score_eligible,
        "non_score_reason": assessment.non_score_reason,
        "intervention": {
            "status": intervention_status,
            "applicability_conditions_met": applicability_conditions_met,
        },
        "observations": {
            "predicted_deltas": {str(k): float(v) for k, v in predicted_deltas.items()},
            "actual_deltas": {str(k): float(v) for k, v in actual_deltas.items()},
            "observation_refs": _bounded_list(observation_refs, limit=50),
            "observed_at": None,
        },
        "comparator": _bounded_json(comparator_context),
        "confounders": _bounded_list(confounders),
        "missing_evidence": missing,
        "resolution_reason": _bounded_text(resolution_reason, 2_000),
        "scoring": {
            "method": "bounded_absolute_delta/v1" if assessment.score_eligible else None,
            "calibration_score": calibration_score if assessment.score_eligible else None,
            "outside_view_comparison": _bounded_json(outside_view_comparison),
            "prediction_score": _bounded_json(prediction_score),
        },
        "provenance": {
            "source_kind": "observed_outcome" if observation_refs else "unreferenced_observation",
            "observation_refs": _bounded_list(observation_refs, limit=50),
        },
        "compatibility": _compatibility("current", None, RESOLUTION_CONTRACT_VERSION),
    }
    contract["completeness"] = {
        "state": "complete" if not missing and observation_refs else "partial",
        "missing_fields": (["provenance.observation_refs"] if not observation_refs else [])
        + (["missing_evidence"] if missing else []),
    }
    return contract


def normalize_resolution_record(record: dict | None) -> dict[str, Any]:
    """Normalize current resolution rows and degrade legacy/unknown versions explicitly."""
    record = record if isinstance(record, dict) else {}
    stored = record.get("resolution_contract")
    stored_version = stored.get("contract_version") if isinstance(stored, dict) else record.get("contract_version")
    if not isinstance(stored, dict) or stored_version != RESOLUTION_CONTRACT_VERSION:
        reason = (
            "legacy_missing_resolution_contract"
            if not isinstance(stored, dict)
            else "unsupported_resolution_contract_version"
        )
        state = _bounded_text(record.get("resolution_state"), 80) or (
            "mixed" if record.get("calibration_score") is not None else "unresolved"
        )
        return {
            "contract_version": RESOLUTION_CONTRACT_VERSION,
            "resolution_id": _bounded_text(record.get("id"), 240),
            "prediction_id": _bounded_text(record.get("prediction"), 240),
            "decision_id": _bounded_text(record.get("decision"), 240),
            "product_id": _bounded_text(record.get("product"), 240),
            "state": state if state in RESOLUTION_STATES else "unresolved",
            "score_eligible": bool(record.get("calibration_score") is not None),
            "non_score_reason": None if record.get("calibration_score") is not None else "legacy_missing_score",
            "intervention": {"status": "unknown", "applicability_conditions_met": None},
            "observations": {
                "predicted_deltas": _bounded_json(record.get("predicted_deltas") or {}),
                "actual_deltas": _bounded_json(record.get("actual_deltas") or {}),
                "observation_refs": [],
                "observed_at": record.get("closed_at"),
            },
            "confounders": [],
            "missing_evidence": ["legacy_resolution_provenance"],
            "resolution_reason": None,
            "scoring": {
                "method": "legacy_bounded_absolute_delta/v0" if record.get("calibration_score") is not None else None,
                "calibration_score": record.get("calibration_score"),
            },
            "provenance": {"source_kind": "legacy", "observation_refs": []},
            "completeness": {
                "state": "partial",
                "missing_fields": ["contract_version", "intervention", "provenance.observation_refs"],
            },
            "compatibility": _compatibility("degraded", reason, stored_version),
        }

    contract = _bounded_json(stored)
    if not isinstance(contract, dict):
        return normalize_resolution_record(
            {key: value for key, value in record.items() if key != "resolution_contract"}
        )
    contract["contract_version"] = RESOLUTION_CONTRACT_VERSION
    contract["resolution_id"] = _bounded_text(record.get("id") or contract.get("resolution_id"), 240)
    contract["prediction_id"] = _bounded_text(record.get("prediction") or contract.get("prediction_id"), 240)
    contract["decision_id"] = _bounded_text(record.get("decision") or contract.get("decision_id"), 240)
    contract["product_id"] = _bounded_text(record.get("product") or contract.get("product_id"), 240)
    raw_state = contract.get("state")
    if raw_state not in RESOLUTION_STATES:
        contract["state"] = "unresolved"
        contract["score_eligible"] = False
        contract["non_score_reason"] = "malformed_resolution_state"
        contract["compatibility"] = _compatibility("degraded", "malformed_resolution_contract", stored_version)
    else:
        contract["score_eligible"] = bool(contract.get("score_eligible"))
        contract["compatibility"] = _compatibility("current", None, stored_version)
    return contract
