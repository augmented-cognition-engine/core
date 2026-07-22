"""Fail-closed ingestion of explicit, plan-linked metric samples.

Measurement Ingestion v1 supports one deliberately narrow adapter: structured metric samples
that already identify the frozen comparator plan, measurement run, target, arm, phase, window,
and observed value. ACE accumulates those samples and emits an ordinary Comparator Observation v1
only when the planned measurement matrix is complete and internally consistent. It never assigns
cohorts, operates a rollout, or infers comparator membership from generic quality history.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any

from core.engine.core.db import parse_one, parse_rows
from core.engine.core.db import pool as default_pool
from core.engine.foresight.contracts import (
    MEASUREMENT_INGESTION_VERSION,
    MEASUREMENT_OBSERVATION_CONTRACT_VERSION,
    _bounded_json,
    normalize_comparator_plan,
)

SUPPORTED_MEASUREMENT_SOURCES = frozenset({"structured_metric"})
MEASUREMENT_ARMS = frozenset({"intervention", "comparator"})
MEASUREMENT_PHASES = frozenset({"baseline", "outcome"})


class MeasurementTargetNotFound(ValueError):
    """The prediction, plan, product, decision, or planned target does not match."""


class MeasurementRequestConflict(ValueError):
    """A sample request ID was reused with different contents."""


def _text(value: object, limit: int = 1_000) -> str | None:
    if value is None:
        return None
    result = " ".join(str(value).split())
    return result[:limit] if result else None


def _refs(value: object, limit: int = 100) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for raw in value[:limit] if (item := _text(raw, 1_000))]


def _record_key(product_id: str, request_id: str) -> str:
    return hashlib.sha256(f"{product_id}|measurement|{request_id}".encode()).hexdigest()[:24]


def _fingerprint(product_id: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        {"product_id": product_id, "payload": payload},
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def _iso(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def build_measurement_observation_contract(
    *,
    observation_id: str,
    request_id: str,
    decision_id: str,
    prediction_id: str,
    product_id: str,
    plan_id: str,
    run_id: str,
    source_type: str,
    capability_id: str,
    metric: str,
    unit: str,
    arm: str,
    phase: str,
    value: float,
    measured_at: object,
    window_start: object,
    window_end: object,
    comparator_type: str,
    design: str,
    evidence_refs: list[str] | None,
    execution: dict | None,
    confounders: list[str] | None,
    source_surface: str,
    actor_ref: str,
) -> dict[str, Any]:
    """Build one bounded raw sample contract without interpreting it as an effect."""
    numeric = None
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        numeric = float(value)
    start = _iso(window_start)
    end = _iso(window_end)
    measured = _iso(measured_at)
    missing: list[str] = []
    if source_type not in SUPPORTED_MEASUREMENT_SOURCES:
        missing.append("source_type")
    if arm not in MEASUREMENT_ARMS:
        missing.append("arm")
    if phase not in MEASUREMENT_PHASES:
        missing.append("phase")
    if numeric is None:
        missing.append("value")
    if not measured:
        missing.append("measured_at")
    if not start or not end or (start and end and start > end):
        missing.append("observation_window")
    refs = _refs(evidence_refs)
    if not refs:
        missing.append("evidence_refs")
    execution = execution if isinstance(execution, dict) else {}
    return {
        "contract_version": MEASUREMENT_OBSERVATION_CONTRACT_VERSION,
        "observation_id": _text(observation_id, 240),
        "request_id": _text(request_id, 240),
        "decision_id": _text(decision_id, 240),
        "prediction_id": _text(prediction_id, 240),
        "product_id": _text(product_id, 240),
        "plan_id": _text(plan_id, 80),
        "run_id": _text(run_id, 240),
        "source": {"type": source_type, "mode": "explicit_arm_phase_sample"},
        "target": {
            "entity_id": _text(capability_id, 240),
            "metric": _text(metric, 160),
            "unit": _text(unit, 80),
        },
        "sample": {"arm": arm, "phase": phase, "value": numeric, "measured_at": measured},
        "observation_window": {"start": start, "end": end},
        "observed_comparator": {
            "type": _text(comparator_type, 80),
            "design": _text(design, 80),
            "causal_claim": False,
            "design_independently_verified": False,
        },
        "execution": {
            "plan_id": _text(execution.get("plan_id") or plan_id, 80),
            "assignment_unit": _text(execution.get("assignment_unit"), 240),
            "allocation": _text(execution.get("allocation"), 500),
            "eligibility_criteria_met": execution.get("eligibility_criteria_met")
            if isinstance(execution.get("eligibility_criteria_met"), bool)
            else None,
            "guardrail_breaches": _refs(execution.get("guardrail_breaches"), 25),
            "deviations": _refs(execution.get("deviations"), 25),
        },
        "evidence_refs": refs,
        "confounders": _refs(confounders, 50),
        "evidence_status": "raw_sample_not_effect",
        "resolution_eligible": False,
        "completeness": {
            "state": "complete" if not missing else "partial",
            "missing_fields": missing,
        },
        "provenance": {
            "source_surface": _text(source_surface, 80),
            "actor_ref": _text(actor_ref, 240),
        },
        "compatibility": {
            "state": "current",
            "reason": None,
            "stored_contract_version": MEASUREMENT_OBSERVATION_CONTRACT_VERSION,
        },
    }


def normalize_measurement_observation(record: dict | None) -> dict[str, Any]:
    """Project a current sample or an explicit degraded legacy placeholder."""
    record = record if isinstance(record, dict) else {}
    stored = record.get("measurement_contract")
    version = stored.get("contract_version") if isinstance(stored, dict) else record.get("measurement_contract_version")
    if not isinstance(stored, dict) or version != MEASUREMENT_OBSERVATION_CONTRACT_VERSION:
        return {
            "contract_version": MEASUREMENT_OBSERVATION_CONTRACT_VERSION,
            "observation_id": _text(record.get("id"), 240),
            "resolution_eligible": False,
            "evidence_status": "unusable_legacy_sample",
            "completeness": {"state": "partial", "missing_fields": ["measurement_contract"]},
            "compatibility": {
                "state": "degraded",
                "reason": "legacy_missing_measurement_contract"
                if not isinstance(stored, dict)
                else "unsupported_measurement_contract_version",
                "stored_contract_version": _text(version, 120),
            },
        }
    contract = _bounded_json(stored)
    if not isinstance(contract, dict):
        return normalize_measurement_observation(
            {key: value for key, value in record.items() if key != "measurement_contract"}
        )
    contract["observation_id"] = _text(record.get("id") or contract.get("observation_id"), 240)
    contract["resolution_eligible"] = False
    contract["compatibility"] = {
        "state": "current",
        "reason": None,
        "stored_contract_version": MEASUREMENT_OBSERVATION_CONTRACT_VERSION,
    }
    return contract


def assemble_measurement_ingestion(*, prediction_id: str, plan: dict, run_id: str, rows: list[dict]) -> dict[str, Any]:
    """Assemble a run receipt and comparator arguments, failing closed on every ambiguity."""
    samples = [normalize_measurement_observation(row) for row in rows]
    planned = {
        str((item.get("target") or {}).get("entity_id")): item.get("target") or {}
        for item in (plan.get("measurements") or [])
        if isinstance(item, dict) and (item.get("target") or {}).get("entity_id")
    }
    required_slots = [
        f"{target}|{arm}|{phase}"
        for target in sorted(planned)
        for arm in sorted(MEASUREMENT_ARMS)
        for phase in sorted(MEASUREMENT_PHASES)
    ]
    slots: dict[str, list[dict]] = {}
    conflicts: list[str] = []
    for sample in samples:
        target = sample.get("target") or {}
        point = sample.get("sample") or {}
        slot = f"{target.get('entity_id')}|{point.get('arm')}|{point.get('phase')}"
        slots.setdefault(slot, []).append(sample)
        planned_target = planned.get(str(target.get("entity_id")))
        if planned_target is None:
            conflicts.append(f"unplanned_target:{target.get('entity_id')}")
        elif target.get("metric") != planned_target.get("metric") or target.get("unit") != planned_target.get("unit"):
            conflicts.append(f"target_metric_or_unit_mismatch:{target.get('entity_id')}")
    for slot, items in slots.items():
        if len(items) > 1:
            conflicts.append(f"duplicate_slot:{slot}")

    missing_slots = [slot for slot in required_slots if len(slots.get(slot, [])) != 1]
    complete_samples = [slots[slot][0] for slot in required_slots if len(slots.get(slot, [])) == 1]
    invariant_fields = {
        "plan_id": {item.get("plan_id") for item in complete_samples},
        "run_id": {item.get("run_id") for item in complete_samples},
        "source_type": {(item.get("source") or {}).get("type") for item in complete_samples},
        "window_start": {(item.get("observation_window") or {}).get("start") for item in complete_samples},
        "window_end": {(item.get("observation_window") or {}).get("end") for item in complete_samples},
        "comparator_type": {(item.get("observed_comparator") or {}).get("type") for item in complete_samples},
        "design": {(item.get("observed_comparator") or {}).get("design") for item in complete_samples},
        "execution": {
            json.dumps(item.get("execution") or {}, sort_keys=True, separators=(",", ":")) for item in complete_samples
        },
    }
    for field, values in invariant_fields.items():
        if len(values) > 1:
            conflicts.append(f"inconsistent_run_metadata:{field}")
    planned_comparator = plan.get("comparator") or {}
    if invariant_fields["comparator_type"] and invariant_fields["comparator_type"] != {planned_comparator.get("type")}:
        conflicts.append("observed_comparator_type_does_not_match_plan")
    if invariant_fields["design"] and invariant_fields["design"] != {planned_comparator.get("assignment_design")}:
        conflicts.append("observed_design_does_not_match_plan")
    if invariant_fields["source_type"] and invariant_fields["source_type"] != {"structured_metric"}:
        conflicts.append("unsupported_measurement_source")
    incomplete_contracts = [
        str(item.get("request_id"))
        for item in complete_samples
        if (item.get("completeness") or {}).get("state") != "complete"
    ]
    if incomplete_contracts:
        conflicts.append("samples_missing_required_evidence")

    status = "conflicted" if conflicts else "collecting" if missing_slots else "ready"
    request_payload = f"{plan.get('plan_id')}|{run_id}"
    comparator_request_id = f"measurement_ingestion:{hashlib.sha256(request_payload.encode()).hexdigest()[:24]}"
    receipt: dict[str, Any] = {
        "contract_version": MEASUREMENT_INGESTION_VERSION,
        "prediction_id": prediction_id,
        "plan_id": plan.get("plan_id"),
        "run_id": run_id,
        "status": status,
        "supported_source": "structured_metric",
        "sample_count": len(samples),
        "required_sample_count": len(required_slots),
        "required_slots": required_slots,
        "missing_slots": missing_slots,
        "conflicts": list(dict.fromkeys(conflicts)),
        "comparator_request_id": comparator_request_id if status == "ready" else None,
        "authority": {
            "assigns_cohorts": False,
            "changes_rollout": False,
            "runs_experiment": False,
        },
        "compatibility": {
            "state": "current",
            "reason": None,
            "stored_contract_version": MEASUREMENT_INGESTION_VERSION,
        },
    }
    if status != "ready":
        return receipt

    first = complete_samples[0]
    measurements: list[dict[str, Any]] = []
    all_refs: set[str] = set()
    all_confounders: set[str] = set()
    for capability_id in sorted(planned):
        values: dict[tuple[str, str], float] = {}
        refs: set[str] = set()
        for arm in sorted(MEASUREMENT_ARMS):
            for phase in sorted(MEASUREMENT_PHASES):
                sample = slots[f"{capability_id}|{arm}|{phase}"][0]
                values[(arm, phase)] = float((sample.get("sample") or {})["value"])
                refs.update(sample.get("evidence_refs") or [])
                all_confounders.update(sample.get("confounders") or [])
        all_refs.update(refs)
        target = planned[capability_id]
        measurements.append(
            {
                "capability_id": capability_id,
                "metric": target.get("metric"),
                "unit": target.get("unit"),
                "intervention_before": values[("intervention", "baseline")],
                "intervention_after": values[("intervention", "outcome")],
                "comparator_before": values[("comparator", "baseline")],
                "comparator_after": values[("comparator", "outcome")],
                "evidence_refs": sorted(refs),
            }
        )
    observed = first.get("observed_comparator") or {}
    receipt["comparator_arguments"] = {
        "request_id": comparator_request_id,
        "comparator_type": observed.get("type"),
        "design": observed.get("design"),
        "observed_at": (first.get("observation_window") or {}).get("end"),
        "measurements": measurements,
        "comparator_label": (plan.get("comparator") or {}).get("label"),
        "window_start": (first.get("observation_window") or {}).get("start"),
        "window_end": (first.get("observation_window") or {}).get("end"),
        "evidence_refs": sorted(all_refs),
        "confounders": sorted(all_confounders),
        "missing_evidence": [],
        "reason": "Automatically assembled from explicit plan-linked structured metric samples.",
        "content": f"Measurement run {run_id} completed the frozen comparator plan matrix.",
        "source_surface": "measurement_ingestion",
        "actor_ref": "system:measurement-ingestion",
        "execution": first.get("execution") or {"plan_id": plan.get("plan_id")},
    }
    return receipt


async def _ingest_run(*, pred: dict, product_id: str, run_id: str, pool) -> dict[str, Any]:
    prediction_id = str(pred.get("id", ""))
    plan = normalize_comparator_plan(pred)
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT * FROM observation
                   WHERE product = <record>$product
                     AND observation_type = 'forecast_measurement'
                     AND affected_prediction = <record>$prediction
                     AND measurement_plan_id = $plan_id
                     AND measurement_run_id = $run_id
                   ORDER BY measured_at ASC, created_at ASC LIMIT 200""",
                {
                    "product": product_id,
                    "prediction": prediction_id,
                    "plan_id": plan.get("plan_id"),
                    "run_id": run_id,
                },
            )
        )
    receipt = assemble_measurement_ingestion(prediction_id=prediction_id, plan=plan, run_id=run_id, rows=rows)
    comparator_result = None
    if receipt["status"] == "ready":
        from core.engine.foresight.comparators import record_comparator_observation

        comparator_result = await record_comparator_observation(
            product_id=product_id,
            decision_id=str(pred.get("decision", "")),
            prediction_id=prediction_id,
            pool=pool,
            **receipt.pop("comparator_arguments"),
        )
        receipt["status"] = "ingested"
        receipt["comparator_observation_id"] = comparator_result.get("id")
        receipt["resolution_trigger"] = comparator_result.get("resolution_trigger")
    async with pool.connection() as db:
        await db.query(
            """UPDATE <record>$prediction SET
                   measurement_ingestion_version = $version,
                   measurement_ingestion_state = $state,
                   measurement_ingestion_status = $status,
                   measurement_ingestion_updated_at = time::now()
               WHERE product = <record>$product""",
            {
                "prediction": prediction_id,
                "product": product_id,
                "version": MEASUREMENT_INGESTION_VERSION,
                "state": receipt,
                "status": receipt["status"],
            },
        )
        await db.query(
            """UPDATE observation SET
                   measurement_ingestion_status = $status,
                   measurement_comparator_observation = IF $comparator THEN <record>$comparator ELSE NONE END
               WHERE product = <record>$product
                 AND observation_type = 'forecast_measurement'
                 AND affected_prediction = <record>$prediction
                 AND measurement_plan_id = $plan_id
                 AND measurement_run_id = $run_id""",
            {
                "product": product_id,
                "prediction": prediction_id,
                "plan_id": plan.get("plan_id"),
                "run_id": run_id,
                "status": receipt["status"],
                "comparator": receipt.get("comparator_observation_id"),
            },
        )
    receipt["comparator"] = comparator_result.get("comparator") if comparator_result else None
    return receipt


async def record_measurement_observation(
    *,
    product_id: str,
    decision_id: str,
    prediction_id: str,
    request_id: str,
    plan_id: str,
    run_id: str,
    source_type: str,
    capability_id: str,
    metric: str,
    unit: str,
    arm: str,
    phase: str,
    value: float,
    measured_at: object,
    window_start: object,
    window_end: object,
    comparator_type: str,
    design: str,
    evidence_refs: list[str] | None,
    execution: dict | None,
    confounders: list[str] | None,
    content: str,
    source_surface: str,
    actor_ref: str,
    pool=None,
) -> dict[str, Any]:
    """Persist one raw sample, then automatically attempt fail-closed run assembly."""
    pool = pool or default_pool
    async with pool.connection() as db:
        pred = parse_one(await db.query("SELECT * FROM ONLY <record>$prediction", {"prediction": prediction_id}))
    if not pred or str(pred.get("product", "")) != product_id or str(pred.get("decision", "")) != decision_id:
        raise MeasurementTargetNotFound("prediction does not belong to product and decision")
    plan = normalize_comparator_plan(pred)
    if not plan_id or plan_id != plan.get("plan_id") or plan.get("status") == "not_proposed":
        raise MeasurementTargetNotFound("measurement plan does not belong to prediction")
    execution_plan_id = str((execution or {}).get("plan_id") or "")
    if execution_plan_id and execution_plan_id != plan_id:
        raise MeasurementTargetNotFound("execution plan does not match measurement plan")
    planned_target = next(
        (
            item.get("target") or {}
            for item in (plan.get("measurements") or [])
            if isinstance(item, dict) and str((item.get("target") or {}).get("entity_id")) == capability_id
        ),
        None,
    )
    if not planned_target or planned_target.get("metric") != metric or planned_target.get("unit") != unit:
        raise MeasurementTargetNotFound("sample target, metric, or unit is not in the frozen plan")

    payload = {
        "decision_id": decision_id,
        "prediction_id": prediction_id,
        "request_id": request_id,
        "plan_id": plan_id,
        "run_id": run_id,
        "source_type": source_type,
        "capability_id": capability_id,
        "metric": metric,
        "unit": unit,
        "arm": arm,
        "phase": phase,
        "value": value,
        "measured_at": str(measured_at),
        "window_start": str(window_start),
        "window_end": str(window_end),
        "comparator_type": comparator_type,
        "design": design,
        "evidence_refs": evidence_refs or [],
        "execution": execution or {},
        "confounders": confounders or [],
        "content": content,
        "source_surface": source_surface,
        "actor_ref": actor_ref,
    }
    fingerprint = _fingerprint(product_id, payload)
    key = _record_key(product_id, request_id)
    observation_id = f"observation:{key}"
    async with pool.connection() as db:
        existing = parse_one(await db.query("SELECT * FROM ONLY <record>$id", {"id": observation_id}))
    if existing:
        if existing.get("content_hash") != fingerprint:
            raise MeasurementRequestConflict("measurement request_id conflict")
        if bool(pred.get("closed")):
            stored_receipt = pred.get("measurement_ingestion_state")
            receipt = (
                stored_receipt
                if isinstance(stored_receipt, dict)
                and stored_receipt.get("run_id") == run_id
                and stored_receipt.get("plan_id") == plan_id
                else {
                    "contract_version": MEASUREMENT_INGESTION_VERSION,
                    "prediction_id": prediction_id,
                    "plan_id": plan_id,
                    "run_id": run_id,
                    "status": "already_recorded",
                    "authority": {
                        "assigns_cohorts": False,
                        "changes_rollout": False,
                        "runs_experiment": False,
                    },
                }
            )
        else:
            receipt = await _ingest_run(pred=pred, product_id=product_id, run_id=run_id, pool=pool)
        return {
            "status": "duplicate",
            "id": observation_id,
            "measurement": normalize_measurement_observation(existing),
            "ingestion": receipt,
        }

    if bool(pred.get("closed")):
        raise MeasurementTargetNotFound("closed prediction cannot accept a new measurement sample")

    contract = build_measurement_observation_contract(
        observation_id=observation_id,
        request_id=request_id,
        decision_id=decision_id,
        prediction_id=prediction_id,
        product_id=product_id,
        plan_id=plan_id,
        run_id=run_id,
        source_type=source_type,
        capability_id=capability_id,
        metric=metric,
        unit=unit,
        arm=arm,
        phase=phase,
        value=value,
        measured_at=measured_at,
        window_start=window_start,
        window_end=window_end,
        comparator_type=comparator_type,
        design=design,
        evidence_refs=evidence_refs,
        execution=execution,
        confounders=confounders,
        source_surface=source_surface,
        actor_ref=actor_ref,
    )
    slot = f"{capability_id}|{arm}|{phase}"
    async with pool.connection() as db:
        row = parse_one(
            await db.query(
                """UPSERT type::record('observation', $record_key) SET
                       product = <record>$product,
                       observation_type = 'forecast_measurement',
                       content = $content,
                       confidence = 1.0f,
                       source = 'api',
                       source_surface = $source_surface,
                       actor_ref = $actor_ref,
                       actor_class = 'authenticated_user',
                       content_hash = $content_hash,
                       affected_decision = <record>$decision,
                       affected_prediction = <record>$prediction,
                       measurement_contract_version = $contract_version,
                       measurement_contract = $contract,
                       measurement_source_type = $source_type,
                       measurement_plan_id = $plan_id,
                       measurement_run_id = $run_id,
                       measurement_slot = $slot,
                       measurement_idempotency_key = $request_id,
                       measured_at = <datetime>$measured_at,
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
                    "contract_version": MEASUREMENT_OBSERVATION_CONTRACT_VERSION,
                    "contract": contract,
                    "source_type": source_type,
                    "plan_id": plan_id,
                    "run_id": run_id,
                    "slot": slot,
                    "request_id": request_id,
                    "measured_at": measured_at,
                },
            )
        )
    stored = row or {
        "id": observation_id,
        "measurement_contract_version": MEASUREMENT_OBSERVATION_CONTRACT_VERSION,
        "measurement_contract": contract,
    }
    receipt = await _ingest_run(pred=pred, product_id=product_id, run_id=run_id, pool=pool)
    return {
        "status": "captured",
        "id": observation_id,
        "measurement": normalize_measurement_observation(stored),
        "ingestion": receipt,
    }
