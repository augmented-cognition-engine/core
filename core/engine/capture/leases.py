"""Versioned contracts for product-scoped observation processing leases."""

from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.engine.core.db import parse_one, parse_rows

OBSERVATION_LEASE_CONTRACT_VERSION = "ace.capture.observation-lease/v1"
DEFAULT_LEASE_SECONDS = 120.0
DEFAULT_HEARTBEAT_SECONDS = 30.0
LEGACY_PROCESSING_RECOVERY_SECONDS = 300.0

_PRODUCT_ID = re.compile(r"^product:[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_OBSERVATION_ID = re.compile(r"^observation:[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
_LEASE_ID = re.compile(r"^observation_lease:[a-f0-9]{32}$")
_OWNER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$")


class LeaseContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ObservationLeaseV1(LeaseContract):
    """One fenced, time-bounded authority to process one observation."""

    contract_version: Literal["ace.capture.observation-lease/v1"] = OBSERVATION_LEASE_CONTRACT_VERSION
    lease_id: str
    product_id: str
    observation_id: str
    owner_id: str = Field(min_length=1, max_length=240)
    generation: int = Field(ge=1)
    acquired_at: datetime
    heartbeat_at: datetime
    expires_at: datetime
    recovered_attempt: bool
    prior_processing_state: Literal["pending", "retryable_failed", "processing"]

    @field_validator("lease_id")
    @classmethod
    def validate_lease_id(cls, value: str) -> str:
        if not _LEASE_ID.fullmatch(value):
            raise ValueError("lease_id must be a bounded observation lease record identity")
        return value

    @field_validator("product_id")
    @classmethod
    def validate_product_id(cls, value: str) -> str:
        if not _PRODUCT_ID.fullmatch(value):
            raise ValueError("product_id must be a product-scoped record identity")
        return value

    @field_validator("observation_id")
    @classmethod
    def validate_observation_id(cls, value: str) -> str:
        if not _OBSERVATION_ID.fullmatch(value):
            raise ValueError("observation_id must be an observation record identity")
        return value

    @field_validator("owner_id")
    @classmethod
    def validate_owner_id(cls, value: str) -> str:
        if not _OWNER_ID.fullmatch(value):
            raise ValueError("owner_id must be a bounded stable token")
        return value

    @field_validator("acquired_at", "heartbeat_at", "expires_at")
    @classmethod
    def validate_timezones(cls, value: datetime, info) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{info.field_name} must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Self:
        if self.heartbeat_at < self.acquired_at:
            raise ValueError("heartbeat_at must not precede acquired_at")
        if self.expires_at <= self.heartbeat_at:
            raise ValueError("expires_at must follow heartbeat_at")
        if self.recovered_attempt is not (self.prior_processing_state == "processing"):
            raise ValueError("recovered_attempt must reflect the prior processing state")
        return self


class ClaimedObservationV1(LeaseContract):
    """A lease plus the exact product-owned observation material it fences."""

    lease: ObservationLeaseV1
    observation: dict

    @model_validator(mode="after")
    def validate_observation_scope(self) -> Self:
        if str(self.observation.get("id") or "") != self.lease.observation_id:
            raise ValueError("claimed observation identity must match its lease")
        if str(self.observation.get("product") or "") != self.lease.product_id:
            raise ValueError("claimed observation product must match its lease")
        if str(self.observation.get("processing_lease_id") or "") != self.lease.lease_id:
            raise ValueError("claimed observation must carry its fencing lease")
        return self


class ObservationLeaseLost(RuntimeError):
    """The caller no longer owns the current, unexpired observation lease."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_lease_id(*, product_id: str, observation_id: str, owner_id: str) -> str:
    """Mint a collision-resistant product-scoped fencing identity."""
    material = f"{product_id}\x00{observation_id}\x00{owner_id}\x00{uuid.uuid4().hex}"
    return f"observation_lease:{hashlib.sha256(material.encode()).hexdigest()[:32]}"


def _raw_return_rows(raw: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        raise RuntimeError("unexpected lease transaction result shape")
    if "error" in raw:
        error = raw["error"]
        message = error.get("message", str(error)) if isinstance(error, dict) else str(error)
        raise RuntimeError(f"lease transaction failed: {message[:300]}")
    statements = raw.get("result") or []
    errors = [item for item in statements if isinstance(item, dict) and item.get("status") == "ERR"]
    if errors:
        messages = [str(item.get("result") or item) for item in errors]
        raise RuntimeError(f"lease transaction failed: {'; '.join(messages)[:300]}")
    if len(statements) < 2 or not isinstance(statements[-2], dict):
        raise RuntimeError("lease transaction omitted its return value")
    return parse_rows(statements[-2].get("result"))


def _lease_from_observation(row: dict[str, Any]) -> ObservationLeaseV1:
    prior_state = str(row.get("processing_lease_prior_state") or "pending")
    recovered = bool(row.get("processing_lease_recovered"))
    return ObservationLeaseV1(
        lease_id=str(row.get("processing_lease_id") or ""),
        product_id=str(row.get("product") or ""),
        observation_id=str(row.get("id") or ""),
        owner_id=str(row.get("processing_lease_owner") or ""),
        generation=int(row.get("processing_lease_generation") or 0),
        acquired_at=row.get("processing_lease_acquired_at"),
        heartbeat_at=row.get("processing_lease_heartbeat_at"),
        expires_at=row.get("processing_lease_expires_at"),
        recovered_attempt=recovered,
        prior_processing_state=prior_state,
    )


async def claim_next_observation(
    db_pool,
    *,
    product_id: str,
    owner_id: str,
    lease_seconds: float = DEFAULT_LEASE_SECONDS,
    orphan_after_seconds: float = LEGACY_PROCESSING_RECOVERY_SECONDS,
    now: datetime | None = None,
) -> ClaimedObservationV1 | None:
    """Atomically claim one due observation or recover one expired attempt.

    The candidate selection and conditional update execute in one SurrealDB
    transaction. Each invocation claims at most one row so work does not sit in
    an un-heartbeated client-side batch while an earlier model call runs.
    """
    if not _PRODUCT_ID.fullmatch(product_id):
        raise ValueError("claim requires a product record identity")
    if not _OWNER_ID.fullmatch(owner_id):
        raise ValueError("claim requires a bounded stable owner identity")
    if not 0.1 <= float(lease_seconds) <= 3_600:
        raise ValueError("lease_seconds must be between 0.1 and 3600")
    if not 0 <= float(orphan_after_seconds) <= 86_400:
        raise ValueError("orphan_after_seconds must be between 0 and 86400")

    claimed_at = now or _utcnow()
    if claimed_at.tzinfo is None or claimed_at.utcoffset() is None:
        raise ValueError("claim time must include a timezone")
    expires_at = claimed_at + timedelta(seconds=float(lease_seconds))
    orphan_cutoff = claimed_at - timedelta(seconds=float(orphan_after_seconds))
    # The ID is minted before selection. It is still product-scoped because the
    # transaction can assign it only to the requested product's candidate.
    provisional_observation = "observation:claim_candidate"
    lease_id = build_lease_id(
        product_id=product_id,
        observation_id=provisional_observation,
        owner_id=owner_id,
    )
    sql = """
        BEGIN;
        LET $candidate = SELECT VALUE id FROM observation
            WHERE product = <record>$product
              AND status = 'pending'
              AND (next_retry_at IS NONE OR next_retry_at <= $now)
              AND (
                    processing_state IS NONE
                    OR processing_state IN ['pending', 'retryable_failed']
                    OR (
                        processing_state = 'processing'
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
                    )
              )
            ORDER BY created_at ASC, id ASC
            LIMIT 1;
        LET $claimed = UPDATE $candidate SET
            processing_lease_prior_state = processing_state ?? 'pending',
            processing_lease_recovered = processing_state = 'processing',
            processing_state = 'processing',
            processing_lease_id = $lease_id,
            processing_lease_owner = $owner,
            processing_lease_generation = (processing_lease_generation ?? 0) + 1,
            processing_lease_acquired_at = $now,
            processing_lease_heartbeat_at = $now,
            processing_lease_expires_at = $expires_at,
            processing_started_at = IF processing_started_at IS NONE THEN $now ELSE processing_started_at END,
            processing_route = 'worker_leased',
            updated_at = time::now()
            WHERE product = <record>$product
              AND status = 'pending'
              AND (next_retry_at IS NONE OR next_retry_at <= $now)
              AND (
                    processing_state IS NONE
                    OR processing_state IN ['pending', 'retryable_failed']
                    OR processing_lease_expires_at <= $now
                    OR (
                        processing_lease_id IS NONE
                        AND (
                            processing_started_at IS NONE
                            OR processing_started_at <= $orphan_cutoff
                        )
                    )
              )
            RETURN AFTER;
        RETURN $claimed;
        COMMIT;
    """
    params = {
        "product": product_id,
        "owner": owner_id,
        "lease_id": lease_id,
        "now": claimed_at,
        "expires_at": expires_at,
        "orphan_cutoff": orphan_cutoff,
    }
    rows: list[dict[str, Any]] | None = None
    for conflict_attempt in range(5):
        try:
            async with db_pool.connection() as db:
                raw = await db.query_raw(sql, params)
            rows = _raw_return_rows(raw)
            break
        except Exception as exc:
            message = str(exc).lower()
            if "transaction" not in message or "conflict" not in message or conflict_attempt == 4:
                raise
            # Serializable write conflicts are expected when workers race for
            # the same head-of-queue row. A bounded yield lets the winner
            # commit; the loser then re-runs selection and normally gets none.
            await asyncio.sleep(0.005 * (conflict_attempt + 1))
    if rows is None:
        raise RuntimeError("lease claim retry loop produced no result")
    if not rows:
        return None
    row = rows[0]
    lease = _lease_from_observation(row)
    return ClaimedObservationV1(lease=lease, observation=row)


async def renew_observation_lease(
    db_pool,
    lease: ObservationLeaseV1,
    *,
    lease_seconds: float = DEFAULT_LEASE_SECONDS,
    now: datetime | None = None,
) -> ObservationLeaseV1:
    """Renew only the exact current, unexpired fencing lease."""
    if not 0.1 <= float(lease_seconds) <= 3_600:
        raise ValueError("lease_seconds must be between 0.1 and 3600")
    renewed_at = now or _utcnow()
    if renewed_at.tzinfo is None or renewed_at.utcoffset() is None:
        raise ValueError("renewal time must include a timezone")
    expires_at = renewed_at + timedelta(seconds=float(lease_seconds))
    async with db_pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """
                UPDATE <record>$observation SET
                    processing_lease_heartbeat_at = $now,
                    processing_lease_expires_at = $expires_at,
                    updated_at = time::now()
                WHERE product = <record>$product
                  AND processing_state = 'processing'
                  AND processing_lease_id = $lease_id
                  AND processing_lease_owner = $owner
                  AND processing_lease_expires_at > $now
                RETURN AFTER
                """,
                {
                    "observation": lease.observation_id,
                    "product": lease.product_id,
                    "lease_id": lease.lease_id,
                    "owner": lease.owner_id,
                    "now": renewed_at,
                    "expires_at": expires_at,
                },
            )
        )
    if not rows:
        raise ObservationLeaseLost("observation lease expired, was replaced, or crossed product scope")
    return _lease_from_observation(rows[0])


async def load_active_observation_lease(
    db_pool,
    *,
    observation_id: str,
    product_id: str,
    lease_id: str,
    owner_id: str,
    now: datetime | None = None,
) -> ObservationLeaseV1:
    """Load the exact current lease and fail closed once it expires."""
    checked_at = now or _utcnow()
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        raise ValueError("lease check time must include a timezone")
    async with db_pool.connection() as db:
        row = parse_one(
            await db.query(
                """
                SELECT * FROM ONLY <record>$observation
                WHERE product = <record>$product
                  AND processing_state = 'processing'
                  AND processing_lease_id = $lease_id
                  AND processing_lease_owner = $owner
                  AND processing_lease_expires_at > $now
                """,
                {
                    "observation": observation_id,
                    "product": product_id,
                    "lease_id": lease_id,
                    "owner": owner_id,
                    "now": checked_at,
                },
            )
        )
    if not row:
        raise ObservationLeaseLost("observation lease is no longer active")
    return _lease_from_observation(row)
