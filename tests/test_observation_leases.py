"""TP1B provider-free lease, concurrency, recovery, and health proofs."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from core.engine.capture.leases import (
    OBSERVATION_LEASE_CONTRACT_VERSION,
    ObservationLeaseLost,
    ObservationLeaseV1,
    claim_next_observation,
    renew_observation_lease,
)
from core.engine.capture.lifecycle import observation_outcome_health, process_observation_attempt
from core.engine.capture.outcomes import ObservationSynthesisOutcomeV1, SuccessfulDisposition
from core.engine.core.db import parse_one


def _token() -> str:
    return uuid.uuid4().hex[:16]


async def _seed_observation(
    db_pool,
    *,
    observation_id: str,
    product_id: str,
    state: str = "pending",
    attempt_count: int = 0,
    started_at: datetime | None = None,
    lease_id: str | None = None,
    lease_owner: str | None = None,
    lease_acquired_at: datetime | None = None,
    lease_heartbeat_at: datetime | None = None,
    lease_expires_at: datetime | None = None,
) -> dict:
    async with db_pool.connection() as db:
        row = parse_one(
            await db.query(
                """
                CREATE ONLY <record>$id SET
                    product = <record>$product,
                    content = 'TP1B synthetic lease input',
                    observation_type = 'pattern',
                    confidence = 0.8,
                    domain_hint = 'testing',
                    discipline_hint = 'testing',
                    source = 'test',
                    status = 'pending',
                    processing_state = $state,
                    processing_attempt_count = $attempt_count,
                    retry_count = $retry_count,
                    processing_started_at = $started_at,
                    processing_lease_id = $lease_id,
                    processing_lease_owner = $lease_owner,
                    processing_lease_generation = $generation,
                    processing_lease_acquired_at = $lease_acquired_at,
                    processing_lease_heartbeat_at = $lease_heartbeat_at,
                    processing_lease_expires_at = $lease_expires_at,
                    processing_lease_recovered = false,
                    processing_lease_prior_state = 'pending',
                    created_at = $created_at,
                    updated_at = $created_at
                """,
                {
                    "id": observation_id,
                    "product": product_id,
                    "state": state,
                    "attempt_count": attempt_count,
                    "retry_count": max(0, attempt_count - 1),
                    "started_at": started_at,
                    "lease_id": lease_id,
                    "lease_owner": lease_owner,
                    "generation": 1 if lease_id else None,
                    "lease_acquired_at": lease_acquired_at,
                    "lease_heartbeat_at": lease_heartbeat_at,
                    "lease_expires_at": lease_expires_at,
                    "created_at": started_at or datetime.now(timezone.utc),
                },
            )
        )
    assert row
    return row


async def _delete_observation(db_pool, observation_id: str) -> None:
    async with db_pool.connection() as db:
        await db.query("DELETE <record>$id", {"id": observation_id})


class _SkipSynthesizer:
    def __init__(self, **_kwargs):
        self._db_pool = None
        self._attempt_id = None

    async def add_observation(self, observation):
        outcome = ObservationSynthesisOutcomeV1(
            observation_id=str(observation["id"]),
            disposition=SuccessfulDisposition.SKIPPED,
            reason="synthetic provider-free TP1B recovery proof",
        )
        return {
            "new_insights": 0,
            "updates": 0,
            "conflicts": 0,
            "skipped": 1,
            "outcomes": [outcome.model_dump(mode="json")],
        }

    async def flush(self):
        return {"new_insights": 0, "updates": 0, "conflicts": 0, "skipped": 0, "outcomes": []}


def test_observation_lease_contract_is_frozen_and_time_bounded():
    now = datetime.now(timezone.utc)
    lease = ObservationLeaseV1(
        lease_id=f"observation_lease:{'a' * 32}",
        product_id="product:tp1b_contract",
        observation_id="observation:tp1b_contract",
        owner_id="worker:contract:1",
        generation=1,
        acquired_at=now,
        heartbeat_at=now,
        expires_at=now + timedelta(seconds=30),
        recovered_attempt=False,
        prior_processing_state="pending",
    )
    assert lease.contract_version == OBSERVATION_LEASE_CONTRACT_VERSION
    with pytest.raises(ValidationError):
        ObservationLeaseV1(**lease.model_dump(), invented=True)
    with pytest.raises(ValidationError):
        ObservationLeaseV1(
            **{
                **lease.model_dump(),
                "recovered_attempt": True,
                "prior_processing_state": "pending",
            }
        )
    with pytest.raises(ValidationError):
        ObservationLeaseV1(
            **{
                **lease.model_dump(),
                "heartbeat_at": now - timedelta(seconds=1),
            }
        )


@pytest.mark.asyncio
async def test_concurrent_workers_produce_exactly_one_claim(db_pool):
    token = _token()
    product_id = f"product:tp1b_race_{token}"
    observation_id = f"observation:tp1b_race_{token}"
    await _seed_observation(db_pool, observation_id=observation_id, product_id=product_id)
    try:
        claims = await asyncio.gather(
            *(
                claim_next_observation(
                    db_pool,
                    product_id=product_id,
                    owner_id=f"worker:race:{index}",
                    lease_seconds=5,
                )
                for index in range(8)
            )
        )
        winners = [claim for claim in claims if claim is not None]
        assert len(winners) == 1
        assert winners[0].lease.observation_id == observation_id
        assert winners[0].lease.product_id == product_id
        assert winners[0].lease.generation == 1
    finally:
        await _delete_observation(db_pool, observation_id)


@pytest.mark.asyncio
async def test_claim_and_renewal_fail_closed_across_product_and_owner(db_pool):
    token = _token()
    product_id = f"product:tp1b_scope_{token}"
    foreign_product = f"product:tp1b_foreign_{token}"
    observation_id = f"observation:tp1b_scope_{token}"
    await _seed_observation(db_pool, observation_id=observation_id, product_id=product_id)
    try:
        assert (
            await claim_next_observation(
                db_pool,
                product_id=foreign_product,
                owner_id="worker:foreign:1",
                lease_seconds=5,
            )
            is None
        )
        claimed = await claim_next_observation(
            db_pool,
            product_id=product_id,
            owner_id="worker:owner:1",
            lease_seconds=5,
        )
        assert claimed is not None
        forged = claimed.lease.model_copy(update={"owner_id": "worker:owner:2"})
        with pytest.raises(ObservationLeaseLost):
            await renew_observation_lease(db_pool, forged, lease_seconds=5)
        renewed = await renew_observation_lease(db_pool, claimed.lease, lease_seconds=5)
        assert renewed.owner_id == "worker:owner:1"
        assert renewed.expires_at > claimed.lease.expires_at
    finally:
        await _delete_observation(db_pool, observation_id)


@pytest.mark.asyncio
async def test_expired_attempt_is_recovered_without_increment_and_finalized(db_pool):
    token = _token()
    product_id = f"product:tp1b_recovery_{token}"
    observation_id = f"observation:tp1b_recovery_{token}"
    now = datetime.now(timezone.utc)
    stale_lease = ObservationLeaseV1(
        lease_id=f"observation_lease:{'b' * 32}",
        product_id=product_id,
        observation_id=observation_id,
        owner_id="worker:crashed:1",
        generation=1,
        acquired_at=now - timedelta(minutes=10),
        heartbeat_at=now - timedelta(minutes=9),
        expires_at=now - timedelta(minutes=8),
        recovered_attempt=False,
        prior_processing_state="pending",
    )
    await _seed_observation(
        db_pool,
        observation_id=observation_id,
        product_id=product_id,
        state="processing",
        attempt_count=1,
        started_at=stale_lease.acquired_at,
        lease_id=stale_lease.lease_id,
        lease_owner=stale_lease.owner_id,
        lease_acquired_at=stale_lease.acquired_at,
        lease_heartbeat_at=stale_lease.heartbeat_at,
        lease_expires_at=stale_lease.expires_at,
    )
    try:
        recovered = await claim_next_observation(
            db_pool,
            product_id=product_id,
            owner_id="worker:replacement:1",
            lease_seconds=10,
        )
        assert recovered is not None
        assert recovered.lease.recovered_attempt is True
        assert recovered.lease.prior_processing_state == "processing"
        assert recovered.lease.generation == 2
        with pytest.raises(ObservationLeaseLost):
            await renew_observation_lease(db_pool, stale_lease, lease_seconds=10)

        receipt = await process_observation_attempt(
            recovered.observation,
            db_pool=db_pool,
            route="worker_leased",
            synthesizer_factory=_SkipSynthesizer,
            scope_prevalidated=True,
            lease_id=recovered.lease.lease_id,
            lease_owner=recovered.lease.owner_id,
            lease_recovered=True,
        )
        assert receipt.attempt_count == 1
        assert receipt.outcome and receipt.outcome.disposition is SuccessfulDisposition.SKIPPED
        async with db_pool.connection() as db:
            row = parse_one(
                await db.query(
                    "SELECT * FROM ONLY <record>$id WHERE product = <record>$product",
                    {"id": observation_id, "product": product_id},
                )
            )
        assert row["status"] == "processed"
        assert row["processing_state"] == "succeeded"
        assert row["processing_attempt_count"] == 1
        assert row.get("processing_lease_id") is None

        health = await observation_outcome_health(db_pool, product_id=product_id)
        assert health["queue_depth"] == 0
        assert health["successful_outcomes_last_5m"] == 1
        assert health["successful_outcomes_per_minute_5m"] == 0.2
        assert health["expired_processing_lease_count"] == 0
    finally:
        await _delete_observation(db_pool, observation_id)


@pytest.mark.asyncio
async def test_heartbeat_prevents_recovery_while_processing_is_alive(db_pool):
    token = _token()
    product_id = f"product:tp1b_heartbeat_{token}"
    observation_id = f"observation:tp1b_heartbeat_{token}"
    await _seed_observation(db_pool, observation_id=observation_id, product_id=product_id)
    claimed = await claim_next_observation(
        db_pool,
        product_id=product_id,
        owner_id="worker:heartbeat:1",
        lease_seconds=0.2,
    )
    assert claimed is not None

    async def slow_processing(*_args, **_kwargs):
        await asyncio.sleep(0.35)
        return object()

    try:
        from core.engine.worker.processor import process_claimed_observation

        with (
            patch("core.engine.worker.processor.pool", db_pool),
            patch("core.engine.worker.processor.process_observation", slow_processing),
        ):
            processing = asyncio.create_task(
                process_claimed_observation(
                    claimed,
                    lease_seconds=0.2,
                    heartbeat_seconds=0.05,
                )
            )
            await asyncio.sleep(0.25)
            stolen = await claim_next_observation(
                db_pool,
                product_id=product_id,
                owner_id="worker:heartbeat:2",
                lease_seconds=0.2,
            )
            assert stolen is None
            await processing
    finally:
        await _delete_observation(db_pool, observation_id)


@pytest.mark.asyncio
async def test_health_degrades_for_expired_processing_lease(db_pool):
    token = _token()
    product_id = f"product:tp1b_health_{token}"
    observation_id = f"observation:tp1b_health_{token}"
    now = datetime.now(timezone.utc)
    await _seed_observation(
        db_pool,
        observation_id=observation_id,
        product_id=product_id,
        state="processing",
        attempt_count=1,
        started_at=now - timedelta(minutes=10),
        lease_id=f"observation_lease:{'c' * 32}",
        lease_owner="worker:expired:1",
        lease_acquired_at=now - timedelta(minutes=10),
        lease_heartbeat_at=now - timedelta(minutes=9),
        lease_expires_at=now - timedelta(minutes=8),
    )
    try:
        health = await observation_outcome_health(db_pool, product_id=product_id)
        assert health["status"] == "degraded"
        assert health["expired_processing_lease_count"] == 1
        assert health["oldest_processing_age_seconds"] >= 590
        assert "expired_processing_lease" in health["policy_breaches"]
        assert "oldest_processing_age" in health["policy_breaches"]
    finally:
        await _delete_observation(db_pool, observation_id)
