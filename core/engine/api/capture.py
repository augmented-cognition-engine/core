# engine/api/capture.py
import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Literal

import jwt
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, Field, field_validator, model_validator

from core.engine.capture.pipeline import CapturePipeline
from core.engine.capture.watchers import SessionImportWatcher, StreamEvent
from core.engine.core.auth import get_current_user
from core.engine.core.config import settings
from core.engine.core.db import parse_one, pool
from core.engine.core.tasks import logged_task
from core.engine.foresight.contracts import (
    INTERVENTION_OBSERVATION_CONTRACT_VERSION,
    build_intervention_observation_contract,
    normalize_forecast_record,
    normalize_intervention_observation,
)
from core.engine.product.correction_receipts import effective_correction_lifecycle

router = APIRouter(tags=["capture"])


_VALID_OBSERVATION_TYPES = frozenset(
    {
        "correction",
        "decision",
        "preference",
        "pattern",
        "learning",
        "error",
        "discovery",
        "convention",
        "session_summary",
        "feedback",
        "user_declaration",
        "failure",
        "intervention",
        "forecast_indicator",
        "forecast_comparator",
        "forecast_measurement",
    }
)


class InterventionConditionObservation(BaseModel):
    condition: str = Field(..., min_length=1, max_length=1_000)
    met: bool | None = None
    evidence_refs: list[str] = Field(default_factory=list, max_length=25)


class InterventionExposure(BaseModel):
    degree: float | None = Field(default=None, ge=0.0, le=1.0)
    scope: str | None = Field(default=None, max_length=1_000)
    unit: str | None = Field(default=None, max_length=120)


class InterventionObservationCreate(BaseModel):
    request_id: str = Field(..., min_length=1, max_length=240)
    decision_id: str = Field(..., min_length=1, max_length=240)
    prediction_id: str = Field(..., min_length=1, max_length=240)
    status: Literal["started", "partial", "completed", "cancelled", "unknown"]
    observed_at: datetime | None = None
    applicability_conditions_met: bool | None = None
    conditions: list[InterventionConditionObservation] = Field(default_factory=list, max_length=50)
    exposure: InterventionExposure | None = None
    evidence_refs: list[str] = Field(default_factory=list, max_length=100)
    confounders: list[str] = Field(default_factory=list, max_length=50)
    missing_evidence: list[str] = Field(default_factory=list, max_length=50)
    reason: str | None = Field(default=None, max_length=2_000)

    @model_validator(mode="after")
    def validate_applicability_summary(self):
        observed = [condition.met for condition in self.conditions if condition.met is not None]
        derived = False if False in observed else True if observed and len(observed) == len(self.conditions) else None
        if (
            self.applicability_conditions_met is not None
            and derived is not None
            and self.applicability_conditions_met is not derived
        ):
            raise ValueError("applicability_conditions_met conflicts with condition observations")
        if self.applicability_conditions_met is None and derived is not None:
            self.applicability_conditions_met = derived
        return self


class ForecastIndicatorObservationCreate(BaseModel):
    request_id: str = Field(..., min_length=1, max_length=240)
    decision_id: str = Field(..., min_length=1, max_length=240)
    prediction_id: str = Field(..., min_length=1, max_length=240)
    indicator_id: str = Field(..., pattern=r"^indicator:[1-9][0-9]*$", max_length=120)
    effect: Literal["supports", "weakens", "falsifies", "inconclusive"]
    observed_at: datetime | None = None
    value: float | None = None
    unit: str | None = Field(default=None, max_length=120)
    evidence_refs: list[str] = Field(default_factory=list, max_length=100)
    reason: str | None = Field(default=None, max_length=2_000)


class ComparatorMeasurementCreate(BaseModel):
    capability_id: str = Field(..., min_length=1, max_length=240)
    metric: str = Field(default="capability_quality", min_length=1, max_length=160)
    unit: str = Field(default="score_delta", min_length=1, max_length=80)
    intervention_before: float
    intervention_after: float
    comparator_before: float
    comparator_after: float
    evidence_refs: list[str] = Field(default_factory=list, max_length=50)


class ComparatorExecutionCreate(BaseModel):
    plan_id: str | None = Field(default=None, pattern=r"^comparator_plan:[a-f0-9]{24}$", max_length=40)
    assignment_unit: str | None = Field(default=None, max_length=240)
    allocation: str | None = Field(default=None, max_length=500)
    eligibility_criteria_met: bool | None = None
    guardrail_breaches: list[str] = Field(default_factory=list, max_length=25)
    deviations: list[str] = Field(default_factory=list, max_length=25)


class ComparatorObservationCreate(BaseModel):
    request_id: str = Field(..., min_length=1, max_length=240)
    decision_id: str = Field(..., min_length=1, max_length=240)
    prediction_id: str = Field(..., min_length=1, max_length=240)
    comparator_type: Literal["no_action", "holdout", "phased_rollout", "alternative_intervention"]
    design: Literal["randomized", "matched", "quasi_experimental", "observational", "unknown"]
    comparator_label: str | None = Field(default=None, max_length=500)
    observed_at: datetime | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    measurements: list[ComparatorMeasurementCreate] = Field(..., min_length=1, max_length=25)
    evidence_refs: list[str] = Field(default_factory=list, max_length=100)
    confounders: list[str] = Field(default_factory=list, max_length=50)
    missing_evidence: list[str] = Field(default_factory=list, max_length=50)
    reason: str | None = Field(default=None, max_length=2_000)
    execution: ComparatorExecutionCreate | None = None

    @model_validator(mode="after")
    def validate_window(self):
        if self.window_start and self.window_end and self.window_start > self.window_end:
            raise ValueError("window_start must not be after window_end")
        return self


class ForecastMeasurementCreate(BaseModel):
    request_id: str = Field(..., min_length=1, max_length=240)
    decision_id: str = Field(..., min_length=1, max_length=240)
    prediction_id: str = Field(..., min_length=1, max_length=240)
    plan_id: str = Field(..., pattern=r"^comparator_plan:[a-f0-9]{24}$", max_length=40)
    run_id: str = Field(..., min_length=1, max_length=240)
    source_type: Literal["structured_metric"] = "structured_metric"
    capability_id: str = Field(..., min_length=1, max_length=240)
    metric: str = Field(..., min_length=1, max_length=160)
    unit: str = Field(..., min_length=1, max_length=80)
    arm: Literal["intervention", "comparator"]
    phase: Literal["baseline", "outcome"]
    value: float
    measured_at: datetime
    window_start: datetime
    window_end: datetime
    comparator_type: Literal["no_action", "holdout", "phased_rollout", "alternative_intervention"]
    design: Literal["randomized", "matched", "quasi_experimental", "observational", "unknown"]
    evidence_refs: list[str] = Field(default_factory=list, max_length=100)
    confounders: list[str] = Field(default_factory=list, max_length=50)
    execution: ComparatorExecutionCreate | None = None

    @model_validator(mode="after")
    def validate_measurement_window(self):
        if self.window_start > self.window_end:
            raise ValueError("window_start must not be after window_end")
        if self.execution and self.execution.plan_id and self.execution.plan_id != self.plan_id:
            raise ValueError("execution plan_id must match plan_id")
        return self


class ObservationCreate(BaseModel):
    observation_type: str = Field(..., description="Observation classification type")
    content: str = Field(..., min_length=1, max_length=10_000, description="Observation text")
    domain_path: str = Field(default="", max_length=500)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    affected_decision_id: str | None = Field(default=None, max_length=200)
    affected_task_id: str | None = Field(default=None, max_length=200)
    source_surface: Literal["api", "cli", "thin_mcp", "capture", "other"] = "api"
    lifecycle_state: Literal["active", "superseded", "invalidated", "contested"] = "active"
    supersedes_correction_id: str | None = Field(default=None, max_length=200)
    invalidates_correction_id: str | None = Field(default=None, max_length=200)
    contests_correction_id: str | None = Field(default=None, max_length=200)
    expires_at: datetime | None = None
    intervention: InterventionObservationCreate | None = None
    indicator: ForecastIndicatorObservationCreate | None = None
    comparator: ComparatorObservationCreate | None = None
    measurement: ForecastMeasurementCreate | None = None

    @field_validator("observation_type")
    @classmethod
    def validate_observation_type(cls, v: str) -> str:
        if v not in _VALID_OBSERVATION_TYPES:
            raise ValueError(f"observation_type must be one of: {', '.join(sorted(_VALID_OBSERVATION_TYPES))}")
        return v

    @field_validator("content")
    @classmethod
    def strip_content(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("content must not be blank")
        return stripped

    @model_validator(mode="after")
    def validate_correction_links(self):
        link_values = (
            self.affected_decision_id,
            self.affected_task_id,
            self.supersedes_correction_id,
            self.invalidates_correction_id,
            self.contests_correction_id,
        )
        if self.observation_type != "correction" and any(link_values):
            raise ValueError("decision, task, and correction links are only valid for correction observations")
        if self.observation_type != "correction" and self.expires_at is not None:
            raise ValueError("expiry is only valid for correction observations")
        if self.observation_type == "intervention" and self.intervention is None:
            raise ValueError("intervention payload is required for intervention observations")
        if self.observation_type != "intervention" and self.intervention is not None:
            raise ValueError("intervention payload is only valid for intervention observations")
        if self.observation_type == "forecast_indicator" and self.indicator is None:
            raise ValueError("indicator payload is required for forecast_indicator observations")
        if self.observation_type != "forecast_indicator" and self.indicator is not None:
            raise ValueError("indicator payload is only valid for forecast_indicator observations")
        if self.observation_type == "forecast_comparator" and self.comparator is None:
            raise ValueError("comparator payload is required for forecast_comparator observations")
        if self.observation_type != "forecast_comparator" and self.comparator is not None:
            raise ValueError("comparator payload is only valid for forecast_comparator observations")
        if self.observation_type == "forecast_measurement" and self.measurement is None:
            raise ValueError("measurement payload is required for forecast_measurement observations")
        if self.observation_type != "forecast_measurement" and self.measurement is not None:
            raise ValueError("measurement payload is only valid for forecast_measurement observations")
        transitions = (
            self.supersedes_correction_id,
            self.invalidates_correction_id,
            self.contests_correction_id,
        )
        if sum(value is not None for value in transitions) > 1:
            raise ValueError("a correction can supersede, invalidate, or contest only one prior correction")
        return self


async def _require_owned_target(db, record_id: str, prefix: str, product_id: str) -> dict:
    if not record_id.startswith(f"{prefix}:"):
        raise HTTPException(status_code=404, detail="Not found")
    row = parse_one(await db.query("SELECT * FROM ONLY <record>$id", {"id": record_id}))
    if not row or str(row.get("product", "")) != str(product_id):
        raise HTTPException(status_code=404, detail="Not found")
    if prefix == "observation" and row.get("observation_type") != "correction":
        raise HTTPException(status_code=404, detail="Not found")
    return row


async def _create_intervention_observation(body: ObservationCreate, user: dict, product_id: str) -> dict:
    """Persist one idempotent intervention observation and trigger evidence-gated resolution."""
    intervention = body.intervention
    if intervention is None:  # Pydantic enforces this; retain a fail-closed service boundary.
        raise HTTPException(status_code=422, detail="intervention payload is required")

    payload = body.model_dump(mode="json", exclude_none=True)
    request_fingerprint = hashlib.sha256(
        json.dumps({"product_id": product_id, "payload": payload}, sort_keys=True).encode("utf-8")
    ).hexdigest()
    record_key = hashlib.sha256(f"{product_id}|{intervention.request_id}".encode("utf-8")).hexdigest()[:24]
    observation_id = f"observation:{record_key}"
    observed_at = intervention.observed_at or datetime.now(timezone.utc)
    actor_ref = str(user.get("sub") or "authenticated_user")[:200]
    conditions = [condition.model_dump(mode="json") for condition in intervention.conditions]
    exposure = intervention.exposure.model_dump(mode="json") if intervention.exposure else None
    async with pool.connection() as db:
        decision = await _require_owned_target(db, intervention.decision_id, "decision", product_id)
        prediction = await _require_owned_target(db, intervention.prediction_id, "decision_prediction", product_id)
        if str(prediction.get("decision", "")) != str(decision.get("id", intervention.decision_id)):
            raise HTTPException(status_code=404, detail="Not found")

        existing = parse_one(await db.query("SELECT * FROM ONLY <record>$id", {"id": observation_id}))
        if existing:
            if existing.get("content_hash") != request_fingerprint:
                raise HTTPException(status_code=409, detail="intervention request_id conflict")
            return {
                "status": "duplicate",
                "id": observation_id,
                "intervention": normalize_intervention_observation(existing),
                "resolution_trigger": {"state": "already_recorded"},
            }

        missing_evidence = list(intervention.missing_evidence)
        forecast = normalize_forecast_record(prediction)
        forecast_conditions = list((forecast.get("intervention") or {}).get("conditions") or [])
        observed_conditions = {condition.condition for condition in intervention.conditions}
        for index, expected in enumerate(forecast_conditions):
            if expected not in observed_conditions:
                missing_evidence.append(f"forecast_applicability_condition:{index}:unobserved")
        contract = build_intervention_observation_contract(
            observation_id=observation_id,
            request_id=intervention.request_id,
            decision_id=intervention.decision_id,
            prediction_id=intervention.prediction_id,
            product_id=product_id,
            status=intervention.status,
            observed_at=observed_at,
            applicability_conditions_met=intervention.applicability_conditions_met,
            conditions=conditions,
            exposure=exposure,
            evidence_refs=intervention.evidence_refs,
            confounders=intervention.confounders,
            missing_evidence=missing_evidence,
            reason=intervention.reason,
            source_surface=body.source_surface,
            actor_ref=actor_ref,
        )

        row = parse_one(
            await db.query(
                """
                UPSERT type::record('observation', $record_key) SET
                    product = <record>$product,
                    observation_type = 'intervention',
                    content = $content,
                    domain_path = $domain_path,
                    domain_hint = $domain_path,
                    discipline_hint = $domain_path,
                    confidence = $confidence,
                    source = 'api',
                    source_surface = $source_surface,
                    actor_ref = $actor_ref,
                    actor_class = 'authenticated_user',
                    content_hash = $content_hash,
                    affected_decision = <record>$decision,
                    affected_prediction = <record>$prediction,
                    intervention_contract_version = $contract_version,
                    intervention_contract = $contract,
                    intervention_status = $intervention_status,
                    intervention_idempotency_key = $request_id,
                    applicability_conditions_met = $applicability_conditions_met,
                    intervention_exposure = $intervention_exposure,
                    observed_at = <datetime>$observed_at,
                    status = 'processed',
                    processed_at = time::now(),
                    created_at = time::now()
                """,
                {
                    "record_key": record_key,
                    "product": product_id,
                    "content": body.content,
                    "domain_path": body.domain_path,
                    "confidence": body.confidence,
                    "source_surface": body.source_surface,
                    "actor_ref": actor_ref,
                    "content_hash": request_fingerprint,
                    "decision": intervention.decision_id,
                    "prediction": intervention.prediction_id,
                    "contract_version": INTERVENTION_OBSERVATION_CONTRACT_VERSION,
                    "contract": contract,
                    "intervention_status": intervention.status,
                    "request_id": intervention.request_id,
                    "applicability_conditions_met": intervention.applicability_conditions_met,
                    "intervention_exposure": exposure.get("degree") if exposure else None,
                    "observed_at": observed_at,
                },
            )
        )

    stored = row or {
        "id": observation_id,
        "product": product_id,
        "affected_decision": intervention.decision_id,
        "affected_prediction": intervention.prediction_id,
        "intervention_contract": contract,
        "intervention_contract_version": INTERVENTION_OBSERVATION_CONTRACT_VERSION,
    }
    try:
        from core.engine.foresight.reconciler import process_intervention_observation

        resolution_trigger = await process_intervention_observation(stored)
    except Exception as exc:
        resolution_trigger = {"state": "degraded", "reason": type(exc).__name__}

    return {
        "status": "captured",
        "id": observation_id,
        "intervention": normalize_intervention_observation(stored),
        "resolution_trigger": resolution_trigger,
    }


async def _create_indicator_observation(body: ObservationCreate, user: dict, product_id: str) -> dict:
    """Persist manual indicator evidence through the existing capture boundary."""
    indicator = body.indicator
    if indicator is None:
        raise HTTPException(status_code=422, detail="indicator payload is required")
    from core.engine.foresight.indicators import (
        IndicatorRequestConflict,
        IndicatorTargetNotFound,
        record_indicator_observation,
    )

    try:
        return await record_indicator_observation(
            product_id=product_id,
            decision_id=indicator.decision_id,
            prediction_id=indicator.prediction_id,
            request_id=indicator.request_id,
            indicator_id=indicator.indicator_id,
            effect=indicator.effect,
            observed_at=indicator.observed_at or datetime.now(timezone.utc),
            value=indicator.value,
            unit=indicator.unit,
            evidence_refs=indicator.evidence_refs,
            reason=indicator.reason,
            content=body.content,
            source_kind="manual_observation",
            source_surface=body.source_surface,
            actor_ref=str(user.get("sub") or "authenticated_user")[:200],
            pool=pool,
        )
    except IndicatorTargetNotFound as exc:
        raise HTTPException(status_code=404, detail="Not found") from exc
    except IndicatorRequestConflict as exc:
        raise HTTPException(status_code=409, detail="indicator request_id conflict") from exc


async def _create_comparator_observation(body: ObservationCreate, user: dict, product_id: str) -> dict:
    """Persist optional observed-comparator evidence through the existing capture boundary."""
    comparator = body.comparator
    if comparator is None:
        raise HTTPException(status_code=422, detail="comparator payload is required")
    from core.engine.foresight.comparators import (
        ComparatorRequestConflict,
        ComparatorTargetNotFound,
        record_comparator_observation,
    )

    try:
        return await record_comparator_observation(
            product_id=product_id,
            decision_id=comparator.decision_id,
            prediction_id=comparator.prediction_id,
            request_id=comparator.request_id,
            comparator_type=comparator.comparator_type,
            design=comparator.design,
            observed_at=comparator.observed_at or datetime.now(timezone.utc),
            measurements=[item.model_dump(mode="json") for item in comparator.measurements],
            comparator_label=comparator.comparator_label,
            window_start=comparator.window_start,
            window_end=comparator.window_end,
            evidence_refs=comparator.evidence_refs,
            confounders=comparator.confounders,
            missing_evidence=comparator.missing_evidence,
            reason=comparator.reason,
            content=body.content,
            source_surface=body.source_surface,
            actor_ref=str(user.get("sub") or "authenticated_user")[:200],
            execution=comparator.execution.model_dump(mode="json") if comparator.execution else None,
            pool=pool,
        )
    except ComparatorTargetNotFound as exc:
        raise HTTPException(status_code=404, detail="Not found") from exc
    except ComparatorRequestConflict as exc:
        raise HTTPException(status_code=409, detail="comparator request_id conflict") from exc


async def _create_measurement_observation(body: ObservationCreate, user: dict, product_id: str) -> dict:
    """Persist a raw plan-linked sample and automatically attempt safe run assembly."""
    measurement = body.measurement
    if measurement is None:
        raise HTTPException(status_code=422, detail="measurement payload is required")
    from core.engine.foresight.measurements import (
        MeasurementRequestConflict,
        MeasurementTargetNotFound,
        record_measurement_observation,
    )

    try:
        return await record_measurement_observation(
            product_id=product_id,
            decision_id=measurement.decision_id,
            prediction_id=measurement.prediction_id,
            request_id=measurement.request_id,
            plan_id=measurement.plan_id,
            run_id=measurement.run_id,
            source_type=measurement.source_type,
            capability_id=measurement.capability_id,
            metric=measurement.metric,
            unit=measurement.unit,
            arm=measurement.arm,
            phase=measurement.phase,
            value=measurement.value,
            measured_at=measurement.measured_at,
            window_start=measurement.window_start,
            window_end=measurement.window_end,
            comparator_type=measurement.comparator_type,
            design=measurement.design,
            evidence_refs=measurement.evidence_refs,
            execution=measurement.execution.model_dump(mode="json")
            if measurement.execution
            else {"plan_id": measurement.plan_id},
            confounders=measurement.confounders,
            content=body.content,
            source_surface=body.source_surface,
            actor_ref=str(user.get("sub") or "authenticated_user")[:200],
            pool=pool,
        )
    except MeasurementTargetNotFound as exc:
        raise HTTPException(status_code=404, detail="Not found") from exc
    except MeasurementRequestConflict as exc:
        raise HTTPException(status_code=409, detail="measurement request_id conflict") from exc


@router.post("/observations", status_code=201)
async def create_observation(body: ObservationCreate, user: dict = Depends(get_current_user)):
    """Create a lightweight observation — simpler than importing a full session transcript."""
    product_id = user.get("product", "product:default")
    if body.observation_type == "intervention":
        return await _create_intervention_observation(body, user, product_id)
    if body.observation_type == "forecast_indicator":
        return await _create_indicator_observation(body, user, product_id)
    if body.observation_type == "forecast_comparator":
        return await _create_comparator_observation(body, user, product_id)
    if body.observation_type == "forecast_measurement":
        return await _create_measurement_observation(body, user, product_id)
    correction_links = {
        "supersedes": body.supersedes_correction_id,
        "invalidates": body.invalidates_correction_id,
        "contests": body.contests_correction_id,
    }
    content_hash = hashlib.sha256(body.content.encode("utf-8")).hexdigest()

    async with pool.connection() as db:
        if body.affected_decision_id:
            await _require_owned_target(db, body.affected_decision_id, "decision", product_id)
        if body.affected_task_id:
            await _require_owned_target(db, body.affected_task_id, "task", product_id)
        for target_id in correction_links.values():
            if target_id:
                await _require_owned_target(db, target_id, "observation", product_id)
        result = await db.query(
            """
            CREATE observation SET
                product = <record>$product,
                observation_type = $type,
                content = $content,
                domain_path = $domain_path,
                domain_hint = $domain_path,
                discipline_hint = $domain_path,
                confidence = $confidence,
                source = 'api',
                source_surface = $source_surface,
                actor_ref = $actor_ref,
                actor_class = 'authenticated_user',
                content_hash = $content_hash,
                lifecycle_state = IF $is_correction THEN $lifecycle_state ELSE NONE END,
                correction_contract_version = IF $is_correction THEN 'correction-v1' ELSE NONE END,
                affected_decision = IF $affected_decision THEN <record>$affected_decision ELSE NONE END,
                affected_task = IF $affected_task THEN <record>$affected_task ELSE NONE END,
                supersedes_correction = IF $supersedes THEN <record>$supersedes ELSE NONE END,
                invalidates_correction = IF $invalidates THEN <record>$invalidates ELSE NONE END,
                contests_correction = IF $contests THEN <record>$contests ELSE NONE END,
                expires_at = IF $is_correction THEN $expires_at ELSE NONE END,
                status = IF $is_correction THEN 'processed' ELSE 'pending' END,
                processed_at = IF $is_correction THEN time::now() ELSE NONE END,
                created_at = time::now()
            """,
            {
                "product": product_id,
                "type": body.observation_type,
                "content": body.content,
                "domain_path": body.domain_path,
                "confidence": body.confidence,
                "source_surface": body.source_surface,
                "actor_ref": str(user.get("sub") or "authenticated_user")[:200],
                "content_hash": content_hash,
                "is_correction": body.observation_type == "correction",
                "lifecycle_state": body.lifecycle_state,
                "affected_decision": body.affected_decision_id,
                "affected_task": body.affected_task_id,
                "supersedes": body.supersedes_correction_id,
                "invalidates": body.invalidates_correction_id,
                "contests": body.contests_correction_id,
                "expires_at": body.expires_at,
            },
        )
        row = parse_one(result)
        if row:
            target_states = {"supersedes": "superseded", "invalidates": "invalidated", "contests": "contested"}
            for relationship, target_id in correction_links.items():
                if target_id:
                    await db.query(
                        """
                        UPDATE <record>$target SET lifecycle_state = $state, updated_at = time::now()
                        WHERE product = <record>$product AND observation_type = 'correction'
                        """,
                        {"target": target_id, "state": target_states[relationship], "product": product_id},
                    )

    # Make the thin-client capture visible to a later invocation immediately;
    # the worker remains the retry path if synthesis is temporarily unavailable.
    if row and body.observation_type != "correction":
        try:
            from core.engine.capture.synthesizer import Synthesizer

            synth = Synthesizer(product_id=product_id, workspace_id=None, batch_size=1)
            synth._db_pool = pool
            await synth.add_observation(row)
            await synth.flush()
            async with pool.connection() as db:
                await db.query(
                    "UPDATE <record>$id SET status = 'processed', processed_at = time::now()",
                    {"id": str(row.get("id", ""))},
                )
        except Exception:
            pass

    result = {"status": "captured", "id": str(row.get("id", "")) if row else ""}
    if row and body.observation_type == "correction":
        result["correction"] = {
            "contract_version": "correction-v1",
            "correction_id": str(row.get("id", "")),
            "product_id": str(product_id),
            "affected_decision_id": body.affected_decision_id,
            "affected_task_id": body.affected_task_id,
            "source_surface": body.source_surface,
            "actor": str(user.get("sub") or "authenticated_user")[:200],
            "actor_class": "authenticated_user",
            "created_at": row.get("created_at"),
            "content_hash": content_hash,
            "confidence": body.confidence,
            "lifecycle_state": effective_correction_lifecycle(body.lifecycle_state, body.expires_at),
            "stored_lifecycle_state": body.lifecycle_state,
            "expires_at": body.expires_at,
            "supersedes_correction_id": body.supersedes_correction_id,
            "invalidates_correction_id": body.invalidates_correction_id,
            "contests_correction_id": body.contests_correction_id,
        }
    return result


class SessionImport(BaseModel):
    transcript: str
    workspace_id: str | None = None


@router.post("/sessions", status_code=202)
async def import_session(body: SessionImport, user: dict = Depends(get_current_user)):
    if len(body.transcript.encode()) > 500_000:
        from fastapi import HTTPException

        raise HTTPException(status_code=413, detail="Transcript exceeds 500KB limit")

    product_id = user.get("product", "product:default")
    session_id = str(uuid.uuid4())
    watcher = SessionImportWatcher(body.transcript, session_id=session_id)
    pipeline = CapturePipeline(
        watcher=watcher,
        product_id=product_id,
        workspace_id=body.workspace_id,
        db_pool=pool,
    )
    # Run async — don't block the response
    logged_task(pipeline.run(), label="capture.pipeline")
    return {"session_id": session_id, "status": "processing"}


@router.websocket("/capture/ws")
async def capture_websocket(websocket: WebSocket):
    await websocket.accept()

    # Authenticate via first message (avoids leaking token in URL/proxy logs)
    # Also supports legacy query param for backward compatibility
    token = websocket.query_params.get("token")
    if not token:
        try:
            auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
            token = auth_msg.get("token")
        except (asyncio.TimeoutError, Exception):
            await websocket.close(code=1008)
            return

    if not token:
        await websocket.close(code=1008)
        return

    try:
        user = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except InvalidTokenError:
        await websocket.close(code=1008)
        return

    product_id = user.get("product", "product:default")
    workspace_id = websocket.query_params.get("workspace")

    session_id = str(uuid.uuid4())
    event_queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()

    # WebSocket watcher that reads from the queue
    class _QueueWatcher:
        async def watch(self):
            while True:
                event = await event_queue.get()
                if event is None:
                    return
                yield event

    watcher = _QueueWatcher()
    pipeline = CapturePipeline(
        watcher=watcher,
        product_id=product_id,
        workspace_id=workspace_id,
        db_pool=pool,
    )

    pipeline_task = asyncio.create_task(pipeline.run())

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            event = StreamEvent(
                timestamp=datetime.now(),
                event_type=msg.get("event_type", "text"),
                content=msg.get("content", ""),
                session_id=session_id,
                metadata=msg.get("metadata"),
            )
            await event_queue.put(event)
            await websocket.send_json({"type": "ack"})
    except WebSocketDisconnect:
        pass
    finally:
        await event_queue.put(None)  # Signal stream end
        await pipeline_task
