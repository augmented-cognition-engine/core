"""E2E tests for the grounding metabolism (spine) — v137.

When a grounded canvas object changes, the beliefs grounded in it can no longer
be assumed current. The metabolism enqueues exactly those beliefs (riding the
grounds-edge reverse lookup) and a drain pass marks them freshness-stale. This
is what makes "the graph is the mind" operationally true — the mind notices when
the ground under a belief moves.

Real SurrealDB (e2e): the enqueue's isolation (only the beliefs grounded in the
CHANGED object, never others) is load-bearing — a false enqueue would re-evaluate
unrelated beliefs.

Spec: docs/superpowers/specs/2026-07-15-grounding-metabolism-design.md
"""

from __future__ import annotations

import pytest

from core.engine.core.db import parse_one, parse_record_id, parse_rows

pytestmark = pytest.mark.e2e


class _FakeLLM:
    """Stub provider — returns a canned structured verdict, no real call."""

    def __init__(self, result):
        self._result = result
        self.calls = 0

    async def complete_structured(self, prompt, schema, model=None, max_tokens=4096):
        self.calls += 1
        return self._result


async def _mk_insight(db, content: str = "metabolism belief", freshness: float | None = None) -> str:
    r = await db.query(
        "CREATE insight SET content = $c, insight_type = 'pattern', tier = 'domain', "
        "confidence = 0.5, source_domain = 'metabolism-test', product = product:test",
        {"c": content},
    )
    iid = str(parse_one(r)["id"])
    if freshness is not None:
        await db.query(
            "UPDATE $id SET freshness_score = $f, freshness_last_computed = time::now()",
            {"id": parse_record_id(iid), "f": freshness},
        )
    return iid


async def _mk_artifact(db) -> str:
    r = await db.query("CREATE canvas_artifact SET shape_kind = 'sticky', author = 'ai', payload = {}")
    return str(parse_one(r)["id"])


async def _cleanup(db, ids: list[str]) -> None:
    for i in ids:
        try:
            await db.query(
                "DELETE reeval_request WHERE belief = $r OR trigger_object = $r",
                {"r": parse_record_id(i)},
            )
            await db.query("DELETE grounds WHERE in = $r OR out = $r", {"r": parse_record_id(i)})
            await db.query(f"DELETE {i}")
        except Exception:
            pass


async def _pending_for(db, belief_id: str, object_id: str) -> list[dict]:
    return parse_rows(
        await db.query(
            "SELECT * FROM reeval_request WHERE belief = $b AND trigger_object = $o AND status = 'pending'",
            {"b": parse_record_id(belief_id), "o": parse_record_id(object_id)},
        )
    )


# --------------------------------------------------------------------------- #
# enqueue — grounds_of → durable pending requests, isolated
# --------------------------------------------------------------------------- #
async def test_enqueue_targets_only_beliefs_grounded_in_the_changed_object(db_health, db_pool):
    from core.engine.graph.grounding import ground
    from core.engine.graph.metabolism import enqueue_reeval_for_object

    async with db_pool.connection() as db:
        b1 = await _mk_insight(db, "grounded in x")
        b2 = await _mk_insight(db, "grounded in y")
        x = await _mk_artifact(db)
        y = await _mk_artifact(db)
    try:
        await ground(b1, x, pool=db_pool)
        await ground(b2, y, pool=db_pool)

        n = await enqueue_reeval_for_object(x, pool=db_pool)
        assert n == 1  # only b1 grounds in x

        async with db_pool.connection() as db:
            assert len(await _pending_for(db, b1, x)) == 1
            assert len(await _pending_for(db, b2, x)) == 0  # b2 grounds in y, not x
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [b1, b2, x, y])


async def test_enqueue_is_idempotent_before_drain(db_health, db_pool):
    from core.engine.graph.grounding import ground
    from core.engine.graph.metabolism import enqueue_reeval_for_object

    async with db_pool.connection() as db:
        b = await _mk_insight(db)
        x = await _mk_artifact(db)
    try:
        await ground(b, x, pool=db_pool)
        await enqueue_reeval_for_object(x, pool=db_pool)
        await enqueue_reeval_for_object(x, pool=db_pool)  # second change before drain

        async with db_pool.connection() as db:
            assert len(await _pending_for(db, b, x)) == 1  # not two
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [b, x])


# --------------------------------------------------------------------------- #
# drain — pending → belief freshness-stale + request done
# --------------------------------------------------------------------------- #
async def test_drain_marks_belief_stale_and_request_done(db_health, db_pool):
    from core.engine.graph.grounding import ground
    from core.engine.graph.metabolism import drain_reeval, enqueue_reeval_for_object

    async with db_pool.connection() as db:
        b = await _mk_insight(db, freshness=0.9)  # currently fresh
        x = await _mk_artifact(db)
    try:
        await ground(b, x, pool=db_pool)
        await enqueue_reeval_for_object(x, pool=db_pool)

        drained = await drain_reeval(pool=db_pool)
        assert drained >= 1

        async with db_pool.connection() as db:
            belief = parse_one(await db.query("SELECT * FROM $b", {"b": parse_record_id(b)}))
            assert belief.get("freshness_score") == 0.0  # dropped from 0.9 → stale
            assert belief.get("freshness_last_computed") is None  # cleared → needs recompute
            # the request stays OPEN (pending) — the freshness-mark is an interim signal,
            # not a resolution; it must remain re-derivable (see the collision regression).
            pend = await _pending_for(db, b, x)
            assert len(pend) == 1
            assert pend[0].get("freshness_marked") is True
            assert pend[0].get("drained_at") is not None
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [b, x])


async def test_drain_does_not_touch_a_belief_that_was_never_enqueued(db_health, db_pool):
    from core.engine.graph.metabolism import drain_reeval

    async with db_pool.connection() as db:
        untouched = await _mk_insight(db, freshness=0.9)
    try:
        await drain_reeval(pool=db_pool)
        async with db_pool.connection() as db:
            belief = parse_one(await db.query("SELECT * FROM $b", {"b": parse_record_id(untouched)}))
            assert belief.get("freshness_score") == 0.9  # untouched
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [untouched])


async def test_drain_survives_a_dangling_belief(db_health, db_pool):
    from core.engine.graph.grounding import ground
    from core.engine.graph.metabolism import drain_reeval, enqueue_reeval_for_object

    async with db_pool.connection() as db:
        b = await _mk_insight(db)
        x = await _mk_artifact(db)
    try:
        await ground(b, x, pool=db_pool)
        await enqueue_reeval_for_object(x, pool=db_pool)
        async with db_pool.connection() as db:
            await db.query(f"DELETE {b}")  # belief gone after enqueue

        drained = await drain_reeval(pool=db_pool)  # must not raise
        assert drained >= 0
        async with db_pool.connection() as db:
            assert len(await _pending_for(db, b, x)) == 0  # request spent, not wedged
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [b, x])


# --------------------------------------------------------------------------- #
# the closed loop — object changes → beliefs re-evaluate, no LLM
# --------------------------------------------------------------------------- #
async def test_closed_loop_change_ground_then_belief_reads_stale(db_health, db_pool):
    from core.engine.graph.grounding import ground
    from core.engine.graph.metabolism import drain_reeval, enqueue_reeval_for_object

    async with db_pool.connection() as db:
        b = await _mk_insight(db, freshness=0.85)
        x = await _mk_artifact(db)
    try:
        await ground(b, x, pool=db_pool)
        # the ground shifts:
        async with db_pool.connection() as db:
            await db.query("UPDATE $o SET payload = {edited: true}", {"o": parse_record_id(x)})
        await enqueue_reeval_for_object(x, pool=db_pool)
        await drain_reeval(pool=db_pool)

        async with db_pool.connection() as db:
            belief = parse_one(await db.query("SELECT * FROM $b", {"b": parse_record_id(b)}))
            assert belief.get("freshness_score") == 0.0  # the mind noticed the ground moved
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [b, x])


# --------------------------------------------------------------------------- #
# observability — the partner can see what the metabolism is doing
# --------------------------------------------------------------------------- #
async def test_pending_reevaluations_surfaces_belief_and_trigger(db_health, db_pool):
    from core.engine.graph.grounding import ground
    from core.engine.graph.metabolism import enqueue_reeval_for_object, pending_reevaluations

    async with db_pool.connection() as db:
        b = await _mk_insight(db, "belief about pricing")
        x = await _mk_artifact(db)
    try:
        await ground(b, x, pool=db_pool)
        await enqueue_reeval_for_object(x, pool=db_pool)

        pend = await pending_reevaluations(pool=db_pool)
        mine = [p for p in pend if p["belief"] == b]
        assert len(mine) == 1
        assert mine[0]["belief_content"] == "belief about pricing"
        assert mine[0]["trigger_object"] == x
        assert mine[0]["reason"] == "ground_changed"
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [b, x])


async def test_pending_reevaluations_skips_dangling_belief(db_health, db_pool):
    from core.engine.graph.grounding import ground
    from core.engine.graph.metabolism import enqueue_reeval_for_object, pending_reevaluations

    async with db_pool.connection() as db:
        b = await _mk_insight(db)
        x = await _mk_artifact(db)
    try:
        await ground(b, x, pool=db_pool)
        await enqueue_reeval_for_object(x, pool=db_pool)
        async with db_pool.connection() as db:
            await db.query(f"DELETE {b}")  # belief gone; its request still pending

        pend = await pending_reevaluations(pool=db_pool)  # must not raise
        assert all(p["belief"] != b for p in pend)  # dangling belief omitted from the surface
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [b, x])


# --------------------------------------------------------------------------- #
# shadow re-derivation — the LLM proposes a new confidence, NEVER applies it
# --------------------------------------------------------------------------- #
async def test_rederive_belief_proposes_without_applying(db_health, db_pool):
    from core.engine.graph.grounding import ground
    from core.engine.graph.metabolism import _Rederivation, rederive_belief

    async with db_pool.connection() as db:
        b = await _mk_insight(db, "pricing is the top objection")  # confidence 0.5
        x = await _mk_artifact(db)
    try:
        await ground(b, x, pool=db_pool)
        fake = _FakeLLM(
            _Rederivation(still_supported=False, proposed_confidence=0.3, rationale="the frame now contradicts it")
        )
        proposal = await rederive_belief(b, pool=db_pool, llm=fake)

        assert fake.calls == 1
        assert proposal["still_supported"] is False
        assert proposal["proposed_confidence"] == 0.3
        assert "contradicts" in proposal["rationale"]
        # SHADOW: the belief's LIVE confidence is untouched — a proposal, not an apply.
        async with db_pool.connection() as db:
            belief = parse_one(await db.query("SELECT confidence FROM $b", {"b": parse_record_id(b)}))
            assert belief["confidence"] == 0.5
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [b, x])


async def test_rederive_belief_clamps_proposed_confidence(db_health, db_pool):
    from core.engine.graph.grounding import ground
    from core.engine.graph.metabolism import _Rederivation, rederive_belief

    async with db_pool.connection() as db:
        b = await _mk_insight(db)
        x = await _mk_artifact(db)
    try:
        await ground(b, x, pool=db_pool)
        fake = _FakeLLM(_Rederivation(still_supported=True, proposed_confidence=1.7, rationale="over range"))
        proposal = await rederive_belief(b, pool=db_pool, llm=fake)
        assert proposal["proposed_confidence"] == 1.0  # clamped from 1.7
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [b, x])


async def test_rederive_belief_returns_none_for_dangling(db_health, db_pool):
    from core.engine.graph.metabolism import rederive_belief

    fake = _FakeLLM(None)
    result = await rederive_belief("insight:does_not_exist", pool=db_pool, llm=fake)
    assert result is None
    assert fake.calls == 0  # never calls the LLM for a belief that doesn't resolve


async def test_rederive_pending_annotates_request_and_surfaces_proposal(db_health, db_pool):
    from core.engine.graph.grounding import ground
    from core.engine.graph.metabolism import (
        _Rederivation,
        enqueue_reeval_for_object,
        pending_reevaluations,
        rederive_pending,
    )

    async with db_pool.connection() as db:
        b = await _mk_insight(db, "pricing belief")
        x = await _mk_artifact(db)
    try:
        await ground(b, x, pool=db_pool)
        await enqueue_reeval_for_object(x, pool=db_pool)

        fake = _FakeLLM(
            _Rederivation(still_supported=True, proposed_confidence=0.62, rationale="the evidence still holds")
        )
        n = await rederive_pending(pool=db_pool, llm=fake)
        assert n >= 1

        # the proposal is surfaced to the partner on the pending request
        pend = await pending_reevaluations(pool=db_pool)
        mine = [p for p in pend if p["belief"] == b]
        assert mine
        assert mine[0].get("proposed_confidence") == 0.62
        assert mine[0].get("still_supported") is True
        assert "holds" in (mine[0].get("rederivation_rationale") or "")

        # still SHADOW: the belief's live confidence is untouched, and the request
        # is still pending (annotation does not consume the lifecycle).
        async with db_pool.connection() as db:
            belief = parse_one(await db.query("SELECT confidence FROM $b", {"b": parse_record_id(b)}))
            assert belief["confidence"] == 0.5

        # idempotent-ish: a second pass does not re-derive an already-proposed request
        n2 = await rederive_pending(pool=db_pool, llm=fake)
        assert n2 == 0
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [b, x])


async def test_rederive_survives_the_freshness_drain(db_health, db_pool):
    """The */15 cron freshness-drain must NOT destroy the state re-derivation and the
    observability surface depend on. Enqueue → drain (as the engine does on cron) →
    the request must STILL be re-derivable and STILL surfaced. Regression for the
    drain-vs-rederive lifecycle collision (adversarial review, 2026-07-15)."""
    from core.engine.graph.grounding import ground
    from core.engine.graph.metabolism import (
        _Rederivation,
        drain_reeval,
        enqueue_reeval_for_object,
        pending_reevaluations,
        rederive_pending,
    )

    async with db_pool.connection() as db:
        b = await _mk_insight(db, "pricing belief")
        x = await _mk_artifact(db)
    try:
        await ground(b, x, pool=db_pool)
        await enqueue_reeval_for_object(x, pool=db_pool)
        await drain_reeval(pool=db_pool)  # the cron runs BEFORE the partner re-derives

        # the belief is freshness-marked, but the request is NOT consumed:
        fake = _FakeLLM(_Rederivation(still_supported=False, proposed_confidence=0.3, rationale="moved"))
        n = await rederive_pending(pool=db_pool, llm=fake)
        assert n >= 1  # NOT preempted by the drain

        pend = await pending_reevaluations(pool=db_pool)
        mine = [p for p in pend if p["belief"] == b]
        assert mine and mine[0]["proposed_confidence"] == 0.3  # still surfaced after the drain
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [b, x])


async def test_ace_rederive_tool_runs_and_surfaces_proposals(db_health, db_pool):
    from core.engine.graph.grounding import ground
    from core.engine.graph.metabolism import _Rederivation, enqueue_reeval_for_object
    from core.engine.mcp.tools import ace_rederive

    async with db_pool.connection() as db:
        b = await _mk_insight(db, "pricing belief")
        x = await _mk_artifact(db)
    try:
        await ground(b, x, pool=db_pool)
        await enqueue_reeval_for_object(x, pool=db_pool)

        fake = _FakeLLM(_Rederivation(still_supported=False, proposed_confidence=0.25, rationale="the ground moved"))
        result = await ace_rederive(limit=5, llm=fake)
        assert result["rederived"] >= 1
        mine = [d for d in result["destabilized_beliefs"] if d["belief"] == b]
        assert mine and mine[0]["proposed_confidence"] == 0.25
    finally:
        async with db_pool.connection() as db:
            await _cleanup(db, [b, x])
