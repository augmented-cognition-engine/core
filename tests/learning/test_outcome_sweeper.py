"""Tests for engine/sentinel/engines/outcome_sweeper.py

Uses db_pool. Creates observations with future/past window_expires_at and
asserts the sweeper only transitions expired ones.
"""

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
async def clean_observations(db_pool):
    """Yield the db_pool, then clean up observations created for this test."""
    yield db_pool
    async with db_pool.connection() as db:
        await db.query(
            "DELETE outcome_observation WHERE product = <record>$pid",
            {"pid": "product:platform"},
        )


async def _insert_observation(db_pool, *, emission_id: str, outcome_label: str, expires_at: datetime) -> str:
    """Insert a bare outcome_observation row and return its id string."""
    async with db_pool.connection() as db:
        result = await db.query(
            """CREATE outcome_observation CONTENT {
                product: <record>$pid,
                emission_id: <string>$eid,
                emission_kind: 'recommendation',
                emission_topic: 'recommendation:test.test',
                pillar: 'test',
                discipline: 'test',
                emitted_at: time::now(),
                outcome_label: <string>$label,
                outcome_at: NONE,
                action_evidence: NONE,
                window_expires_at: <datetime>$expires
            }""",
            {
                "pid": "product:platform",
                "eid": emission_id,
                "label": outcome_label,
                "expires": expires_at.isoformat(),
            },
        )
    from core.engine.core.db import parse_rows

    rows = parse_rows(result)
    assert rows, f"Failed to insert observation {emission_id}"
    return str(rows[0]["id"])


@pytest.mark.asyncio
async def test_sweeper_transitions_expired_observations(db_pool, clean_observations):
    """Sweeper transitions open observations with past window_expires_at to 'ignored'."""
    from core.engine.core.db import parse_rows
    from core.engine.sentinel.engines.outcome_sweeper import sweep_expired_observations

    now = datetime.now(timezone.utc)

    # Expired (past)
    eid_expired = "sweep-test-expired-001"
    await _insert_observation(
        db_pool,
        emission_id=eid_expired,
        outcome_label="open",
        expires_at=now - timedelta(hours=1),
    )

    # Future (still active)
    eid_active = "sweep-test-active-001"
    await _insert_observation(
        db_pool,
        emission_id=eid_active,
        outcome_label="open",
        expires_at=now + timedelta(days=7),
    )

    result = await sweep_expired_observations("product:platform")
    assert result["observations_swept"] >= 1

    # Verify expired → ignored
    async with db_pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT outcome_label FROM outcome_observation WHERE product = <record>$pid AND emission_id = $eid",
                {"pid": "product:platform", "eid": eid_expired},
            )
        )
    assert len(rows) == 1
    assert rows[0]["outcome_label"] == "ignored"

    # Verify active → still open
    async with db_pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT outcome_label FROM outcome_observation WHERE product = <record>$pid AND emission_id = $eid",
                {"pid": "product:platform", "eid": eid_active},
            )
        )
    assert len(rows) == 1
    assert rows[0]["outcome_label"] == "open"


@pytest.mark.asyncio
async def test_sweeper_idempotent(db_pool, clean_observations):
    """Re-running sweeper on already-ignored rows is a no-op (doesn't double-count or error)."""
    from core.engine.sentinel.engines.outcome_sweeper import sweep_expired_observations

    now = datetime.now(timezone.utc)

    eid = "sweep-test-idempotent-001"
    await _insert_observation(
        db_pool,
        emission_id=eid,
        outcome_label="open",
        expires_at=now - timedelta(hours=2),
    )

    # First sweep
    r1 = await sweep_expired_observations("product:platform")
    assert r1["observations_swept"] >= 1

    # Second sweep — already ignored, should sweep 0 for this row
    r2 = await sweep_expired_observations("product:platform")
    # The specific row should not be swept again (it's no longer 'open')
    assert r2["observations_swept"] == 0


@pytest.mark.asyncio
async def test_sweeper_ignores_non_open_labels(db_pool, clean_observations):
    """Sweeper does NOT touch acted_on or answered rows even if window is expired."""
    from core.engine.core.db import parse_rows
    from core.engine.sentinel.engines.outcome_sweeper import sweep_expired_observations

    now = datetime.now(timezone.utc)

    # acted_on with expired window — should be left alone
    eid_acted = "sweep-test-acted-001"
    await _insert_observation(
        db_pool,
        emission_id=eid_acted,
        outcome_label="acted_on",
        expires_at=now - timedelta(hours=5),
    )

    await sweep_expired_observations("product:platform")

    async with db_pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT outcome_label FROM outcome_observation WHERE product = <record>$pid AND emission_id = $eid",
                {"pid": "product:platform", "eid": eid_acted},
            )
        )
    assert len(rows) == 1
    assert rows[0]["outcome_label"] == "acted_on"  # untouched


@pytest.mark.asyncio
async def test_sweeper_returns_count(db_pool, clean_observations):
    """sweep_expired_observations returns a count of swept rows."""
    from core.engine.sentinel.engines.outcome_sweeper import sweep_expired_observations

    now = datetime.now(timezone.utc)

    # Insert 2 expired, 1 active
    for i in range(2):
        await _insert_observation(
            db_pool,
            emission_id=f"sweep-count-expired-{i:03d}",
            outcome_label="open",
            expires_at=now - timedelta(minutes=30),
        )
    await _insert_observation(
        db_pool,
        emission_id="sweep-count-active-001",
        outcome_label="open",
        expires_at=now + timedelta(days=3),
    )

    result = await sweep_expired_observations("product:platform")
    assert result["observations_swept"] >= 2


def test_outcome_sweeper_registered():
    """outcome_sweeper sentinel engine is registered with the correct cron."""
    import core.engine.sentinel.engines.outcome_sweeper  # noqa: F401
    from core.engine.sentinel.registry import engine_registry

    assert "outcome_sweeper" in engine_registry
    entry = engine_registry["outcome_sweeper"]
    assert entry["cron"] == "0 */4 * * *"
