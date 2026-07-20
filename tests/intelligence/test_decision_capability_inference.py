# tests/intelligence/test_decision_capability_inference.py
"""Tests for atomic-claim batch capability inference module."""

import pytest

from core.engine.intelligence.decision_capability_inference import (
    infer_capabilities_for_decisions,
)


async def _seed_decision(pool, *, rationale, already_inferred=False):
    """Helper to seed a decision row in the test DB.

    When already_inferred=True, sets affected_capabilities_inferred_at via
    server-side time::now() (not a Python string).

    Returns: the decision ID (e.g., "decision:abc123")
    """
    async with pool.connection() as db:
        if already_inferred:
            # Mark as already-inferred with a placeholder capability list
            result = await db.query(
                """
                CREATE decision SET
                    product = <record>'product:test',
                    rationale = $rationale,
                    title = 'Test decision',
                    decision_type = 'architecture',
                    affected_capabilities = ['auth'],
                    affected_capabilities_inferred_at = time::now(),
                    affected_capabilities_confidence = 0.8
                RETURN id
                """,
                {"rationale": rationale},
            )
        else:
            # Uninferred row
            result = await db.query(
                """
                CREATE decision SET
                    product = <record>'product:test',
                    rationale = $rationale,
                    title = 'Test decision',
                    decision_type = 'architecture',
                    affected_capabilities = NONE,
                    affected_capabilities_inferred_at = NONE,
                    affected_capabilities_confidence = NONE
                RETURN id
                """,
                {"rationale": rationale},
            )
        from core.engine.core.db import parse_one

        row = parse_one(result)
        return row["id"] if row else None


def _stub_llm(monkeypatch, ids):
    """Make the batch LLM call deterministic for the given decision ids.

    Two tests here verify the atomic-CLAIM and idempotency behaviour, which is
    pure DB logic — `UPDATE ... WHERE inferred_at IS NONE` — and has nothing to
    do with what the model returns. Left un-stubbed, they made a live LLM call
    and flaked whenever the CLI provider degraded under sustained suite load
    (rows come back `errored` instead of `inferred`, and the count assertions
    break). Their siblings already stub the LLM (`_BoomLLM`, `_PartialLLM`);
    these two simply did not. Stubbing removes the uncontrolled input without
    weakening what the tests prove.
    """

    class _StubLLM:
        async def complete_json(self, *args, **kwargs):
            return {rid: {"affected_capabilities": ["auth"], "confidence": 0.9} for rid in ids}

    monkeypatch.setattr(
        "core.engine.intelligence.decision_capability_inference.get_llm",
        lambda: _StubLLM(),
    )


async def _fetch(pool, decision_id):
    """Fetch a decision row by ID."""
    from core.engine.core.db import parse_one, parse_record_id

    async with pool.connection() as db:
        result = await db.query(
            """SELECT id, title, rationale, decision_type,
                      affected_capabilities, affected_capabilities_inferred_at,
                      affected_capabilities_confidence
               FROM $decision_id""",
            {"decision_id": parse_record_id(decision_id)},
        )
        return parse_one(result)


@pytest.mark.asyncio
async def test_atomic_claim_skips_already_inferred_rows(db_pool, monkeypatch):
    """Atomic claim via UPDATE-with-WHERE-IS-NONE skips already-claimed rows.

    - Seed two decisions: one uninferred, one already-inferred
    - Run inference
    - Assert: exactly one inferred, one claimed_lost

    The skip is DB logic, independent of the model — so the LLM is stubbed
    (see `_stub_llm`). `decision_b` never reaches the LLM anyway: its claim
    returns nothing because `inferred_at` is already set, so `claimed_lost == 1`
    remains the real guard on the skip behaviour.
    """
    decision_a = await _seed_decision(db_pool, rationale="we chose flux capacitors", already_inferred=False)
    decision_b = await _seed_decision(db_pool, rationale="we chose dilithium", already_inferred=True)

    fetched_a = await _fetch(db_pool, decision_a)
    fetched_b = await _fetch(db_pool, decision_b)

    _stub_llm(monkeypatch, {decision_a})

    result = await infer_capabilities_for_decisions(
        decision_rows=[fetched_a, fetched_b],
        pool=db_pool,
    )

    # Only decision_a should be inferred this run; decision_b is claimed_lost
    assert result.inferred == 1
    assert result.claimed_lost == 1
    assert result.errored == 0


@pytest.mark.asyncio
async def test_batch_llm_failure_writes_empty_caps_and_continues(db_pool, monkeypatch):
    """LLM batch failure writes empty capabilities + inferred_at, doesn't re-raise.

    - Seed 3 uninferred decisions
    - Monkeypatch LLM to raise
    - Run inference
    - Assert: all 3 rows get affected_capabilities_inferred_at set + empty list
    """
    rows_ids = [await _seed_decision(db_pool, rationale=f"reason {i}", already_inferred=False) for i in range(3)]

    # Force the LLM to raise. The system may use any of three providers
    # (Claude API / CLI / Ollama) depending on env, so patch the get_llm
    # call site inside the module under test rather than a specific provider.
    class _BoomLLM:
        async def complete_json(self, *args, **kwargs):
            raise RuntimeError("LLM down")

    monkeypatch.setattr(
        "core.engine.intelligence.decision_capability_inference.get_llm",
        lambda: _BoomLLM(),
    )

    fetched = [await _fetch(db_pool, rid) for rid in rows_ids]

    result = await infer_capabilities_for_decisions(
        decision_rows=fetched,
        pool=db_pool,
    )

    assert result.inferred == 0
    assert result.errored == 3

    # Verify each row was claimed and written with empty caps
    for rid in rows_ids:
        row = await _fetch(db_pool, rid)
        assert row["affected_capabilities_inferred_at"] is not None, f"Row {rid} not marked inferred"
        assert row["affected_capabilities"] == [], f"Row {rid} doesn't have empty caps"


@pytest.mark.asyncio
async def test_partial_llm_response_marks_missing_rows_as_errored(db_pool, monkeypatch):
    """If the batched LLM response omits some rows, those rows commit with
    empty caps and count as `errored`, while present rows are inferred normally.

    This is the regression test for the failure mode where `_infer_batch` returns
    a dict shorter than the input (LLM dropped a row, returned malformed entry,
    etc.). Without the per-row miss-detection in `infer_capabilities_for_decisions`,
    missing rows would silently count as inferred=0 errored=0 — invisible loss.
    """
    rows_ids = [await _seed_decision(db_pool, rationale=f"reason {i}", already_inferred=False) for i in range(3)]
    fetched = [await _fetch(db_pool, rid) for rid in rows_ids]

    # LLM returns only the first 2 of the 3 decisions
    present_ids = {rows_ids[0], rows_ids[1]}

    class _PartialLLM:
        async def complete_json(self, *args, **kwargs):
            return {rid: {"affected_capabilities": ["auth"], "confidence": 0.9} for rid in present_ids}

    monkeypatch.setattr(
        "core.engine.intelligence.decision_capability_inference.get_llm",
        lambda: _PartialLLM(),
    )

    result = await infer_capabilities_for_decisions(decision_rows=fetched, pool=db_pool)

    assert result.inferred == 2
    assert result.errored == 1

    # The missing row should still have inferred_at set (claim happened) and
    # affected_capabilities=[] (empty-caps fallback).
    missing_id = rows_ids[2]
    missing_row = await _fetch(db_pool, missing_id)
    assert missing_row["affected_capabilities_inferred_at"] is not None
    assert missing_row["affected_capabilities"] == []


@pytest.mark.asyncio
async def test_second_run_finds_zero_uninferred(db_pool, monkeypatch):
    """Idempotency: second run against same data finds nothing left to infer.

    - Seed 5 uninferred decisions
    - Run inference → inferred=5
    - Fetch the same decisions again
    - Run inference again → inferred=0, claimed_lost=5

    The idempotency being proved is the claim's, not the model's, so the LLM is
    stubbed (the second run makes no LLM call at all — every row's claim returns
    nothing). This is what kept the test flaking under load.
    """
    rows_ids = [await _seed_decision(db_pool, rationale=f"reason {i}", already_inferred=False) for i in range(5)]
    fetched = [await _fetch(db_pool, rid) for rid in rows_ids]

    _stub_llm(monkeypatch, set(rows_ids))

    first = await infer_capabilities_for_decisions(decision_rows=fetched, pool=db_pool)
    assert first.inferred == 5

    # Re-fetch — inferred_at is now populated
    refetched = [await _fetch(db_pool, rid) for rid in rows_ids]
    second = await infer_capabilities_for_decisions(decision_rows=refetched, pool=db_pool)
    assert second.inferred == 0
    assert second.claimed_lost == 5
