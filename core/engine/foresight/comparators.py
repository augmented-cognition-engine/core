"""Idempotent observed-comparator evidence for decision forecasts.

Comparator observations are optional post-decision evidence. They never rewrite the frozen
forecast and are never required at cold start. Eligible rows expose a transparent
difference-in-differences effect for resolution; weaker rows remain inspectable evidence.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from core.engine.core.db import parse_one, parse_rows
from core.engine.core.db import pool as default_pool
from core.engine.foresight.contracts import (
    COMPARATOR_OBSERVATION_CONTRACT_VERSION,
    COMPARATOR_STATE_VERSION,
    build_comparator_observation_contract,
    normalize_comparator_observation,
    normalize_comparator_plan,
    normalize_forecast_record,
)


class ComparatorTargetNotFound(ValueError):
    """The prediction, decision, product, or measurement target does not match."""


class ComparatorRequestConflict(ValueError):
    """A comparator request ID was reused with different evidence."""


def _record_key(product_id: str, request_id: str) -> str:
    return hashlib.sha256(f"{product_id}|comparator|{request_id}".encode()).hexdigest()[:24]


def _fingerprint(product_id: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        {"product_id": product_id, "payload": payload},
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def comparator_effects(contract: dict) -> dict[str, float]:
    """Return eligible capability effects only; never invent or partially reconstruct them."""
    if not contract.get("resolution_eligible"):
        return {}
    effects: dict[str, float] = {}
    for measurement in contract.get("measurements") or []:
        if not isinstance(measurement, dict):
            return {}
        target = measurement.get("target") or {}
        capability_id = str(target.get("entity_id") or "")
        effect = measurement.get("effect_delta")
        if not capability_id or not isinstance(effect, (int, float)) or isinstance(effect, bool):
            return {}
        effects[capability_id] = float(effect)
    return effects


def _parsed_time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif value is not None:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _downgraded_attribution(strength: str, state: str) -> str:
    if state == "aligned":
        return strength
    if state == "partially_aligned":
        return {"stronger": "moderate", "moderate": "limited"}.get(strength, strength)
    if state == "not_aligned":
        return "limited" if strength in {"stronger", "moderate", "limited"} else "unknown"
    return strength


def evaluate_plan_alignment(
    *,
    plan: dict,
    observation_contract: dict,
    execution: dict | None,
    explicit_plan_id: str | None,
) -> dict[str, Any]:
    """Compare planned and observed facts without treating either as causal proof."""
    execution = execution if isinstance(execution, dict) else {}
    plan_id = str(plan.get("plan_id") or "")
    observed = observation_contract.get("comparator") or {}
    observed_strength = str(observed.get("attribution_strength") or "unknown")
    if not plan_id or plan.get("status") == "not_proposed":
        return {
            "state": "not_planned",
            "plan_id": None,
            "link_method": "none",
            "checks": [],
            "deviations": list(execution.get("deviations") or []),
            "effective_attribution_strength": observed_strength,
            "attribution_basis": "observed_design_only_no_plan",
            "causal_claim": False,
        }

    checks: list[dict[str, Any]] = []
    deviations = [str(item)[:1_000] for item in (execution.get("deviations") or [])[:25] if str(item)]

    planned_comparator = plan.get("comparator") or {}
    for dimension, planned_value, observed_value in (
        ("comparator_type", planned_comparator.get("type"), observed.get("type")),
        ("assignment_design", planned_comparator.get("assignment_design"), observed.get("design")),
    ):
        matched = bool(planned_value) and planned_value == observed_value
        checks.append(
            {
                "dimension": dimension,
                "state": "matched" if matched else "deviated",
                "planned": planned_value,
                "observed": observed_value,
            }
        )
        if not matched:
            deviations.append(f"{dimension}:planned={planned_value}:observed={observed_value}")

    planned_targets = {
        str((item.get("target") or {}).get("entity_id"))
        for item in (plan.get("measurements") or [])
        if isinstance(item, dict) and (item.get("target") or {}).get("entity_id")
    }
    observed_targets = {
        str((item.get("target") or {}).get("entity_id"))
        for item in (observation_contract.get("measurements") or [])
        if isinstance(item, dict) and (item.get("target") or {}).get("entity_id")
    }
    target_state = (
        "matched"
        if planned_targets and planned_targets == observed_targets
        else "partial"
        if planned_targets.intersection(observed_targets)
        else "deviated"
    )
    checks.append(
        {
            "dimension": "measurement_targets",
            "state": target_state,
            "planned": sorted(planned_targets),
            "observed": sorted(observed_targets),
        }
    )
    if target_state != "matched":
        deviations.append("measurement_targets_not_fully_aligned")

    planned_unit = str((plan.get("assignment") or {}).get("unit") or "")
    observed_unit = str(execution.get("assignment_unit") or "")
    unit_state = "matched" if planned_unit and planned_unit == observed_unit else "unverified"
    if observed_unit and planned_unit != observed_unit:
        unit_state = "deviated"
        deviations.append(f"assignment_unit:planned={planned_unit}:observed={observed_unit}")
    checks.append(
        {
            "dimension": "assignment_unit",
            "state": unit_state,
            "planned": planned_unit or None,
            "observed": observed_unit or None,
        }
    )

    eligibility_met = execution.get("eligibility_criteria_met")
    eligibility_state = (
        "matched" if eligibility_met is True else "deviated" if eligibility_met is False else "unverified"
    )
    checks.append(
        {
            "dimension": "eligibility_criteria",
            "state": eligibility_state,
            "planned": list((plan.get("assignment") or {}).get("eligibility_criteria") or []),
            "observed": eligibility_met,
        }
    )
    if eligibility_met is False:
        deviations.append("planned_eligibility_criteria_failed")

    minimum_days = (plan.get("timing") or {}).get("minimum_duration_days")
    window = observation_contract.get("observation_window") or {}
    start = _parsed_time(window.get("start"))
    end = _parsed_time(window.get("end"))
    observed_days = (end - start).total_seconds() / 86_400 if start and end and end >= start else None
    if minimum_days is None:
        duration_state = "unverified"
    elif observed_days is None:
        duration_state = "unverified"
    elif observed_days >= float(minimum_days):
        duration_state = "matched"
    else:
        duration_state = "deviated"
        deviations.append(f"duration_days:planned_minimum={minimum_days}:observed={observed_days:.3f}")
    checks.append(
        {
            "dimension": "duration",
            "state": duration_state,
            "planned_minimum_days": minimum_days,
            "observed_days": observed_days,
        }
    )

    breaches = [str(item)[:1_000] for item in (execution.get("guardrail_breaches") or [])[:25] if str(item)]
    checks.append(
        {
            "dimension": "guardrails",
            "state": "deviated" if breaches else "matched",
            "planned": list(plan.get("guardrails") or []),
            "observed_breaches": breaches,
        }
    )
    deviations.extend(f"guardrail_breach:{item}" for item in breaches)

    core_states = {item["dimension"]: item["state"] for item in checks}
    if (
        core_states["comparator_type"] == "deviated"
        or core_states["assignment_design"] == "deviated"
        or core_states["measurement_targets"] == "deviated"
    ):
        state = "not_aligned"
    elif (
        plan.get("status") != "proposed"
        or any(item["state"] in {"deviated", "partial", "unverified"} for item in checks)
        or deviations
    ):
        state = "partially_aligned"
    else:
        state = "aligned"
    effective = _downgraded_attribution(observed_strength, state)
    return {
        "state": state,
        "plan_id": plan_id,
        "link_method": "explicit_plan_id" if explicit_plan_id else "prediction_plan_auto_link",
        "checks": checks,
        "deviations": list(dict.fromkeys(deviations)),
        "effective_attribution_strength": effective,
        "attribution_basis": (
            "observed_design_with_aligned_plan"
            if state == "aligned"
            else "observed_design_downgraded_for_plan_deviation"
        ),
        "causal_claim": False,
    }


def _comparator_state(prediction_id: str, rows: list[dict]) -> dict[str, Any]:
    observations = [normalize_comparator_observation(row) for row in rows]
    latest = observations[0] if observations else None
    eligible = [item for item in observations if item.get("resolution_eligible")]
    status = "eligible" if eligible else "ineligible" if observations else "absent"
    return {
        "contract_version": COMPARATOR_STATE_VERSION,
        "prediction_id": prediction_id,
        "status": status,
        "latest": latest,
        "latest_eligible": eligible[0] if eligible else None,
        "observation_refs": [str(item.get("observation_id")) for item in observations if item.get("observation_id")],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "compatibility": {
            "state": "current",
            "reason": None,
            "stored_contract_version": COMPARATOR_STATE_VERSION,
        },
    }


async def _aggregate_comparator_state(pred: dict, product_id: str, *, pool) -> dict[str, Any]:
    prediction_id = str(pred.get("id", ""))
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT * FROM observation
                   WHERE product = <record>$product
                     AND observation_type = 'forecast_comparator'
                     AND affected_prediction = <record>$prediction
                   ORDER BY observed_at DESC, created_at DESC LIMIT 100""",
                {"product": product_id, "prediction": prediction_id},
            )
        )
    state = _comparator_state(prediction_id, rows)
    async with pool.connection() as db:
        await db.query(
            """UPDATE <record>$prediction SET
                   comparator_state_version = $state_version,
                   comparator_evidence_state = $state,
                   comparator_status = $status,
                   comparator_updated_at = time::now()
               WHERE product = <record>$product""",
            {
                "prediction": prediction_id,
                "product": product_id,
                "state_version": COMPARATOR_STATE_VERSION,
                "state": state,
                "status": state["status"],
            },
        )
    return state


async def record_comparator_observation(
    *,
    product_id: str,
    decision_id: str,
    prediction_id: str,
    request_id: str,
    comparator_type: str,
    design: str,
    observed_at: object,
    measurements: list[dict],
    comparator_label: str | None,
    window_start: object,
    window_end: object,
    evidence_refs: list[str] | None,
    confounders: list[str] | None,
    missing_evidence: list[str] | None,
    reason: str | None,
    content: str,
    source_surface: str,
    actor_ref: str,
    execution: dict | None = None,
    pool=None,
) -> dict[str, Any]:
    """Validate, idempotently persist, aggregate, and attempt horizon-gated reconciliation."""
    pool = pool or default_pool
    async with pool.connection() as db:
        pred = parse_one(await db.query("SELECT * FROM ONLY <record>$prediction", {"prediction": prediction_id}))
    if (
        not pred
        or str(pred.get("product", "")) != product_id
        or str(pred.get("decision", "")) != decision_id
        or bool(pred.get("closed"))
    ):
        raise ComparatorTargetNotFound("open prediction does not belong to product and decision")

    forecast = normalize_forecast_record(pred)
    plan = normalize_comparator_plan(pred)
    explicit_plan_id = str((execution or {}).get("plan_id") or "") or None
    if explicit_plan_id and explicit_plan_id != plan.get("plan_id"):
        raise ComparatorTargetNotFound("comparator plan does not belong to prediction")
    forecast_targets = {
        str((item.get("target") or {}).get("entity_id"))
        for item in (forecast.get("consequences") or [])
        if isinstance(item, dict) and (item.get("target") or {}).get("entity_id")
    }
    supplied_targets = {str(item.get("capability_id") or "") for item in measurements}
    if not supplied_targets or "" in supplied_targets or not supplied_targets.issubset(forecast_targets):
        raise ComparatorTargetNotFound("comparator measurement target does not belong to prediction")

    payload = {
        "decision_id": decision_id,
        "prediction_id": prediction_id,
        "request_id": request_id,
        "comparator_type": comparator_type,
        "design": design,
        "observed_at": str(observed_at),
        "measurements": measurements,
        "comparator_label": comparator_label,
        "window_start": str(window_start) if window_start is not None else None,
        "window_end": str(window_end) if window_end is not None else None,
        "evidence_refs": evidence_refs or [],
        "confounders": confounders or [],
        "missing_evidence": missing_evidence or [],
        "reason": reason,
        "content": content,
        "source_surface": source_surface,
        "actor_ref": actor_ref,
        "execution": execution or {},
    }
    fingerprint = _fingerprint(product_id, payload)
    key = _record_key(product_id, request_id)
    observation_id = f"observation:{key}"
    async with pool.connection() as db:
        existing = parse_one(await db.query("SELECT * FROM ONLY <record>$id", {"id": observation_id}))
    if existing:
        if existing.get("content_hash") != fingerprint:
            raise ComparatorRequestConflict("comparator request_id conflict")
        state = await _aggregate_comparator_state(pred, product_id, pool=pool)
        return {
            "status": "duplicate",
            "id": observation_id,
            "comparator": normalize_comparator_observation(existing),
            "comparator_state": state,
            "resolution_trigger": {"state": "already_recorded"},
        }

    contract = build_comparator_observation_contract(
        observation_id=observation_id,
        request_id=request_id,
        decision_id=decision_id,
        prediction_id=prediction_id,
        product_id=product_id,
        comparator_type=comparator_type,
        design=design,
        observed_at=observed_at,
        measurements=measurements,
        comparator_label=comparator_label,
        window_start=window_start,
        window_end=window_end,
        evidence_refs=evidence_refs,
        confounders=confounders,
        missing_evidence=missing_evidence,
        reason=reason,
        source_surface=source_surface,
        actor_ref=actor_ref,
    )
    alignment = evaluate_plan_alignment(
        plan=plan,
        observation_contract=contract,
        execution=execution,
        explicit_plan_id=explicit_plan_id,
    )
    contract["execution"] = {
        "plan_id": explicit_plan_id or alignment.get("plan_id"),
        "assignment_unit": str((execution or {}).get("assignment_unit") or "")[:240] or None,
        "allocation": str((execution or {}).get("allocation") or "")[:500] or None,
        "eligibility_criteria_met": (execution or {}).get("eligibility_criteria_met"),
        "guardrail_breaches": list((execution or {}).get("guardrail_breaches") or [])[:25],
        "declared_deviations": list((execution or {}).get("deviations") or [])[:25],
    }
    contract["plan_alignment"] = alignment
    contract["comparator"]["effective_attribution_strength"] = alignment["effective_attribution_strength"]
    async with pool.connection() as db:
        row = parse_one(
            await db.query(
                """UPSERT type::record('observation', $record_key) SET
                       product = <record>$product,
                       observation_type = 'forecast_comparator',
                       content = $content,
                       confidence = 1.0f,
                       source = 'api',
                       source_surface = $source_surface,
                       actor_ref = $actor_ref,
                       actor_class = 'authenticated_user',
                       content_hash = $content_hash,
                       affected_decision = <record>$decision,
                       affected_prediction = <record>$prediction,
                       comparator_contract_version = $contract_version,
                       comparator_contract = $contract,
                       comparator_type = $comparator_type,
                       comparator_design = $comparator_design,
                       comparator_resolution_eligible = $resolution_eligible,
                       comparator_idempotency_key = $request_id,
                       comparator_plan_id = $plan_id,
                       comparator_alignment_state = $alignment_state,
                       observed_at = <datetime>$observed_at,
                       status = 'processed',
                       processed_at = time::now(),
                       created_at = time::now()""",
                {
                    "record_key": key,
                    "product": product_id,
                    "content": content,
                    "source_surface": source_surface,
                    "actor_ref": actor_ref,
                    "content_hash": fingerprint,
                    "decision": decision_id,
                    "prediction": prediction_id,
                    "contract_version": COMPARATOR_OBSERVATION_CONTRACT_VERSION,
                    "contract": contract,
                    "comparator_type": comparator_type,
                    "comparator_design": design,
                    "resolution_eligible": contract["resolution_eligible"],
                    "request_id": request_id,
                    "plan_id": alignment.get("plan_id"),
                    "alignment_state": alignment.get("state"),
                    "observed_at": observed_at,
                },
            )
        )
    stored = row or {
        "id": observation_id,
        "product": product_id,
        "affected_decision": decision_id,
        "affected_prediction": prediction_id,
        "comparator_contract_version": COMPARATOR_OBSERVATION_CONTRACT_VERSION,
        "comparator_contract": contract,
    }
    state = await _aggregate_comparator_state(pred, product_id, pool=pool)
    try:
        from core.engine.foresight.reconciler import process_comparator_observation

        resolution_trigger = await process_comparator_observation(stored)
    except Exception as exc:
        resolution_trigger = {"state": "degraded", "reason": type(exc).__name__}
    return {
        "status": "captured",
        "id": observation_id,
        "comparator": normalize_comparator_observation(stored),
        "comparator_state": state,
        "resolution_trigger": resolution_trigger,
    }
