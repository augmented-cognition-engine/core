"""One unbuildable spec must not stall the whole backlog.

The bug my own fakes hid from me:

    A failed build requeues its spec to 'approved' (correct — a failure IS retryable). The session
    then asks for the next buildable spec... and gets the SAME one back, because it is approved and
    still top-ranked. It fails again. And again. Until the consecutive-failure ceiling halts the
    entire session — having built nothing, and never having looked at any other spec.

    One spec that no arm can route (a real one is sitting in production right now) would therefore
    stall the entire backlog.

test_a_failed_build_does_not_stop_the_session passed the whole time, because its fake returned a
DIFFERENT spec on each call. The fake did not model requeueing, so it could not see the livelock.
That is the whole hazard of testing a loop against a fake queue.

The fix: within a session, never attempt the same spec twice. Its repair budget was already spent
inside dispatch; retrying it here just re-runs a build we already know fails. Move on to real work.
Across sessions it is still 'approved' and gets a fresh try — which is right, because the world may
have changed (a new arm, a fixed dep) between runs.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_a_failing_spec_is_not_retried_forever_within_one_session(monkeypatch):
    """The realistic queue: a failed build goes back to 'approved', so a naive re-read hands the
    same spec straight back."""
    import core.engine.arms.session as session

    # A REALISTIC queue: three approved specs. The first always fails and is requeued (so it stays
    # approved and keeps coming back). The other two build fine.
    approved = {"agent_spec:cursed", "agent_spec:a", "agent_spec:b"}
    order = ["agent_spec:cursed", "agent_spec:a", "agent_spec:b"]
    attempts: list[str] = []

    async def _next(product_id, pool=None, exclude=None):
        exclude = exclude or set()
        for sid in order:
            if sid in approved and sid not in exclude:
                return sid
        return None

    async def _build(spec_id, product_id="product:platform", pool=None):
        attempts.append(spec_id)
        if spec_id == "agent_spec:cursed":
            return {"built": False, "reason": "no arm can build this spec yet"}  # requeued, stays approved
        approved.discard(spec_id)  # a built spec leaves the queue
        return {"built": True, "branch": f"arm/{spec_id[-1]}"}

    async def _noop(*a, **kw):
        return 0

    monkeypatch.setattr(session, "_next_buildable_spec", _next)
    monkeypatch.setattr(session, "build_spec", _build)
    monkeypatch.setattr(session, "reconcile_stale_runs", _noop)
    monkeypatch.setattr(session, "reconcile_stranded_specs", _noop)

    out = await session.run_build_session(product_id="product:platform", max_builds=10)

    assert attempts.count("agent_spec:cursed") == 1, (
        "the cursed spec must be attempted ONCE. Retrying it re-runs a build we already know fails — "
        "and with ranking it stays top of the queue, so the session would grind on it until the "
        "failure ceiling and never look at the work it COULD have done."
    )
    assert len(out["built"]) == 2, "the other two specs must still get built — one bad spec is not a dead session"
    assert out["stopped_because"] == "no work left"


@pytest.mark.asyncio
async def test_the_queue_read_receives_the_exclusion_set(monkeypatch):
    """Wiring check: the skip-list is useless if the selector never sees it."""
    import core.engine.arms.session as session

    seen_excludes: list[set] = []

    async def _next(product_id, pool=None, exclude=None):
        seen_excludes.append(set(exclude or ()))
        return "agent_spec:x" if not exclude else None

    async def _build(spec_id, product_id="product:platform", pool=None):
        return {"built": False, "reason": "nope"}

    async def _noop(*a, **kw):
        return 0

    monkeypatch.setattr(session, "_next_buildable_spec", _next)
    monkeypatch.setattr(session, "build_spec", _build)
    monkeypatch.setattr(session, "reconcile_stale_runs", _noop)
    monkeypatch.setattr(session, "reconcile_stranded_specs", _noop)

    await session.run_build_session(product_id="product:platform", max_builds=5)

    assert seen_excludes[0] == set(), "nothing attempted yet"
    assert "agent_spec:x" in seen_excludes[1], "an attempted spec must be excluded from the next read"


@pytest.mark.asyncio
async def test_the_selector_actually_filters_excluded_specs():
    """And the selector must honour it — against the real query shape."""
    from core.engine.arms.session import _next_buildable_spec

    class _DB:
        async def query(self, q, params=None):
            if "FROM agent_spec" in q:
                return [
                    [
                        {"id": "agent_spec:one", "created_at": "2026-01-01"},
                        {"id": "agent_spec:two", "created_at": "2026-02-01"},
                    ]
                ]
            return [[]]

    class _Pool:
        def connection(self):
            class Ctx:
                async def __aenter__(self):
                    return _DB()

                async def __aexit__(self, *a):
                    return False

            return Ctx()

    assert await _next_buildable_spec("product:platform", pool=_Pool()) == "agent_spec:one"
    assert await _next_buildable_spec("product:platform", pool=_Pool(), exclude={"agent_spec:one"}) == "agent_spec:two"
    assert (
        await _next_buildable_spec("product:platform", pool=_Pool(), exclude={"agent_spec:one", "agent_spec:two"})
        is None
    ), "everything attempted → no work left, not an infinite loop"
