"""The session should build the most VALUABLE spec next, not the oldest one.

FIFO is a defensible default and a poor strategy: left alone overnight, a FIFO loop spends its
whole budget on whatever happened to be filed first. ACE already knows what matters — capability
gaps, scored against phase-relative floors, ranked by ProductPrioritizer. The session just has to
ask it.

Two properties worth pinning:

  - RE-RANK EVERY ITERATION, not once per session. A build that closes a gap CHANGES what is most
    valuable next; that is the compounding loop, and ranking once up-front would throw it away.
  - RANKING IS AN OPTIMIZATION, NEVER A GATE. If the prioritizer is unavailable, the session falls
    back to FIFO and keeps building. A ranking failure must never look like "no work left" — that
    is the lying instrument this whole layer exists to avoid.
"""

from __future__ import annotations

import pytest


class _FakeDB:
    """Serves the spec queue; the prioritizer is faked separately."""

    def __init__(self, specs):
        self.queries: list[tuple[str, dict]] = []
        self._specs = specs

    async def query(self, q, params=None):
        self.queries.append((q.strip(), params or {}))
        if "FROM agent_spec" in q:
            return [self._specs]
        if "FROM capability" in q:
            return [[{"id": "capability:auth", "slug": "auth"}, {"id": "capability:ui", "slug": "ui"}]]
        return [[]]


class _FakePool:
    def __init__(self, db):
        self._db = db

    def connection(self):
        db = self._db

        class Ctx:
            async def __aenter__(self):
                return db

            async def __aexit__(self, *a):
                return False

        return Ctx()


_SPECS = [
    # oldest first — FIFO would pick 'old' every time
    {"id": "agent_spec:old", "capability": "capability:ui", "created_at": "2026-01-01"},
    {"id": "agent_spec:new", "capability": "capability:auth", "created_at": "2026-07-01"},
]


@pytest.mark.asyncio
async def test_the_session_builds_the_most_valuable_spec_not_the_oldest(monkeypatch):
    import core.engine.arms.session as session

    async def _ranked(product_id, pool=None):
        # auth is in far worse shape than ui — its spec should win despite being newer
        return {"auth": 0.9, "ui": 0.1}

    monkeypatch.setattr(session, "_gap_scores_by_capability", _ranked)

    spec = await session._next_buildable_spec("product:platform", pool=_FakePool(_FakeDB(_SPECS)))

    assert spec == "agent_spec:new", "the urgent capability wins over the old filing date"


@pytest.mark.asyncio
async def test_fifo_breaks_ties_and_is_the_fallback_when_nothing_is_ranked(monkeypatch):
    import core.engine.arms.session as session

    async def _no_scores(product_id, pool=None):
        return {}

    monkeypatch.setattr(session, "_gap_scores_by_capability", _no_scores)

    spec = await session._next_buildable_spec("product:platform", pool=_FakePool(_FakeDB(_SPECS)))

    assert spec == "agent_spec:old", "with no signal, oldest-first — the honest default"


@pytest.mark.asyncio
async def test_a_broken_prioritizer_degrades_to_fifo_and_never_blocks_the_build(monkeypatch):
    """Ranking is an optimization. If it breaks, we build the oldest thing — we do NOT stop, and we
    certainly do not report an empty backlog."""
    import core.engine.arms.session as session

    async def _boom(product_id, pool=None):
        raise RuntimeError("prioritizer exploded")

    monkeypatch.setattr(session, "_gap_scores_by_capability", _boom)

    spec = await session._next_buildable_spec("product:platform", pool=_FakePool(_FakeDB(_SPECS)))

    assert spec == "agent_spec:old", "a dead ranker must not stop the loop — fall back, keep building"


@pytest.mark.asyncio
async def test_specs_with_no_capability_are_still_buildable(monkeypatch):
    """An unlinked spec scores nothing — it must still be built, just after the scored ones."""
    import core.engine.arms.session as session

    specs = [
        {"id": "agent_spec:orphan", "created_at": "2026-01-01"},  # no capability at all
        {"id": "agent_spec:scored", "capability": "capability:auth", "created_at": "2026-07-01"},
    ]

    async def _scores(product_id, pool=None):
        return {"auth": 0.8}

    monkeypatch.setattr(session, "_gap_scores_by_capability", _scores)

    spec = await session._next_buildable_spec("product:platform", pool=_FakePool(_FakeDB(specs)))
    assert spec == "agent_spec:scored"

    # ...and with nothing scored, the orphan is still picked up rather than stranded forever.
    async def _none(product_id, pool=None):
        return {}

    monkeypatch.setattr(session, "_gap_scores_by_capability", _none)
    spec = await session._next_buildable_spec("product:platform", pool=_FakePool(_FakeDB(specs)))
    assert spec == "agent_spec:orphan", "an unranked spec must never be permanently unbuildable"


@pytest.mark.asyncio
async def test_ranking_is_recomputed_every_iteration(monkeypatch):
    """The compounding property: closing a gap changes what matters next. Rank once per session and
    you throw that away — the loop would keep chasing a priority order that its own work invalidated."""
    import core.engine.arms.session as session

    calls = {"n": 0}
    built: list[str] = []

    async def _next(product_id, pool=None, exclude=None):
        calls["n"] += 1
        return f"agent_spec:{calls['n']}" if calls["n"] <= 3 else None

    async def _build(spec_id, product_id="product:platform", pool=None):
        built.append(spec_id)
        return {"built": True}

    async def _noop(*a, **kw):
        return 0

    monkeypatch.setattr(session, "_next_buildable_spec", _next)
    monkeypatch.setattr(session, "build_spec", _build)
    monkeypatch.setattr(session, "reconcile_stale_runs", _noop)

    await session.run_build_session(product_id="product:platform", max_builds=10)

    assert len(built) == 3
    assert calls["n"] == 4, "the queue is re-read (and so re-ranked) before EVERY build, not once"


@pytest.mark.asyncio
async def test_gap_scores_reuse_the_existing_prioritizer(monkeypatch):
    """Do not grow a second, rival ranking. ACE already scores gaps against phase-relative floors —
    ask it."""
    import core.engine.arms.session as session

    class _FakePrioritizer:
        def __init__(self, pool):
            pass

        async def prioritize(self, product_id):
            return [
                {"capability_slug": "auth", "priority_score": 0.4},
                {"capability_slug": "auth", "priority_score": 0.9},  # worst gap on auth wins
                {"capability_slug": "ui", "priority_score": 0.2},
            ]

    monkeypatch.setattr(session, "ProductPrioritizer", _FakePrioritizer)

    scores = await session._gap_scores_by_capability("product:platform", pool=_FakePool(_FakeDB([])))

    assert scores == {"auth": 0.9, "ui": 0.2}, "a capability is as urgent as its WORST gap"
