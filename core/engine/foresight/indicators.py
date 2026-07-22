"""Active, evidence-bearing evaluation of forecast leading indicators.

Only explicit machine-resolvable rules are evaluated automatically. Prose-only indicators remain
manual and are surfaced as such; ACE never converts fuzzy text into an invented measurement rule.
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
    INDICATOR_EFFECTS,
    INDICATOR_OBSERVATION_CONTRACT_VERSION,
    INDICATOR_OPERATORS,
    INDICATOR_STATE_VERSION,
    build_indicator_observation_contract,
    normalize_forecast_record,
    normalize_indicator_observation,
)


class IndicatorTargetNotFound(ValueError):
    """The prediction, decision, product, or indicator identity does not match."""


class IndicatorRequestConflict(ValueError):
    """A request ID was reused with different indicator evidence."""


def _record_key(product_id: str, request_id: str) -> str:
    return hashlib.sha256(f"{product_id}|indicator|{request_id}".encode()).hexdigest()[:24]


def _fingerprint(product_id: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        {"product_id": product_id, "payload": payload},
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def _indicator_catalog(forecast: dict) -> list[dict]:
    rule = forecast.get("resolution_rule")
    indicators = rule.get("indicators") if isinstance(rule, dict) else None
    return [item for item in (indicators or []) if isinstance(item, dict)]


def _baseline_value(forecast: dict, rule: dict) -> float | None:
    baseline = forecast.get("baseline")
    state = baseline.get("current_state") if isinstance(baseline, dict) else None
    capability_id = str(rule.get("capability_id") or "")
    if not isinstance(state, dict) or capability_id not in state:
        return None
    capability_state = state.get(capability_id)
    if isinstance(capability_state, dict):
        dimension = rule.get("dimension")
        candidate = capability_state.get(dimension) if dimension else capability_state.get("overall")
        if candidate is None and len(capability_state) == 1:
            candidate = next(iter(capability_state.values()))
    else:
        candidate = capability_state
    try:
        value = float(candidate)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def evaluate_rule(rule: dict, value: object, baseline_value: object = None) -> tuple[str, str]:
    """Evaluate one frozen rule, returning effect and a bounded machine-readable reason."""
    operator = rule.get("operator")
    if operator not in INDICATOR_OPERATORS:
        return "inconclusive", "unsupported_operator"
    try:
        observed = float(value)
        threshold = float(rule.get("threshold"))
    except (TypeError, ValueError):
        return "inconclusive", "missing_numeric_measurement"
    if not math.isfinite(observed) or not math.isfinite(threshold):
        return "inconclusive", "non_finite_measurement"

    compared = observed
    if operator.startswith("delta_"):
        try:
            baseline = float(baseline_value)
        except (TypeError, ValueError):
            return "inconclusive", "missing_baseline"
        if not math.isfinite(baseline):
            return "inconclusive", "missing_baseline"
        compared = observed - baseline

    met = compared >= threshold if operator in {"gte", "delta_gte"} else compared <= threshold
    effect_key = "effect_when_met" if met else "effect_when_not_met"
    effect = rule.get(effect_key, "inconclusive")
    if effect not in INDICATOR_EFFECTS:
        effect = "inconclusive"
    return effect, "rule_met" if met else "rule_not_met"


def _indicator_state(prediction_id: str, forecast: dict, observations: list[dict]) -> dict[str, Any]:
    latest: dict[str, dict] = {}
    for row in observations:
        contract = normalize_indicator_observation(row)
        indicator_id = str(contract.get("indicator_id") or "")
        if indicator_id and indicator_id not in latest:
            latest[indicator_id] = contract

    effects = {item.get("effect") for item in latest.values()} - {None, "inconclusive"}
    if "falsifies" in effects:
        overall = "falsifies"
    elif "supports" in effects and "weakens" in effects:
        overall = "mixed"
    elif "weakens" in effects:
        overall = "weakens"
    elif "supports" in effects:
        overall = "supports"
    elif latest:
        overall = "inconclusive"
    else:
        overall = "unobserved"

    catalog_ids = [str(item.get("local_id")) for item in _indicator_catalog(forecast) if item.get("local_id")]
    missing = [indicator_id for indicator_id in catalog_ids if indicator_id not in latest]
    refs = [str(item.get("observation_id")) for item in latest.values() if item.get("observation_id")]
    return {
        "contract_version": INDICATOR_STATE_VERSION,
        "prediction_id": prediction_id,
        "overall_state": overall,
        "latest_by_indicator": latest,
        "observation_refs": refs,
        "missing_indicator_ids": missing,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "completeness": {
            "state": "complete" if catalog_ids and not missing else "partial",
            "missing_fields": [f"indicator:{item}" for item in missing]
            + ([] if catalog_ids else ["forecast.resolution_rule.indicators"]),
        },
        "compatibility": {
            "state": "current",
            "reason": None,
            "stored_contract_version": INDICATOR_STATE_VERSION,
        },
    }


async def _aggregate_indicator_state(pred: dict, product_id: str, *, pool) -> dict[str, Any]:
    prediction_id = str(pred.get("id", ""))
    forecast = normalize_forecast_record(pred)
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT * FROM observation
                   WHERE product = <record>$product
                     AND observation_type = 'forecast_indicator'
                     AND affected_prediction = <record>$prediction
                   ORDER BY observed_at DESC, created_at DESC LIMIT 200""",
                {"product": product_id, "prediction": prediction_id},
            )
        )
    state = _indicator_state(prediction_id, forecast, rows)
    async with pool.connection() as db:
        await db.query(
            """UPDATE <record>$prediction SET
                   indicator_state_version = $state_version,
                   indicator_evidence_state = $state,
                   indicator_status = $status,
                   indicator_updated_at = time::now()
               WHERE product = <record>$product""",
            {
                "prediction": prediction_id,
                "product": product_id,
                "state_version": INDICATOR_STATE_VERSION,
                "state": state,
                "status": state["overall_state"],
            },
        )
    return state


async def record_indicator_observation(
    *,
    product_id: str,
    decision_id: str,
    prediction_id: str,
    request_id: str,
    indicator_id: str,
    effect: str,
    observed_at: object,
    value: object,
    unit: str | None,
    evidence_refs: list[str] | None,
    reason: str | None,
    content: str,
    source_kind: str,
    source_surface: str,
    actor_ref: str,
    baseline_value: object = None,
    rule: dict | None = None,
    pool=None,
) -> dict[str, Any]:
    """Idempotently persist indicator evidence and refresh operational indicator state."""
    pool = pool or default_pool
    if effect not in INDICATOR_EFFECTS:
        raise ValueError(f"unsupported indicator effect: {effect}")
    async with pool.connection() as db:
        pred = parse_one(await db.query("SELECT * FROM ONLY <record>$prediction", {"prediction": prediction_id}))
    if (
        not pred
        or str(pred.get("product", "")) != product_id
        or str(pred.get("decision", "")) != decision_id
        or bool(pred.get("closed"))
    ):
        raise IndicatorTargetNotFound("open prediction does not belong to product and decision")
    forecast = normalize_forecast_record(pred)
    indicator = next(
        (item for item in _indicator_catalog(forecast) if item.get("local_id") == indicator_id),
        None,
    )
    if indicator is None:
        raise IndicatorTargetNotFound("indicator does not belong to prediction")

    payload = {
        "decision_id": decision_id,
        "prediction_id": prediction_id,
        "request_id": request_id,
        "indicator_id": indicator_id,
        "effect": effect,
        "observed_at": str(observed_at),
        "value": value,
        "unit": unit,
        "baseline_value": baseline_value,
        "rule": rule,
        "evidence_refs": evidence_refs or [],
        "reason": reason,
        "content": content,
        "source_kind": source_kind,
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
            raise IndicatorRequestConflict("indicator request_id conflict")
        state = await _aggregate_indicator_state(pred, product_id, pool=pool)
        return {
            "status": "duplicate",
            "id": observation_id,
            "indicator": normalize_indicator_observation(existing),
            "indicator_state": state,
        }

    async with pool.connection() as db:
        contract = build_indicator_observation_contract(
            observation_id=observation_id,
            request_id=request_id,
            decision_id=decision_id,
            prediction_id=prediction_id,
            product_id=product_id,
            indicator_id=indicator_id,
            indicator_description=str(indicator.get("description") or ""),
            effect=effect,
            observed_at=observed_at,
            value=value,
            unit=unit,
            baseline_value=baseline_value,
            rule=rule,
            evidence_refs=evidence_refs,
            reason=reason,
            source_kind=source_kind,
            source_surface=source_surface,
            actor_ref=actor_ref,
        )
        row = parse_one(
            await db.query(
                """UPSERT type::record('observation', $record_key) SET
                       product = <record>$product,
                       observation_type = 'forecast_indicator',
                       content = $content,
                       confidence = 1.0f,
                       source = $source_kind,
                       source_surface = $source_surface,
                       actor_ref = $actor_ref,
                       actor_class = $actor_class,
                       content_hash = $content_hash,
                       affected_decision = <record>$decision,
                       affected_prediction = <record>$prediction,
                       indicator_contract_version = $contract_version,
                       indicator_contract = $contract,
                       indicator_local_id = $indicator_id,
                       indicator_effect = $effect,
                       indicator_idempotency_key = $request_id,
                       observed_at = <datetime>$observed_at,
                       status = 'processed',
                       processed_at = time::now(),
                       created_at = time::now()""",
                {
                    "record_key": key,
                    "product": product_id,
                    "content": content,
                    "source_kind": source_kind,
                    "source_surface": source_surface,
                    "actor_ref": actor_ref,
                    "actor_class": "ace_system" if source_kind == "automatic_quality_rule" else "authenticated_user",
                    "content_hash": fingerprint,
                    "decision": decision_id,
                    "prediction": prediction_id,
                    "contract_version": INDICATOR_OBSERVATION_CONTRACT_VERSION,
                    "contract": contract,
                    "indicator_id": indicator_id,
                    "effect": effect,
                    "request_id": request_id,
                    "observed_at": observed_at,
                },
            )
        )

    stored = row or {
        "id": observation_id,
        "product": product_id,
        "affected_decision": decision_id,
        "affected_prediction": prediction_id,
        "indicator_contract_version": INDICATOR_OBSERVATION_CONTRACT_VERSION,
        "indicator_contract": contract,
    }
    state = await _aggregate_indicator_state(pred, product_id, pool=pool)
    return {
        "status": "captured",
        "id": observation_id,
        "indicator": normalize_indicator_observation(stored),
        "indicator_state": state,
    }


async def evaluate_indicator_rules_for_prediction(pred: dict, product_id: str, *, pool=None) -> list[dict]:
    """Evaluate all automatic quality rules for one open prediction."""
    pool = pool or default_pool
    forecast = normalize_forecast_record(pred)
    results: list[dict] = []
    for indicator in _indicator_catalog(forecast):
        rule = indicator.get("rule")
        if indicator.get("monitoring") != "automatic" or not isinstance(rule, dict):
            continue
        capability_id = str(rule.get("capability_id") or "")
        dimension = rule.get("dimension")
        if dimension:
            query = """SELECT id, score, assessed_at, dimension FROM capability_quality
                       WHERE product = <record>$product
                         AND capability IN (
                             SELECT VALUE id FROM capability
                             WHERE product = <record>$product AND slug = <string>$capability
                         )
                         AND dimension = <string>$dimension
                       ORDER BY assessed_at DESC LIMIT 1"""
        else:
            query = """SELECT id, score, assessed_at, dimension FROM capability_quality
                       WHERE product = <record>$product
                         AND capability IN (
                             SELECT VALUE id FROM capability
                             WHERE product = <record>$product AND slug = <string>$capability
                         )
                       ORDER BY assessed_at DESC LIMIT 1"""
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    query,
                    {"product": product_id, "capability": capability_id, "dimension": dimension},
                )
            )
        if not rows:
            continue
        quality = rows[0]
        baseline = _baseline_value(forecast, rule)
        effect, reason = evaluate_rule(rule, quality.get("score"), baseline)
        evidence_ref = str(quality.get("id") or "")
        assessed_at = quality.get("assessed_at") or datetime.now(timezone.utc)
        request_id = "|".join(
            [
                "auto-quality",
                str(pred.get("id", "")),
                str(indicator.get("local_id", "")),
                evidence_ref,
                str(assessed_at),
            ]
        )
        results.append(
            await record_indicator_observation(
                product_id=product_id,
                decision_id=str(pred.get("decision", "")),
                prediction_id=str(pred.get("id", "")),
                request_id=request_id,
                indicator_id=str(indicator.get("local_id", "")),
                effect=effect,
                observed_at=assessed_at,
                value=quality.get("score"),
                unit="capability_quality_score",
                baseline_value=baseline,
                rule=rule,
                evidence_refs=[evidence_ref] if evidence_ref else [],
                reason=reason,
                content=f"Automatic indicator evaluation: {indicator.get('description', '')}",
                source_kind="automatic_quality_rule",
                source_surface="sentinel",
                actor_ref="ace:indicator_evaluator",
                pool=pool,
            )
        )
    return results
