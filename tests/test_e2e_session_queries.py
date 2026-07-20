"""Does the session's SurrealQL actually RUN?

Every other session test uses a fake pool, which happily accepts any string as a query. That means
malformed SurrealQL — a bad cast, a v3 'ORDER BY field must be selected' violation, a record-id
binding mistake — would pass the entire fast suite and fail only in production, silently, inside a
loop nobody is watching. Exactly the reachability gap that keeps shipping green in this repo.

These tests execute each query against the real DB. They assert almost nothing about the RESULTS
(the DB may legitimately be empty) — the assertion is that the query PARSES AND EXECUTES.
"""

from __future__ import annotations

import pytest

PID = "product:platform"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_the_spec_queue_query_executes(db_pool):
    from core.engine.arms.session import _next_buildable_spec

    spec = await _next_buildable_spec(PID)  # must not raise: the SQL has to be valid
    assert spec is None or spec.startswith("agent_spec:")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_the_capability_slug_lookup_executes(db_pool):
    from core.engine.arms.session import _capability_slugs

    slugs = await _capability_slugs(PID)
    assert isinstance(slugs, dict)
    # Every key must be a real capability record id — this is the bridge the ranking depends on.
    # If it silently produced junk keys, spec→score lookups would all miss and the ranking would
    # degrade to FIFO while LOOKING like it worked.
    for cap_id in slugs:
        assert cap_id.startswith("capability:"), f"bad capability id key: {cap_id!r}"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_the_gap_ranking_executes_against_the_real_prioritizer(db_pool):
    from core.engine.arms.session import _gap_scores_by_capability

    scores = await _gap_scores_by_capability(PID)
    assert isinstance(scores, dict)
    for slug, score in scores.items():
        assert isinstance(slug, str) and slug
        assert isinstance(score, float)


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_the_run_ledger_round_trips_against_the_real_db(db_pool):
    """create → checkpoint → finalize → read back. The whole durability claim rests on this SQL
    actually working; a fake pool cannot tell us that it does."""
    from core.engine.arms import run_ledger

    run_id = await run_ledger.create_run(product_id=PID, intent="E2E_LEDGER probe", arm_domain="code")
    assert run_id and run_id.startswith("arm_run:"), "create_run must return a real record id"

    ev = await run_ledger.checkpoint(run_id, "planned", {"n_actions": 1}, seq=1)
    assert ev, "checkpoint must persist an arm_run_event"

    # While 'running', the run must appear in the attention list (that is the interrupted-build case).
    attention = await run_ledger.get_runs_needing_attention(product_id=PID)
    assert any(str(r["id"]) == run_id for r in attention), "a running build must be visible as needing attention"

    await run_ledger.finalize_run(run_id=run_id, status="verified", reason="probe", attempts=1)

    # Once verified it must DROP OUT of the attention list — a finished build is not waiting on anyone.
    attention_after = await run_ledger.get_runs_needing_attention(product_id=PID)
    assert not any(str(r["id"]) == run_id for r in attention_after), "a verified run must not nag a human"

    # Bind as a RecordID, not a string — a bare-string DELETE silently deletes NOTHING and the probe
    # rows would quietly accumulate in the attention list forever.
    from core.engine.core.db import parse_record_id

    ref = parse_record_id(run_id)
    async with db_pool.connection() as db:
        await db.query("DELETE arm_run_event WHERE run = $r", {"r": ref})
        await db.query("DELETE $r", {"r": ref})


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_reconcile_only_reaps_OLD_running_runs(db_pool):
    """The safety margin that keeps reconciliation from eating a build that is happening right now."""
    from core.engine.arms import run_ledger

    run_id = await run_ledger.create_run(product_id=PID, intent="E2E_RECONCILE probe", arm_domain="code")
    assert run_id

    # $r must be bound as a RecordID, not a bare string (the SurrealDB v3 trap).
    from core.engine.core.db import parse_record_id, parse_rows

    ref = parse_record_id(run_id)

    async def _status() -> str | None:
        async with db_pool.connection() as db:
            rows = parse_rows(await db.query("SELECT status FROM $r", {"r": ref}))
        return rows[0].get("status") if rows else None

    # A run created seconds ago is IN FLIGHT, not a zombie. Reaping it would be worse than the disease.
    await run_ledger.reconcile_stale_runs(product_id=PID, older_than_minutes=60)
    assert await _status() == "running", "a fresh run must NEVER be reaped as a zombie"

    # With a zero-minute threshold it IS old enough, and must be parked (never 'failed' — nobody
    # judged that work).
    n = await run_ledger.reconcile_stale_runs(product_id=PID, older_than_minutes=0)
    assert n >= 1
    assert await _status() == "parked"

    async with db_pool.connection() as db:
        await db.query("DELETE $r", {"r": ref})
