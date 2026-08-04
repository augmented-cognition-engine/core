"""Shared persistence and finalization for ordinary observation processing."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from surrealdb import RecordID

from core.engine.capture.outcomes import (
    MAX_ERROR_MESSAGE_CHARS,
    SYNTHESIS_POLICY_VERSION,
    SYNTHESIS_PROCESSOR_VERSION,
    SYNTHESIS_SCHEMA_VERSION,
    FailureCategory,
    ObservationSynthesisOutcomeV1,
    ProcessingState,
    SuccessfulDisposition,
    SynthesisFailureV1,
    SynthesisOutcomeReceiptV1,
    SynthesisProvenanceV1,
    build_attempt_id,
    build_material_hash,
    build_receipt_id,
    receipt_hash,
)
from core.engine.core.db import parse_one, parse_rows

logger = logging.getLogger(__name__)

MAX_PROCESSING_ATTEMPTS = 3
BASE_RETRY_DELAY_SECONDS = 5
MAX_RETRY_DELAY_SECONDS = 300
MAX_HEALTHY_PENDING_AGE_SECONDS = 900
MAX_HEALTHY_PROCESSING_AGE_SECONDS = 300


class OutcomeReplayConflict(RuntimeError):
    """The same deterministic attempt coordinate was replayed with different material."""


class OutcomeProductScopeError(RuntimeError):
    """A receipt or referenced record does not belong to the requested product."""


def _record_text(value: Any) -> str:
    return str(value or "")


def _record_id(value: str) -> RecordID:
    table, separator, key = value.partition(":")
    if not separator or not table or not key:
        raise ValueError("record reference must use table:key form")
    return RecordID(table, key)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _bounded_error_message(exc: Exception) -> str:
    message = " ".join(str(exc).split()) or type(exc).__name__
    return message[:MAX_ERROR_MESSAGE_CHARS]


def classify_synthesis_failure(exc: Exception) -> SynthesisFailureV1:
    """Return a bounded classification; never persist a traceback or provider payload."""
    error_type = type(exc).__name__[:160]
    module = type(exc).__module__
    lowered = f"{module}.{error_type}".lower()
    if isinstance(exc, OutcomeProductScopeError):
        category = FailureCategory.VALIDATION
        code = "cross_product_outcome_reference"
    elif isinstance(exc, (ValueError, TypeError)):
        category = FailureCategory.VALIDATION
        code = "invalid_synthesis_outcome"
    elif any(token in lowered for token in ("surreal", "database", "db", "persist")):
        category = FailureCategory.PERSISTENCE
        code = "persistence_error"
    elif any(token in lowered for token in ("provider", "openai", "anthropic", "llm", "timeout")):
        category = FailureCategory.PROVIDER
        code = "provider_error"
    elif isinstance(exc, RuntimeError):
        category = FailureCategory.PROCESSING
        code = "processing_error"
    else:
        category = FailureCategory.UNKNOWN
        code = "unknown_error"
    return SynthesisFailureV1(
        category=category,
        code=code,
        error_type=error_type or "Exception",
        message=_bounded_error_message(exc),
    )


def _retry_time(*, attempt_count: int, completed_at: datetime) -> datetime:
    delay = min(MAX_RETRY_DELAY_SECONDS, BASE_RETRY_DELAY_SECONDS * (2 ** max(0, attempt_count - 1)))
    return completed_at + timedelta(seconds=delay)


def _receipt_from_row(row: dict[str, Any] | None) -> SynthesisOutcomeReceiptV1 | None:
    if not row:
        return None
    payload = row.get("receipt")
    if not isinstance(payload, dict):
        return None
    return SynthesisOutcomeReceiptV1.model_validate(payload)


async def load_outcome_receipt(db_pool, *, receipt_id: str, product_id: str) -> SynthesisOutcomeReceiptV1 | None:
    """Load a receipt only through its product scope."""
    async with db_pool.connection() as db:
        row = parse_one(
            await db.query(
                "SELECT receipt FROM ONLY <record>$id WHERE product = <record>$product",
                {"id": receipt_id, "product": product_id},
            )
        )
    return _receipt_from_row(row)


async def load_attempt_receipt(
    db_pool,
    *,
    attempt_id: str,
    product_id: str,
) -> SynthesisOutcomeReceiptV1 | None:
    async with db_pool.connection() as db:
        row = parse_one(
            await db.query(
                """
                SELECT receipt FROM synthesis_outcome_receipt
                WHERE product = <record>$product AND attempt_id = $attempt_id
                LIMIT 1
                """,
                {"product": product_id, "attempt_id": attempt_id},
            )
        )
    return _receipt_from_row(row)


async def _require_product_references(
    db_pool,
    receipt: SynthesisOutcomeReceiptV1,
    *,
    observation_prevalidated: bool = False,
) -> None:
    """Fail closed if the observation or any receipt reference crosses products."""
    outcome = receipt.outcome
    insight_refs: tuple[str, ...] = ()
    conflict_refs: tuple[str, ...] = ()
    if outcome is not None:
        insight_refs = tuple(
            sorted(
                set(
                    outcome.created_insight_refs
                    + outcome.updated_insight_refs
                    + outcome.merged_insight_refs
                    + outcome.conflicting_insight_refs
                )
            )
        )
        conflict_refs = outcome.conflict_record_refs

    async with db_pool.connection() as db:
        if not observation_prevalidated:
            owned_observation = parse_one(
                await db.query(
                    "SELECT id FROM ONLY <record>$id WHERE product = <record>$product",
                    {"id": receipt.observation_id, "product": receipt.product_id},
                )
            )
            if not owned_observation:
                raise OutcomeProductScopeError("observation is absent from the receipt product scope")
        if insight_refs:
            rows = parse_rows(
                await db.query(
                    "SELECT id FROM insight WHERE product = <record>$product AND id IN $ids",
                    {"product": receipt.product_id, "ids": [_record_id(ref) for ref in insight_refs]},
                )
            )
            if {str(row.get("id")) for row in rows} != set(insight_refs):
                raise OutcomeProductScopeError("an insight reference is absent from the receipt product scope")
        if conflict_refs:
            rows = parse_rows(
                await db.query(
                    "SELECT id FROM conflict WHERE product = <record>$product AND id IN $ids",
                    {"product": receipt.product_id, "ids": [_record_id(ref) for ref in conflict_refs]},
                )
            )
            if {str(row.get("id")) for row in rows} != set(conflict_refs):
                raise OutcomeProductScopeError("a conflict reference is absent from the receipt product scope")


async def persist_outcome_receipt(
    db_pool,
    receipt: SynthesisOutcomeReceiptV1,
    *,
    references_prevalidated: bool = False,
) -> SynthesisOutcomeReceiptV1:
    """Create an immutable receipt, returning an exact replay unchanged.

    A different payload at the same deterministic attempt identity raises rather
    than overwriting history.  ``references_prevalidated`` is reserved for the
    shared lifecycle, whose inputs come from product-scoped capture/fetch paths.
    Direct callers are checked against the database.
    """
    validated = SynthesisOutcomeReceiptV1.model_validate(receipt)
    existing = await load_attempt_receipt(
        db_pool,
        attempt_id=validated.attempt_id,
        product_id=validated.product_id,
    )
    if existing is not None:
        if receipt_hash(existing) != receipt_hash(validated):
            raise OutcomeReplayConflict("attempt identity already has different immutable receipt material")
        return existing

    # Lifecycle callers may already have proved observation ownership, but
    # synthesized insight/conflict references are always checked.  A trusted
    # input route must not turn an LLM-supplied cross-product reference into
    # durable evidence.
    await _require_product_references(
        db_pool,
        validated,
        observation_prevalidated=references_prevalidated,
    )

    outcome = validated.outcome
    payload = validated.model_dump(mode="json", exclude_none=True)
    params = {
        "record_key": validated.receipt_id.partition(":")[2],
        "contract_version": validated.contract_version,
        "product": validated.product_id,
        "observation": validated.observation_id,
        "attempt_id": validated.attempt_id,
        "attempt_count": validated.attempt_count,
        "processing_state": validated.processing_state.value,
        "disposition": outcome.disposition.value if outcome else None,
        "created_insights": [_record_id(ref) for ref in outcome.created_insight_refs] if outcome else [],
        "updated_insights": [_record_id(ref) for ref in outcome.updated_insight_refs] if outcome else [],
        "merged_insights": [_record_id(ref) for ref in outcome.merged_insight_refs] if outcome else [],
        "conflicting_insights": [_record_id(ref) for ref in outcome.conflicting_insight_refs] if outcome else [],
        "conflict_records": [_record_id(ref) for ref in outcome.conflict_record_refs] if outcome else [],
        "reason": outcome.reason if outcome else None,
        "failure": validated.failure.model_dump(mode="json") if validated.failure else None,
        "retryable": validated.retryable,
        "next_retry_at": validated.next_retry_at,
        "processor_version": validated.processor_version,
        "policy_version": validated.policy_version,
        "schema_version": validated.schema_version,
        "material_hash": validated.material_hash,
        "started_at": validated.started_at,
        "completed_at": validated.completed_at,
        "provenance": validated.provenance.model_dump(mode="json", exclude_none=True),
        "explainable_terminal": validated.explainable_terminal,
        "receipt": payload,
        "receipt_hash": receipt_hash(validated),
    }
    async with db_pool.connection() as db:
        result = await db.query(
            """
            CREATE ONLY type::record('synthesis_outcome_receipt', $record_key) SET
                contract_version = $contract_version,
                product = <record>$product,
                observation = <record>$observation,
                attempt_id = $attempt_id,
                attempt_count = $attempt_count,
                processing_state = $processing_state,
                disposition = $disposition,
                created_insights = $created_insights,
                updated_insights = $updated_insights,
                merged_insights = $merged_insights,
                conflicting_insights = $conflicting_insights,
                conflict_records = $conflict_records,
                reason = $reason,
                failure = $failure,
                retryable = $retryable,
                next_retry_at = $next_retry_at,
                processor_version = $processor_version,
                policy_version = $policy_version,
                schema_version = $schema_version,
                material_hash = $material_hash,
                started_at = $started_at,
                completed_at = $completed_at,
                provenance = $provenance,
                explainable_terminal = $explainable_terminal,
                receipt = $receipt,
                receipt_hash = $receipt_hash,
                created_at = time::now()
            """,
            params,
        )
    if isinstance(result, str):
        # Duplicate-key races are resolved through the immutable replay check.
        raced = await load_attempt_receipt(
            db_pool,
            attempt_id=validated.attempt_id,
            product_id=validated.product_id,
        )
        if raced is not None and receipt_hash(raced) == receipt_hash(validated):
            return raced
        raise OutcomeReplayConflict(f"receipt create failed closed: {result[:200]}")
    stored = _receipt_from_row(parse_one(result))
    return stored or validated


def _outcome_from_synthesizer(result: Any, *, observation_id: str) -> ObservationSynthesisOutcomeV1:
    """Extract exactly one explicit outcome from the synthesizer protocol."""
    if isinstance(result, dict):
        raw_outcomes = result.get("outcomes") or []
        for raw in raw_outcomes:
            candidate = (
                raw
                if isinstance(raw, ObservationSynthesisOutcomeV1)
                else ObservationSynthesisOutcomeV1.model_validate(raw)
            )
            if candidate.observation_id == observation_id:
                return candidate
        if not any(int(result.get(key, 0) or 0) for key in ("new_insights", "updates", "conflicts")):
            return ObservationSynthesisOutcomeV1(
                observation_id=observation_id,
                disposition=SuccessfulDisposition.SKIPPED,
                reason="synthesis_policy_returned_no_material_action",
            )
    if result is None or not isinstance(result, dict):
        return ObservationSynthesisOutcomeV1(
            observation_id=observation_id,
            disposition=SuccessfulDisposition.SKIPPED,
            reason="legacy_synthesizer_protocol_returned_no_explicit_outcome",
        )
    raise ValueError("synthesizer did not return an explicit outcome for the observation")


def _build_receipt(
    *,
    product_id: str,
    observation_id: str,
    attempt_count: int,
    material_hash: str,
    route: str,
    source: str | None,
    session_id: str | None,
    started_at: datetime,
    completed_at: datetime,
    outcome: ObservationSynthesisOutcomeV1 | None = None,
    failure: SynthesisFailureV1 | None = None,
) -> SynthesisOutcomeReceiptV1:
    attempt_id = build_attempt_id(
        product_id=product_id,
        observation_id=observation_id,
        attempt_count=attempt_count,
        route=route,
    )
    if outcome is not None:
        state = ProcessingState.SUCCEEDED
        retryable = False
        next_retry_at = None
    else:
        exhausted = attempt_count >= MAX_PROCESSING_ATTEMPTS
        state = ProcessingState.DEAD_LETTER if exhausted else ProcessingState.RETRYABLE_FAILED
        retryable = not exhausted
        next_retry_at = None if exhausted else _retry_time(attempt_count=attempt_count, completed_at=completed_at)
    return SynthesisOutcomeReceiptV1(
        receipt_id=build_receipt_id(product_id=product_id, attempt_id=attempt_id),
        product_id=product_id,
        observation_id=observation_id,
        attempt_id=attempt_id,
        attempt_count=attempt_count,
        processing_state=state,
        outcome=outcome,
        failure=failure,
        retryable=retryable,
        next_retry_at=next_retry_at,
        processor_version=SYNTHESIS_PROCESSOR_VERSION,
        policy_version=SYNTHESIS_POLICY_VERSION,
        schema_version=SYNTHESIS_SCHEMA_VERSION,
        material_hash=material_hash,
        started_at=started_at,
        completed_at=completed_at,
        provenance=SynthesisProvenanceV1(route=route, source=source, session_id=session_id),
        explainable_terminal=True,
    )


async def _mark_processing(
    db_pool,
    *,
    observation_id: str,
    product_id: str,
    attempt_count: int,
    route: str,
    started_at: datetime,
    lease_id: str | None = None,
    lease_owner: str | None = None,
) -> None:
    lease_where = ""
    if lease_id is not None:
        lease_where = """
            AND processing_lease_id = $lease_id
            AND processing_lease_owner = $lease_owner
            AND processing_lease_expires_at > $started_at
        """
    async with db_pool.connection() as db:
        result = await db.query(
            f"""
            UPDATE <record>$id SET
                processing_state = 'processing',
                processing_attempt_count = $attempt_count,
                retry_count = $attempt_count - 1,
                processing_started_at = $started_at,
                processing_route = $route,
                next_retry_at = NONE,
                updated_at = time::now()
            WHERE product = <record>$product
            {lease_where}
            RETURN AFTER
            """,
            {
                "id": observation_id,
                "product": product_id,
                "attempt_count": attempt_count,
                "started_at": started_at,
                "route": route,
                "lease_id": lease_id,
                "lease_owner": lease_owner,
            },
        )
    if lease_id is not None and not parse_rows(result):
        from core.engine.capture.leases import ObservationLeaseLost

        raise ObservationLeaseLost("processing attempt no longer owns its observation lease")


async def _finalize_observation(
    db_pool,
    receipt: SynthesisOutcomeReceiptV1,
    *,
    confidence: float | None = None,
    observation_type: str | None = None,
    lease_id: str | None = None,
    lease_owner: str | None = None,
) -> None:
    succeeded = receipt.processing_state is ProcessingState.SUCCEEDED
    if succeeded:
        state_sql = "processing_state = 'succeeded', status = 'processed', processed_at = $completed_at"
    elif receipt.processing_state is ProcessingState.DEAD_LETTER:
        state_sql = "processing_state = 'dead_letter', status = 'failed', processed_at = NONE"
    else:
        state_sql = "processing_state = 'retryable_failed', status = 'pending', processed_at = NONE"
    lease_where = ""
    if lease_id is not None:
        lease_where = """
            AND processing_lease_id = $lease_id
            AND processing_lease_owner = $lease_owner
            AND processing_lease_expires_at > time::now()
        """
    async with db_pool.connection() as db:
        result = await db.query(
            f"""
            UPDATE <record>$id SET
                {state_sql},
                processing_attempt_count = $attempt_count,
                retry_count = $attempt_count,
                next_retry_at = $next_retry_at,
                outcome_receipt = <record>$receipt_id,
                last_error = $last_error,
                processing_lease_id = NONE,
                processing_lease_owner = NONE,
                processing_lease_acquired_at = NONE,
                processing_lease_heartbeat_at = NONE,
                processing_lease_expires_at = NONE,
                processing_lease_recovered = NONE,
                processing_lease_prior_state = NONE,
                updated_at = time::now()
            WHERE product = <record>$product
            {lease_where}
            RETURN AFTER
            """,
            {
                "id": receipt.observation_id,
                "product": receipt.product_id,
                "attempt_count": receipt.attempt_count,
                "next_retry_at": receipt.next_retry_at,
                "receipt_id": receipt.receipt_id,
                "completed_at": receipt.completed_at,
                "last_error": receipt.failure.message if receipt.failure else None,
                # Retained as an unused compatibility binding for capture-path
                # instrumentation/tests that inspect the final DB parameter set.
                "confidence": confidence,
                "type": observation_type,
                "lease_id": lease_id,
                "lease_owner": lease_owner,
            },
        )
    if lease_id is not None and not parse_rows(result):
        from core.engine.capture.leases import ObservationLeaseLost

        raise ObservationLeaseLost("finalization lost its observation lease fence")


async def _restore_attempt_coordinate(
    db_pool,
    *,
    observation_id: str,
    product_id: str,
    prior_attempts: int,
    exc: Exception,
    lease_id: str | None = None,
    lease_owner: str | None = None,
) -> None:
    """Best-effort rollback of queue bookkeeping after receipt/finalization failure.

    Synthesis side effects use the deterministic attempt identity. Restoring the
    prior counter makes the next invocation replay that same coordinate, so a
    receipt written just before a finalization failure is loaded instead of
    causing synthesis to run again.
    """
    try:
        lease_where = ""
        if lease_id is not None:
            lease_where = """
                AND processing_lease_id = $lease_id
                AND processing_lease_owner = $lease_owner
            """
        async with db_pool.connection() as db:
            await db.query(
                f"""
                UPDATE <record>$id SET
                    status = 'pending',
                    processing_state = 'pending',
                    processing_attempt_count = $prior_attempts,
                    retry_count = $prior_attempts,
                    processing_started_at = NONE,
                    next_retry_at = NONE,
                    last_error = $last_error,
                    processing_lease_id = NONE,
                    processing_lease_owner = NONE,
                    processing_lease_acquired_at = NONE,
                    processing_lease_heartbeat_at = NONE,
                    processing_lease_expires_at = NONE,
                    processing_lease_recovered = NONE,
                    processing_lease_prior_state = NONE,
                    updated_at = time::now()
                WHERE product = <record>$product
                {lease_where}
                """,
                {
                    "id": observation_id,
                    "product": product_id,
                    "prior_attempts": prior_attempts,
                    "last_error": _bounded_error_message(exc),
                    "lease_id": lease_id,
                    "lease_owner": lease_owner,
                },
            )
    except Exception:
        logger.exception(
            "Could not restore observation attempt coordinate: observation=%s product=%s",
            observation_id,
            product_id,
        )


async def process_observation_attempt(
    observation: dict[str, Any],
    *,
    db_pool,
    route: str,
    synthesizer_factory: Callable[..., Any] | None = None,
    scope_prevalidated: bool = False,
    lease_id: str | None = None,
    lease_owner: str | None = None,
    lease_recovered: bool = False,
) -> SynthesisOutcomeReceiptV1:
    """Run and durably finalize one ordinary observation attempt.

    All API, MCP, worker, document, and session paths call this function.  It is
    deliberately single-observation: the durable receipt can therefore account
    for every input without guessing how a batch-level count maps back to rows.
    """
    observation_id = _record_text(observation.get("id"))
    product_id = _record_text(observation.get("product"))
    if not observation_id.startswith("observation:") or not product_id.startswith("product:"):
        raise ValueError("processing requires product-scoped observation and product identities")
    if (lease_id is None) is not (lease_owner is None):
        raise ValueError("lease_id and lease_owner must be supplied together")
    if lease_id is not None:
        from core.engine.capture.leases import load_active_observation_lease

        await load_active_observation_lease(
            db_pool,
            observation_id=observation_id,
            product_id=product_id,
            lease_id=lease_id,
            owner_id=lease_owner or "",
        )
    if not scope_prevalidated:
        async with db_pool.connection() as db:
            owned = parse_one(
                await db.query(
                    "SELECT id FROM ONLY <record>$id WHERE product = <record>$product",
                    {"id": observation_id, "product": product_id},
                )
            )
        if not owned:
            raise OutcomeProductScopeError("observation is absent from the processing product scope")

    prior_attempts = max(
        int(observation.get("processing_attempt_count") or 0),
        int(observation.get("retry_count") or 0),
    )
    recovered_attempt = lease_recovered or bool(observation.get("processing_lease_recovered"))
    attempt_count = prior_attempts if recovered_attempt and prior_attempts > 0 else prior_attempts + 1
    material_hash = build_material_hash(observation, product_id=product_id, observation_id=observation_id)
    attempt_id = build_attempt_id(
        product_id=product_id,
        observation_id=observation_id,
        attempt_count=attempt_count,
        route=route,
    )
    existing = await load_attempt_receipt(db_pool, attempt_id=attempt_id, product_id=product_id)
    if existing is not None:
        if existing.material_hash != material_hash:
            raise OutcomeReplayConflict("attempt replay changed observation material")
        await _finalize_observation(
            db_pool,
            existing,
            confidence=observation.get("confidence"),
            observation_type=observation.get("observation_type"),
            lease_id=lease_id,
            lease_owner=lease_owner,
        )
        return existing

    started_at = _utcnow()
    await _mark_processing(
        db_pool,
        observation_id=observation_id,
        product_id=product_id,
        attempt_count=attempt_count,
        route=route,
        started_at=started_at,
        lease_id=lease_id,
        lease_owner=lease_owner,
    )

    if synthesizer_factory is None:
        from core.engine.capture.synthesizer import Synthesizer

        synthesizer_factory = Synthesizer

    if lease_id is not None:
        from core.engine.capture.leases import load_active_observation_lease

        await load_active_observation_lease(
            db_pool,
            observation_id=observation_id,
            product_id=product_id,
            lease_id=lease_id,
            owner_id=lease_owner or "",
        )

    try:
        synth = synthesizer_factory(product_id=product_id, workspace_id=None, batch_size=1)
        synth._db_pool = db_pool
        synth._attempt_id = attempt_id
        add_result = await synth.add_observation(observation)
        # Always flush to drain ancillary work and preserve the legacy
        # Synthesizer protocol. A batch_size=1 synthesizer returns its material
        # result from add_observation; the subsequent empty flush is harmless.
        flush_result = await synth.flush()
        result = add_result if isinstance(add_result, dict) else flush_result
        outcome = _outcome_from_synthesizer(result, observation_id=observation_id)
        completed_at = _utcnow()
        receipt = _build_receipt(
            product_id=product_id,
            observation_id=observation_id,
            attempt_count=attempt_count,
            material_hash=material_hash,
            route=route,
            source=str(observation.get("source") or "") or None,
            session_id=str(observation.get("session_id") or "") or None,
            started_at=started_at,
            completed_at=completed_at,
            outcome=outcome,
        )
    except Exception as exc:
        completed_at = _utcnow()
        receipt = _build_receipt(
            product_id=product_id,
            observation_id=observation_id,
            attempt_count=attempt_count,
            material_hash=material_hash,
            route=route,
            source=str(observation.get("source") or "") or None,
            session_id=str(observation.get("session_id") or "") or None,
            started_at=started_at,
            completed_at=completed_at,
            failure=classify_synthesis_failure(exc),
        )
        logger.warning(
            "Observation attempt failed truthfully: observation=%s state=%s error=%s",
            observation_id,
            receipt.processing_state.value,
            receipt.failure.code if receipt.failure else "unknown",
        )

    if lease_id is not None:
        from core.engine.capture.leases import load_active_observation_lease

        await load_active_observation_lease(
            db_pool,
            observation_id=observation_id,
            product_id=product_id,
            lease_id=lease_id,
            owner_id=lease_owner or "",
        )

    try:
        durable = await persist_outcome_receipt(
            db_pool,
            receipt,
            references_prevalidated=scope_prevalidated,
        )
    except OutcomeProductScopeError as exc:
        # The proposed successful outcome is not admissible evidence. Persist a
        # bounded failure receipt for the same attempt instead of leaving the
        # row unexplained or trusting a cross-product model reference.
        failed_receipt = _build_receipt(
            product_id=product_id,
            observation_id=observation_id,
            attempt_count=attempt_count,
            material_hash=material_hash,
            route=route,
            source=str(observation.get("source") or "") or None,
            session_id=str(observation.get("session_id") or "") or None,
            started_at=started_at,
            completed_at=_utcnow(),
            failure=classify_synthesis_failure(exc),
        )
        try:
            durable = await persist_outcome_receipt(
                db_pool,
                failed_receipt,
                references_prevalidated=scope_prevalidated,
            )
        except Exception as persist_exc:
            await _restore_attempt_coordinate(
                db_pool,
                observation_id=observation_id,
                product_id=product_id,
                prior_attempts=prior_attempts,
                exc=persist_exc,
                lease_id=lease_id,
                lease_owner=lease_owner,
            )
            raise
    except Exception as exc:
        await _restore_attempt_coordinate(
            db_pool,
            observation_id=observation_id,
            product_id=product_id,
            prior_attempts=prior_attempts,
            exc=exc,
            lease_id=lease_id,
            lease_owner=lease_owner,
        )
        raise

    try:
        await _finalize_observation(
            db_pool,
            durable,
            confidence=observation.get("confidence"),
            observation_type=observation.get("observation_type"),
            lease_id=lease_id,
            lease_owner=lease_owner,
        )
    except Exception as exc:
        await _restore_attempt_coordinate(
            db_pool,
            observation_id=observation_id,
            product_id=product_id,
            prior_attempts=prior_attempts,
            exc=exc,
            lease_id=lease_id,
            lease_owner=lease_owner,
        )
        raise
    return durable


def _count(row: dict[str, Any] | None) -> int:
    return int((row or {}).get("n") or 0)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


async def observation_outcome_health(db_pool, *, product_id: str) -> dict[str, Any]:
    """Return bounded product-scoped lifecycle counts and declared health semantics."""
    async with db_pool.connection() as db:
        queue_depth = parse_one(
            await db.query(
                """
                SELECT count() AS n FROM observation
                WHERE product = <record>$product AND status = 'pending'
                GROUP ALL
                """,
                {"product": product_id},
            )
        )
        pending = parse_one(
            await db.query(
                """
                SELECT count() AS n FROM observation
                WHERE product = <record>$product AND status = 'pending'
                  AND (processing_state IS NONE OR processing_state = 'pending')
                GROUP ALL
                """,
                {"product": product_id},
            )
        )
        oldest = parse_one(
            await db.query(
                """
                SELECT created_at FROM observation
                WHERE product = <record>$product AND status = 'pending'
                  AND (processing_state IS NONE OR processing_state = 'pending')
                ORDER BY created_at ASC LIMIT 1
                """,
                {"product": product_id},
            )
        )
        processing = parse_one(
            await db.query(
                "SELECT count() AS n FROM observation WHERE product = <record>$product AND processing_state = 'processing' GROUP ALL",
                {"product": product_id},
            )
        )
        oldest_processing = parse_one(
            await db.query(
                """
                SELECT processing_started_at FROM observation
                WHERE product = <record>$product AND processing_state = 'processing'
                ORDER BY processing_started_at ASC LIMIT 1
                """,
                {"product": product_id},
            )
        )
        expired_leases = parse_one(
            await db.query(
                """
                SELECT count() AS n FROM observation
                WHERE product = <record>$product
                  AND status = 'pending'
                  AND processing_state = 'processing'
                  AND (
                        processing_lease_expires_at <= $now
                        OR (
                            processing_lease_id IS NONE
                            AND (
                                processing_started_at IS NONE
                                OR processing_started_at <= $orphan_cutoff
                            )
                        )
                  )
                GROUP ALL
                """,
                {
                    "product": product_id,
                    "now": _utcnow(),
                    "orphan_cutoff": _utcnow() - timedelta(seconds=MAX_HEALTHY_PROCESSING_AGE_SECONDS),
                },
            )
        )
        retryable = parse_one(
            await db.query(
                "SELECT count() AS n FROM observation WHERE product = <record>$product AND processing_state = 'retryable_failed' GROUP ALL",
                {"product": product_id},
            )
        )
        dead_letter = parse_one(
            await db.query(
                "SELECT count() AS n FROM observation WHERE product = <record>$product AND processing_state = 'dead_letter' GROUP ALL",
                {"product": product_id},
            )
        )
        dispositions = parse_rows(
            await db.query(
                """
                SELECT disposition, count() AS n FROM synthesis_outcome_receipt
                WHERE product = <record>$product AND processing_state = 'succeeded'
                GROUP BY disposition
                """,
                {"product": product_id},
            )
        )
        latest = parse_one(
            await db.query(
                """
                SELECT completed_at FROM synthesis_outcome_receipt
                WHERE product = <record>$product AND processing_state = 'succeeded'
                ORDER BY completed_at DESC LIMIT 1
                """,
                {"product": product_id},
            )
        )
        recent_successes = parse_one(
            await db.query(
                """
                SELECT count() AS n FROM synthesis_outcome_receipt
                WHERE product = <record>$product
                  AND processing_state = 'succeeded'
                  AND completed_at >= $cutoff
                GROUP ALL
                """,
                {"product": product_id, "cutoff": _utcnow() - timedelta(minutes=5)},
            )
        )
        legacy = parse_one(
            await db.query(
                """
                SELECT count() AS n FROM observation
                WHERE product = <record>$product AND status = 'processed' AND outcome_receipt IS NONE
                  AND NOT (observation_type = 'correction' AND correction_contract_version IS NOT NONE)
                  AND NOT (observation_type = 'intervention' AND intervention_contract_version IS NOT NONE)
                  AND NOT (observation_type = 'forecast_indicator' AND indicator_contract_version IS NOT NONE)
                  AND NOT (observation_type = 'forecast_comparator' AND comparator_contract_version IS NOT NONE)
                  AND NOT (observation_type = 'forecast_measurement' AND measurement_contract_version IS NOT NONE)
                GROUP ALL
                """,
                {"product": product_id},
            )
        )

    oldest_at = _parse_datetime((oldest or {}).get("created_at"))
    oldest_age = max(0.0, (_utcnow() - oldest_at).total_seconds()) if oldest_at else None
    oldest_processing_at = _parse_datetime((oldest_processing or {}).get("processing_started_at"))
    oldest_processing_age = (
        max(0.0, (_utcnow() - oldest_processing_at).total_seconds()) if oldest_processing_at else None
    )
    succeeded = {disposition.value: 0 for disposition in SuccessfulDisposition}
    for row in dispositions:
        disposition = str(row.get("disposition") or "")
        if disposition in succeeded:
            succeeded[disposition] = int(row.get("n") or 0)
    pending_count = _count(pending)
    retryable_count = _count(retryable)
    dead_letter_count = _count(dead_letter)
    legacy_count = _count(legacy)
    expired_lease_count = _count(expired_leases)
    recent_success_count = _count(recent_successes)
    policy_breaches: list[str] = []
    if pending_count and oldest_age is not None and oldest_age > MAX_HEALTHY_PENDING_AGE_SECONDS:
        policy_breaches.append("oldest_pending_age")
    if retryable_count:
        policy_breaches.append("retryable_failed")
    if dead_letter_count:
        policy_breaches.append("dead_letter")
    if legacy_count:
        policy_breaches.append("legacy_unexplained")
    if expired_lease_count:
        policy_breaches.append("expired_processing_lease")
    if oldest_processing_age is not None and oldest_processing_age > MAX_HEALTHY_PROCESSING_AGE_SECONDS:
        policy_breaches.append("oldest_processing_age")

    return {
        "status": "degraded" if policy_breaches else "healthy",
        "queue_depth": _count(queue_depth),
        "pending_count": pending_count,
        "oldest_pending_age_seconds": round(oldest_age, 3) if oldest_age is not None else None,
        "processing_count": _count(processing),
        "oldest_processing_age_seconds": (
            round(oldest_processing_age, 3) if oldest_processing_age is not None else None
        ),
        "expired_processing_lease_count": expired_lease_count,
        "succeeded_by_disposition": succeeded,
        "retryable_failure_count": retryable_count,
        "dead_letter_count": dead_letter_count,
        "legacy_unexplained_count": legacy_count,
        "last_successful_outcome_at": (latest or {}).get("completed_at"),
        "successful_outcomes_last_5m": recent_success_count,
        "successful_outcomes_per_minute_5m": round(recent_success_count / 5.0, 3),
        "policy": {
            "max_healthy_pending_age_seconds": MAX_HEALTHY_PENDING_AGE_SECONDS,
            "max_retryable_failures": 0,
            "max_dead_letters": 0,
            "max_legacy_unexplained": 0,
            "max_healthy_processing_age_seconds": MAX_HEALTHY_PROCESSING_AGE_SECONDS,
            "max_expired_processing_leases": 0,
        },
        "policy_breaches": policy_breaches,
    }
